import os
import tomli
import tomli_w
import yaml
import subprocess
import re
import shutil
import requests
import time
from concurrent.futures import ThreadPoolExecutor
import base64
import secrets
from pathlib import Path
from rich.console import Console
from yaml.resolver import BaseResolver
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from tempfile import NamedTemporaryFile, TemporaryDirectory
from kubernetes import client, config

from domino.cli.utils.constants import COLOR_PALETTE, DOMINO_HELM_PATH, DOMINO_HELM_VERSION, DOMINO_HELM_REPOSITORY


class AsLiteral(str):
    pass


def represent_literal(dumper, data):
    return dumper.represent_scalar(BaseResolver.DEFAULT_SCALAR_TAG, data, style="|")


yaml.add_representer(AsLiteral, represent_literal)


console = Console()


###############################################################################
# GIT PROVIDER HELPERS
###############################################################################

# SSH host and URL scheme differ per provider.
_GIT_SSH_HOSTS = {
    "github":    "github.com",
    "gitlab":    "gitlab.com",
    "generic":   None,   # resolved from DOMINO_GIT_SSH_HOST env var at runtime
}


def _get_provider(platform_config: dict | None = None) -> str:
    """
    Return the active git provider.
    Resolution order:
      1. [git] section in the loaded config dict (if provided)
      2. DOMINO_GIT_PROVIDER env var
      3. fall back to 'github' for backwards compatibility
    """
    if platform_config:
        git_section = platform_config.get("git") or {}
        provider = git_section.get("DOMINO_GIT_PROVIDER")
        if provider:
            return provider.lower()
    return os.environ.get("DOMINO_GIT_PROVIDER", "github").lower()


def _git_ssh_url(provider: str, repository: str) -> str:
    """
    Build the SSH clone URL for the given provider and repository path.

    repository is expected in 'namespace/project' form (no host, no .git suffix).

    Examples:
      github    → ssh://git@github.com/org/repo.git
      gitlab    → ssh://git@gitlab.com/org/repo.git
      generic   → ssh://git@<DOMINO_GIT_SSH_HOST>/org/repo.git
    """
    host = _GIT_SSH_HOSTS.get(provider)
    if host is None:
        host = os.environ.get("DOMINO_GIT_SSH_HOST", "")
        if not host:
            raise ValueError(
                "Git provider is 'generic' but DOMINO_GIT_SSH_HOST env var is not set."
            )
    return f"ssh://git@{host}/{repository.strip('/')}.git"


def _strip_host_from_repo(provider: str, raw: str) -> str:
    """
    Normalise a repository value that may include a full URL into
    'namespace/project' form.

    Handles inputs like:
      https://github.com/org/repo   → org/repo
      git@github.com:org/repo.git   → org/repo
      org/repo                      → org/repo  (no-op)
    """
    # Strip common URL prefixes
    for prefix in ("https://", "http://", "ssh://"):
        if raw.startswith(prefix):
            raw = raw.split("//", 1)[1]
            break

    # Strip host portion (everything up to and including the first / or :)
    host = _GIT_SSH_HOSTS.get(provider, "")
    if host and host in raw:
        raw = raw.split(host, 1)[1].lstrip("/:")

    return raw.removesuffix(".git").strip("/")


###############################################################################
# SSH KEY HELPERS
###############################################################################

def create_ssh_pair_key():
    """Generate an RSA-4096 SSH key pair for GitSync."""
    provider_label = os.environ.get("DOMINO_GIT_PROVIDER", "GitHub").capitalize()
    console.print(f"Generating SSH key pair for {provider_label} Workflows...")
    key = rsa.generate_private_key(
        backend=crypto_default_backend(),
        public_exponent=65537,
        key_size=4096,
    )
    private_key = key.private_bytes(
        crypto_serialization.Encoding.PEM,
        crypto_serialization.PrivateFormat.PKCS8,
        crypto_serialization.NoEncryption(),
    )
    public_key = key.public_key().public_bytes(
        crypto_serialization.Encoding.OpenSSH,
        crypto_serialization.PublicFormat.OpenSSH,
    )
    return private_key, public_key


###############################################################################
# PREPARE PLATFORM
###############################################################################

def prepare_platform(
    cluster_name: str,
    http_port: int,
    https_port: int,
    workflows_repository: str,
    github_workflows_ssh_private_key: str,       # kwarg kept for CLI compat
    github_default_pieces_repository_token: str,  # kwarg kept for CLI compat
    github_workflows_token: str,                  # kwarg kept for CLI compat
    deploy_mode: str,
    local_pieces_repository_path: list,
    local_domino_path: str,
    local_rest_image: str,
    local_frontend_image: str,
    local_airflow_image: str,
    git_provider: str | None = None,
) -> None:
    """
    Create (or update) the local config-domino-local.toml with all platform
    settings.  All git-provider-specific values are written under a [git]
    section so the file stays provider-agnostic; legacy [github] keys are
    also written for backwards compatibility with older tooling that reads
    the file directly.
    """
    config_file_path = Path(__file__).resolve().parent / "config-domino-local.toml"
    with open(str(config_file_path), "rb") as f:
        config_dict = tomli.load(f)

    # Resolve provider — CLI flag wins, then env var, then default
    if git_provider is None:
        git_provider = os.environ.get("DOMINO_GIT_PROVIDER", "github").lower()

    running_path = str(Path().cwd().resolve())
    config_dict["path"]["DOMINO_LOCAL_RUNNING_PATH"] = running_path
    config_dict["kind"]["DOMINO_KIND_CLUSTER_NAME"] = cluster_name
    config_dict["kind"]["DOMINO_DEPLOY_MODE"] = deploy_mode
    config_dict["kind"]["DOMINO_KIND_CLUSTER_HTTP_PORT"] = http_port
    config_dict["kind"]["DOMINO_KIND_CLUSTER_HTTPS_PORT"] = https_port
    config_dict["domino_frontend"]["API_URL"] = "http://localhost{}/api".format(f":{http_port}")

    if deploy_mode == "local-k8s-dev":
        config_dict["dev"]["DOMINO_AIRFLOW_IMAGE"] = local_airflow_image
        config_dict["dev"]["DOMINO_REST_IMAGE"] = local_rest_image
        config_dict["dev"]["DOMINO_FRONTEND_IMAGE"] = local_frontend_image
        config_dict["dev"]["DOMINO_LOCAL_DOMINO_PACKAGE"] = local_domino_path
        for local_pieces_repository in local_pieces_repository_path:
            repo_config_file_path = Path(local_pieces_repository).resolve() / "config.toml"
            with open(str(repo_config_file_path), "rb") as f:
                repo_toml = tomli.load(f)
            repo_name = repo_toml["repository"]["REPOSITORY_NAME"]
            config_dict["dev"][repo_name] = local_pieces_repository

    # Normalise the repository to 'namespace/project' form
    repo_path = _strip_host_from_repo(git_provider, workflows_repository)

    # -----------------------------------------------------------------------
    # Write provider-agnostic [git] section
    # -----------------------------------------------------------------------
    if "git" not in config_dict:
        config_dict["git"] = {}

    config_dict["git"]["DOMINO_GIT_PROVIDER"] = git_provider
    config_dict["git"]["DOMINO_GIT_WORKFLOWS_REPOSITORY"] = repo_path
    config_dict["git"]["DOMINO_GIT_ACCESS_TOKEN_WORKFLOWS"] = github_workflows_token
    config_dict["git"]["DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN"] = github_default_pieces_repository_token

    ssh_private_key = github_workflows_ssh_private_key   # alias for readability below
    if not ssh_private_key:
        private_key, public_key = create_ssh_pair_key()
        ssh_private_key = base64.b64encode(private_key).decode("utf-8")
        config_dict["git"]["DOMINO_GIT_WORKFLOWS_SSH_PRIVATE_KEY"] = ssh_private_key
        config_dict["git"]["DOMINO_GIT_WORKFLOWS_SSH_PUBLIC_KEY"] = public_key.decode("utf-8")
    else:
        config_dict["git"]["DOMINO_GIT_WORKFLOWS_SSH_PRIVATE_KEY"] = ssh_private_key

    # -----------------------------------------------------------------------
    # Mirror values into legacy [github] section for backwards compatibility
    # -----------------------------------------------------------------------
    if "github" not in config_dict:
        config_dict["github"] = {}

    config_dict["github"]["DOMINO_GITHUB_WORKFLOWS_REPOSITORY"] = repo_path
    config_dict["github"]["DOMINO_GITHUB_ACCESS_TOKEN_WORKFLOWS"] = github_workflows_token
    config_dict["github"]["DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN"] = github_default_pieces_repository_token
    config_dict["github"]["DOMINO_GITHUB_WORKFLOWS_SSH_PRIVATE_KEY"] = ssh_private_key
    if "DOMINO_GIT_WORKFLOWS_SSH_PUBLIC_KEY" in config_dict.get("git", {}):
        config_dict["github"]["DOMINO_GITHUB_WORKFLOWS_SSH_PUBLIC_KEY"] = config_dict["git"]["DOMINO_GIT_WORKFLOWS_SSH_PUBLIC_KEY"]

    with open("config-domino-local.toml", "wb") as f:
        tomli_w.dump(config_dict, f)

    console.print("")
    console.print(f"Domino is prepared to run at: {running_path}")
    console.print(f"You can check and modify the configuration file at: {running_path}/config-domino-local.toml")
    console.print("Next, run: `domino platform create`")
    console.print("")


###############################################################################
# CREATE PLATFORM
###############################################################################

def create_platform(install_airflow: bool = True, use_gpu: bool = False) -> None:
    with open("config-domino-local.toml", "rb") as f:
        platform_config = tomli.load(f)

    # Resolve provider from config, then env, then default
    provider = _get_provider(platform_config)

    # Read git settings — prefer [git] section, fall back to legacy [github]
    def _git(key_new: str, key_legacy: str, default=None):
        """Read from [git] first, then legacy [github], then default."""
        git_section = platform_config.get("git") or {}
        github_section = platform_config.get("github") or {}
        return (
            git_section.get(key_new)
            or github_section.get(key_legacy)
            or default
        )

    token_pieces    = _git("DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN", "DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN")
    token_workflows = _git("DOMINO_GIT_ACCESS_TOKEN_WORKFLOWS",      "DOMINO_GITHUB_ACCESS_TOKEN_WORKFLOWS")
    workflows_repo  = _git("DOMINO_GIT_WORKFLOWS_REPOSITORY",        "DOMINO_GITHUB_WORKFLOWS_REPOSITORY")
    ssh_private_key = _git("DOMINO_GIT_WORKFLOWS_SSH_PRIVATE_KEY",   "DOMINO_GITHUB_WORKFLOWS_SSH_PRIVATE_KEY")

    # Build Kind cluster config
    kubeadm_config_patches = dict(
        kind="InitConfiguration",
        nodeRegistration=dict(
            kubeletExtraArgs={"node-labels": "ingress-ready=true"}
        ),
    )
    extra_mounts_local_repositories = []
    domino_dev_private_variables_list = [
        "DOMINO_LOCAL_DOMINO_PACKAGE",
        "DOMINO_REST_IMAGE",
        "DOMINO_FRONTEND_IMAGE",
        "DOMINO_AIRFLOW_IMAGE",
    ]
    local_pieces_repositories = {
        key: value
        for key, value in platform_config["dev"].items()
        if key not in domino_dev_private_variables_list
    }

    if platform_config["kind"]["DOMINO_DEPLOY_MODE"] == "local-k8s-dev":
        for repo_name, repo_path in local_pieces_repositories.items():
            extra_mounts_local_repositories.append(
                dict(
                    hostPath=repo_path,
                    containerPath=f"/pieces_repositories/{repo_name}",
                    readOnly=True,
                    propagation="HostToContainer",
                )
            )
        if platform_config["dev"].get("DOMINO_LOCAL_DOMINO_PACKAGE"):
            domino_local_package_absolute_path = Path(
                platform_config["dev"]["DOMINO_LOCAL_DOMINO_PACKAGE"]
            ).resolve()
            extra_mounts_local_repositories.append(
                dict(
                    hostPath=str(domino_local_package_absolute_path),
                    containerPath="/domino/domino_py/src/domino",
                    readOnly=True,
                    propagation="HostToContainer",
                )
            )

    kubeadm_parsed = AsLiteral(yaml.dump(kubeadm_config_patches))
    use_gpu_dict = {} if not use_gpu else {"gpus": True}
    kind_config = dict(
        kind="Cluster",
        apiVersion="kind.x-k8s.io/v1alpha4",
        nodes=[
            dict(
                role="control-plane",
                kubeadmConfigPatches=[kubeadm_parsed],
                extraPortMappings=[
                    dict(
                        containerPort=80,
                        hostPort=platform_config["kind"].get("DOMINO_KIND_CLUSTER_HTTP_PORT", 80),
                        listenAddress="0.0.0.0",
                        protocol="TCP",
                    ),
                    dict(
                        containerPort=443,
                        hostPort=platform_config["kind"].get("DOMINO_KIND_CLUSTER_HTTPS_PORT", 443),
                        listenAddress="0.0.0.0",
                        protocol="TCP",
                    ),
                ],
            ),
            dict(
                role="worker",
                extraMounts=[
                    dict(
                        hostPath=platform_config["path"]["DOMINO_LOCAL_RUNNING_PATH"] + "/workflow_shared_storage",
                        containerPath="/cluster_shared_storage",
                        readOnly=False,
                        propagation="Bidirectional",
                    ),
                    *extra_mounts_local_repositories,
                ],
                **use_gpu_dict,
            ),
        ],
    )
    with open("kind-cluster-config.yaml", "w") as f:
        yaml.dump(kind_config, f)

    cluster_name = platform_config["kind"]["DOMINO_KIND_CLUSTER_NAME"]

    # Delete previous Kind cluster
    console.print("")
    console.print(f"Removing previous Kind cluster - {cluster_name}...")
    result = subprocess.run(
        ["kind", "delete", "cluster", "--name", cluster_name], capture_output=True, text=True
    )
    if result.returncode != 0:
        error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise Exception(f"An error occurred while deleting previous Kind cluster - {cluster_name}: {error_message}")
    console.print("")

    # Create new Kind cluster
    console.print(f"Creating new Kind cluster - {cluster_name}...")
    result = subprocess.run(
        ["kind", "create", "cluster", "--name", cluster_name, "--config", "kind-cluster-config.yaml"]
    )
    if result.returncode != 0:
        error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise Exception(f"An error occurred while creating Kind cluster - {cluster_name}: {error_message}")
    console.print("")
    console.print("Kind cluster created successfully!", style=f"bold {COLOR_PALETTE.get('success')}")

    # Install Ingress NGINX controller
    console.print("")
    console.print("Installing NGINX controller...")
    subprocess.run(
        ["kubectl", "apply", "-f", "https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml"],
        stdout=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["kubectl", "wait", "--namespace", "ingress-nginx", "--for", "condition=ready", "pod",
         "--selector=app.kubernetes.io/component=controller", "--timeout=660s"]
    )
    if result.returncode != 0:
        error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise Exception(f"An error occurred while installing NGINX controller: {error_message}")
    console.print("NGINX controller installed successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
    console.print("")

    # Load local images to Kind cluster
    local_domino_airflow_image   = platform_config.get("dev", {}).get("DOMINO_AIRFLOW_IMAGE", None)
    local_domino_frontend_image  = platform_config.get("dev", {}).get("DOMINO_FRONTEND_IMAGE", None)
    local_domino_rest_image      = platform_config.get("dev", {}).get("DOMINO_REST_IMAGE", None)

    _is_dev_mode = platform_config["kind"]["DOMINO_DEPLOY_MODE"] == "local-k8s-dev"

    domino_airflow_image_tag = "latest"
    domino_airflow_image = os.environ.get("DOMINO_AIRFLOW_IMAGE", "ghcr.io/iisas/domino-airflow-base")
    if local_domino_airflow_image:
        console.print(f"Loading local Domino Airflow image {local_domino_airflow_image} to Kind cluster...")
        subprocess.run(["kind", "load", "docker-image", local_domino_airflow_image, "--name", cluster_name, "--nodes", f"{cluster_name}-worker"])
        domino_airflow_image = f"docker.io/library/{local_domino_airflow_image}"
    elif _is_dev_mode and not local_domino_airflow_image:
        domino_airflow_image_tag = "latest-dev"

    if local_domino_frontend_image:
        console.print(f"Loading local frontend image {local_domino_frontend_image} to Kind cluster...")
        subprocess.run(["kind", "load", "docker-image", local_domino_frontend_image, "--name", cluster_name, "--nodes", f"{cluster_name}-worker"])
        domino_frontend_image = f"docker.io/library/{local_domino_frontend_image}"
    elif _is_dev_mode:
        domino_frontend_image = os.environ.get("DOMINO_FRONTEND_IMAGE", "ghcr.io/iisas/domino-frontend:k8s-dev")
    else:
        domino_frontend_image = os.environ.get("DOMINO_FRONTEND_IMAGE", "ghcr.io/iisas/domino-frontend:k8s")

    if local_domino_rest_image:
        console.print(f"Loading local REST image {local_domino_rest_image} to Kind cluster...")
        subprocess.run(["kind", "load", "docker-image", local_domino_rest_image, "--name", cluster_name, "--nodes", f"{cluster_name}-worker"])
        domino_rest_image = f"docker.io/library/{local_domino_rest_image}"
    elif _is_dev_mode:
        domino_rest_image = os.environ.get("DOMINO_REST_IMAGE", "ghcr.io/iisas/domino-rest:latest-dev")
    else:
        domino_rest_image = os.environ.get("DOMINO_REST_IMAGE", "ghcr.io/iisas/domino-rest:latest")

    # NVIDIA GPU operator
    if use_gpu:
        console.print("Installing NVIDIA GPU Operator...")
        subprocess.run(["helm", "repo", "add", "nvidia", "https://nvidia.github.io/gpu-operator"])
        subprocess.run(["helm", "repo", "update"])
        subprocess.run(
            "helm install --wait --generate-name -n gpu-operator --create-namespace nvidia/gpu-operator --set driver.enabled=false",
            shell=True,
        )

    # Override values for Domino Helm chart
    db_enabled = platform_config["domino_db"].get("DOMINO_CREATE_DATABASE", True)
    domino_values_override_config = {
        "git_access_token_pieces":    token_pieces,
        "git_access_token_workflows": token_workflows,
        "frontend": {
            "enabled":    True,
            "image":      domino_frontend_image,
            "apiEnv":     "dev" if platform_config["kind"]["DOMINO_DEPLOY_MODE"] in ["local-k8s-dev", "local-k8s"] else "prod",
            "deployMode": platform_config["kind"]["DOMINO_DEPLOY_MODE"],
            "apiUrl":     platform_config["domino_frontend"].get(
                "API_URL",
                "http://localhost:{}/api".format(platform_config["kind"].get("DOMINO_KIND_CLUSTER_HTTP_PORT", 80)),
            ),
            "baseName": platform_config["domino_frontend"].get("BASE_NAME", "/"),
        },
        "rest": {
            "enabled":           True,
            "image":             domino_rest_image,
            "workflowsRepository": workflows_repo,
            "createDefaultUser": platform_config["domino_db"].get("DOMINO_CREATE_DEFAULT_USER", True),
        },
    }

    if not db_enabled:
        domino_values_override_config["database"] = {
            **domino_values_override_config.get("database", {}),
            "host":     platform_config["domino_db"]["DOMINO_DB_HOST"],
            "name":     platform_config["domino_db"]["DOMINO_DB_NAME"],
            "user":     platform_config["domino_db"]["DOMINO_DB_USER"],
            "password": platform_config["domino_db"]["DOMINO_DB_PASSWORD"],
            "port":     str(platform_config["domino_db"].get("DOMINO_DB_PORT", 5432)),
        }

    # Override values for Airflow Helm chart
    # GitSync SSH URL is now built from the active provider
    git_sync_repo = _git_ssh_url(provider, workflows_repo)

    airflow_ssh_config = dict(gitSshKey=ssh_private_key)
    airflow_ssh_config_parsed = AsLiteral(yaml.dump(airflow_ssh_config))

    extra_env = [dict(name="AIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL", value="10")]
    extra_env_parsed = AsLiteral(yaml.dump(extra_env))

    workers_extra_volumes = []
    workers_extra_volumes_mounts = []
    workers = {}
    scheduler = {}
    if (
        platform_config["kind"]["DOMINO_DEPLOY_MODE"] == "local-k8s-dev"
        and platform_config["dev"].get("DOMINO_LOCAL_DOMINO_PACKAGE")
    ):
        workers_extra_volumes = [
            {"name": "domino-dev-extra", "persistentVolumeClaim": {"claimName": "domino-dev-volume-claim"}}
        ]
        workers_extra_volumes_mounts = [
            {"name": "domino-dev-extra", "mountPath": "/opt/airflow/domino/domino_py/src/domino"}
        ]
        workers   = {"workers":   {"extraVolumes": workers_extra_volumes, "extraVolumeMounts": workers_extra_volumes_mounts}}
        scheduler = {"scheduler": {"extraVolumes": workers_extra_volumes, "extraVolumeMounts": workers_extra_volumes_mounts}}

    airflow_values_override_config = {
        "env": [{"name": "DOMINO_DEPLOY_MODE", "value": platform_config["kind"]["DOMINO_DEPLOY_MODE"]}],
        "images": {
            "useDefaultImageForMigration": False,
            "airflow": {
                "repository": domino_airflow_image,
                "tag":        domino_airflow_image_tag,
                "pullPolicy": "IfNotPresent",
            },
        },
        "extraSecrets": {
            "airflow-ssh-secret": {"data": airflow_ssh_config_parsed}
        },
        "extraEnv": extra_env_parsed,
        "config": {
            "api": {"auth_backends": "airflow.api.auth.backend.basic_auth"}
        },
        "dags": {
            "gitSync": {
                "enabled":      True,
                "wait":         10,
                "repo":         git_sync_repo,   # ← provider-aware SSH URL
                "branch":       "main",
                "subPath":      "workflows",
                "sshKeySecret": "airflow-ssh-secret",
            }
        },
        "migrateDatabaseJob": {
            "jobAnnotations": {"sidecar.istio.io/inject": "false"},
            "annotations":    {"sidecar.istio.io/inject": "false"},
        },
        "createUserJob": {
            "jobAnnotations": {"sidecar.istio.io/inject": "false"},
            "annotations":    {"sidecar.istio.io/inject": "false"},
        },
        "postgresql": {"enabled": False},
        "data":       {"metadataSecretName": "airflow-metadata-secret"},
        "webserverSecretKey": secrets.token_hex(16),
        **workers,
        **scheduler,
    }

    # Update Helm repositories
    subprocess.run(["helm", "repo", "add", "domino-iisas", DOMINO_HELM_REPOSITORY])
    subprocess.run(["helm", "repo", "add", "apache-airflow", "https://airflow.apache.org/"])
    subprocess.run(["helm", "repo", "update"])

    # Install Airflow Helm Chart
    if install_airflow:
        console.print("Installing Apache Airflow...")

        if not airflow_values_override_config["postgresql"]["enabled"]:
            console.print("Using external database for the Apache Airflow metastore.")

            airflow_db_host     = platform_config["airflow_db"].get("AIRFLOW_DB_HOST", "airflow-postgres-rw")
            airflow_db_port     = platform_config["airflow_db"].get("AIRFLOW_DB_PORT", 5432)
            airflow_db_user     = platform_config["airflow_db"].get("AIRFLOW_DB_USER", "airflow")
            airflow_db_password = platform_config["airflow_db"].get("AIRFLOW_DB_PASSWORD", "airflow")
            airflow_db_name     = platform_config["airflow_db"].get("AIRFLOW_DB_NAME", "postgres")

            if not platform_config["airflow_db"].get("AIRFLOW_DB_HOST", False):
                console.print("Installing external database for the Apache Airflow metastore...")
                result = subprocess.run([
                    "kubectl", "create", "secret", "generic",
                    f"{airflow_values_override_config['data']['metadataSecretName']}",
                    f"--from-literal=connection=postgresql://{airflow_db_user}:{airflow_db_password}@{airflow_db_host}:{airflow_db_port}/{airflow_db_name}",
                    f"--from-literal=username={airflow_db_user}",
                    f"--from-literal=password={airflow_db_password}",
                ])
                if result.returncode != 0:
                    error_message = result.stderr.strip() if result.stderr else result.stdout.strip()

                console.print("Adding CloudNativePG repository...")
                subprocess.run(["helm", "repo", "add", "cnpg", "https://cloudnative-pg.github.io/charts"])
                console.print("Updating helm repositories...")
                subprocess.run(["helm", "repo", "update", "cnpg"])
                console.print("Installing CloudNativePG operator...")
                subprocess.run(["helm", "install", "cnpg", "--namespace", "default", "--set", "config.clusterWide=false", "cnpg/cloudnative-pg", "--hide-notes"])
                console.print("Waiting for the CloudNativePG operator to be ready...")
                subprocess.run(["kubectl", "wait", "--namespace", "default", "--for", "condition=Available", "deployment/cnpg-cloudnative-pg", "--timeout=60s"])

                airflow_db_image     = platform_config["airflow_db"].get("AIRFLOW_DB_IMAGE", "ghcr.io/cloudnative-pg/postgresql")
                airflow_db_image_tag = platform_config["airflow_db"].get("AIRFLOW_DB_IMAGE_TAG", "13")
                airflow_db_manifest = [{
                    "apiVersion": "postgresql.cnpg.io/v1",
                    "kind":       "Cluster",
                    "metadata":   {"name": "airflow-postgres", "namespace": "default"},
                    "spec": {
                        "instances":  1,
                        "imageName":  f"{airflow_db_image}:{airflow_db_image_tag}",
                        "storage":    {"size": "1Gi"},
                        "bootstrap":  {
                            "initdb": {
                                "database": airflow_db_name,
                                "owner":    airflow_db_user,
                                "secret":   {"name": airflow_values_override_config["data"]["metadataSecretName"]},
                                "encoding": "UTF-8",
                            }
                        },
                    },
                }]

                with NamedTemporaryFile(suffix=".yaml", mode="w", delete_on_close=False) as fp:
                    yaml_output = "\n---\n".join(yaml.safe_dump(doc, sort_keys=False) for doc in airflow_db_manifest)
                    fp.write(yaml_output)
                    fp.close()
                    subprocess.run(["kubectl", "apply", "-f", str(fp.name)], stdout=subprocess.DEVNULL)
                    result = subprocess.run(["kubectl", "wait", "--namespace", "default", "--for", "condition=Ready", "cluster/airflow-postgres", "--timeout=60s"])
                    if result.returncode != 0:
                        error_message = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else "no details given"
                        raise Exception(f"An error occurred while installing database for Apache Airflow metastore: {error_message}")

                console.print("Database for the Apache Airflow metastore installed successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
                console.print("")

        with NamedTemporaryFile(suffix=".yaml", mode="w") as fp:
            yaml.dump(airflow_values_override_config, fp)
            subprocess.run(["helm", "install", "-f", str(fp.name), "airflow", "apache-airflow/airflow", "--version", "1.18.0"])

    # Install Domino Helm Chart
    local_domino_path = platform_config.get("dev", {}).get("DOMINO_LOCAL_DOMINO_PACKAGE")
    if platform_config.get("kind", {}).get("DOMINO_DEPLOY_MODE") == "local-k8s-dev" and local_domino_path:
        console.print("Installing Domino using local helm...")
        helm_domino_path = Path(local_domino_path).parent.parent / "helm/domino"
        with NamedTemporaryFile(suffix=".yaml", mode="w") as fp:
            yaml.dump(domino_values_override_config, fp)
            subprocess.run(["helm", "install", "-f", str(fp.name), "domino", helm_domino_path])
    else:
        console.print("Installing Domino using remote helm...")
        with TemporaryDirectory() as tmp_dir:
            console.print("Downloading Domino Helm chart...")
            subprocess.run(["helm", "pull", DOMINO_HELM_PATH, "--untar", "-d", tmp_dir])
            with NamedTemporaryFile(suffix=".yaml", mode="w") as fp:
                yaml.dump(domino_values_override_config, fp)
                console.print("Installing Domino...")
                subprocess.run(["helm", "install", "-f", str(fp.name), "domino", f"{tmp_dir}/domino"])

    # Create PVs/PVCs for local-k8s-dev mode
    if platform_config["kind"]["DOMINO_DEPLOY_MODE"] == "local-k8s-dev":
        config.load_kube_config()
        k8s_client = client.CoreV1Api()
        v1 = client.RbacAuthorizationV1Api()

        for sa_name, binding_name in [
            ("airflow-worker",    "full-access-user-clusterrolebinding-worker"),
            ("airflow-scheduler", "full-access-user-clusterrolebinding-scheduler"),
        ]:
            crb = client.V1ClusterRoleBinding(
                metadata=client.V1ObjectMeta(name=binding_name),
                subjects=[client.RbacV1Subject(kind="ServiceAccount", name=sa_name, namespace="default")],
                role_ref=client.V1RoleRef(kind="ClusterRole", name="cluster-admin", api_group="rbac.authorization.k8s.io"),
            )
            console.print(f"Creating RBAC Authorization for {sa_name} (local dev)")
            v1.create_cluster_role_binding(crb)

        for project_name in local_pieces_repositories.keys():
            console.log(f"Creating PV and PVC for {project_name}...")
            pv_name  = "pv-{}".format(str(project_name.lower().replace("_", "-")))
            pvc_name = "pvc-{}".format(str(project_name.lower().replace("_", "-")))

            pvc_exists = False
            try:
                k8s_client.read_namespaced_persistent_volume_claim(name=pvc_name, namespace="default")
                pvc_exists = True
            except client.ApiException as e:
                if e.status != 404:
                    raise e

            if not pvc_exists:
                pvc = client.V1PersistentVolumeClaim(
                    metadata=client.V1ObjectMeta(name=pvc_name),
                    spec=client.V1PersistentVolumeClaimSpec(
                        access_modes=["ReadOnlyMany"],
                        volume_name=pv_name,
                        resources=client.V1ResourceRequirements(requests={"storage": "300Mi"}),
                        storage_class_name="standard",
                    ),
                )
                k8s_client.create_namespaced_persistent_volume_claim(namespace="default", body=pvc)

            pv_exists = False
            try:
                k8s_client.read_persistent_volume(name=pv_name)
                pv_exists = True
            except client.ApiException as e:
                if e.status != 404:
                    raise e

            if not pv_exists:
                pv = client.V1PersistentVolume(
                    metadata=client.V1ObjectMeta(name=pv_name),
                    spec=client.V1PersistentVolumeSpec(
                        access_modes=["ReadWriteOnce"],
                        capacity={"storage": "1Gi"},
                        persistent_volume_reclaim_policy="Retain",
                        storage_class_name="standard",
                        host_path=client.V1HostPathVolumeSource(path=f"/pieces_repositories/{project_name}"),
                        claim_ref=client.V1ObjectReference(namespace="default", name=pvc_name, kind="PersistentVolumeClaim"),
                        node_affinity=client.V1VolumeNodeAffinity(
                            required=client.V1NodeSelector(
                                node_selector_terms=[
                                    client.V1NodeSelectorTerm(
                                        match_expressions=[
                                            client.V1NodeSelectorRequirement(
                                                key="kubernetes.io/hostname",
                                                operator="In",
                                                values=["domino-cluster-worker"],
                                            )
                                        ]
                                    )
                                ]
                            )
                        ),
                    ),
                )
                k8s_client.create_persistent_volume(body=pv)

        if platform_config["dev"].get("DOMINO_LOCAL_DOMINO_PACKAGE"):
            console.print("Creating PV's and PVC's for Local Domino Package...")
            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(name="domino-dev-volume-claim"),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteMany"],
                    volume_name="domino-dev-volume",
                    resources=client.V1ResourceRequirements(requests={"storage": "300Mi"}),
                    storage_class_name="standard",
                ),
            )
            k8s_client.create_namespaced_persistent_volume_claim(namespace="default", body=pvc)
            pv = client.V1PersistentVolume(
                metadata=client.V1ObjectMeta(name="domino-dev-volume"),
                spec=client.V1PersistentVolumeSpec(
                    storage_class_name="standard",
                    access_modes=["ReadWriteMany"],
                    capacity={"storage": "2Gi"},
                    host_path=client.V1HostPathVolumeSource(path="/domino/domino_py/src/domino"),
                    claim_ref=client.V1ObjectReference(namespace="default", name="domino-dev-volume-claim"),
                    node_affinity=client.V1VolumeNodeAffinity(
                        required=client.V1NodeSelector(
                            node_selector_terms=[
                                client.V1NodeSelectorTerm(
                                    match_expressions=[
                                        client.V1NodeSelectorRequirement(
                                            key="kubernetes.io/hostname",
                                            operator="In",
                                            values=["domino-cluster-worker"],
                                        )
                                    ]
                                )
                            ]
                        )
                    ),
                ),
            )
            k8s_client.create_persistent_volume(body=pv)

    console.print("")
    console.print("K8s resources created successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
    console.print("You can now access the Domino frontend at: http://localhost:{}/".format(platform_config["kind"].get("DOMINO_KIND_CLUSTER_HTTP_PORT")))
    console.print("Domino's REST API: http://localhost:{}/api/".format(platform_config["kind"].get("DOMINO_KIND_CLUSTER_HTTP_PORT")))
    console.print("Domino's REST API Swagger: http://localhost:{}/api/docs".format(platform_config["kind"].get("DOMINO_KIND_CLUSTER_HTTP_PORT")))
    console.print("")


###############################################################################
# DESTROY PLATFORM
###############################################################################

def destroy_platform() -> None:
    with open("config-domino-local.toml", "rb") as f:
        platform_config = tomli.load(f)
    cluster_name = platform_config["kind"]["DOMINO_KIND_CLUSTER_NAME"]
    console.print(f"Removing Kind cluster - {cluster_name}...")
    result = subprocess.run(
        ["kind", "delete", "cluster", "--name", cluster_name], capture_output=True, text=True
    )
    if result.returncode != 0:
        error_message = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise Exception(f"An error occurred while deleting Kind cluster - {cluster_name}: {error_message}")
    console.print("")
    console.print("Kind cluster removed successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
    console.print("")


###############################################################################
# RUN / STOP PLATFORM (docker compose)
###############################################################################

def run_platform_compose(
    github_token: str,       # kwarg name kept for backwards compat with CLI
    use_config_file: bool = False,
    dev: bool = False,
    debug: bool = False,
) -> None:
    console.print("Starting Domino Platform using Docker Compose.")
    console.print("Please wait, this might take a few minutes...")

    create_database = True
    os.environ["DOMINO_CREATE_DEFAULT_USER"] = "true"
    os.environ["DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN"] = github_token

    if use_config_file:
        console.print("Using config file...")
        with open("config-domino-local.toml", "rb") as f:
            platform_config = tomli.load(f)
        create_database = platform_config["domino_db"].get("DOMINO_CREATE_DATABASE", True)
        os.environ["DOMINO_CREATE_DEFAULT_USER"] = str(
            platform_config["domino_db"].get("DOMINO_CREATE_DEFAULT_USER", "true")
        ).lower()

        if not create_database:
            os.environ["DOMINO_DB_HOST"]     = platform_config["domino_db"].get("DOMINO_DB_HOST", "postgres")
            os.environ["DOMINO_DB_PORT"]     = platform_config["domino_db"].get("DOMINO_DB_PORT", 5432)
            os.environ["DOMINO_DB_USER"]     = platform_config["domino_db"].get("DOMINO_DB_USER", "postgres")
            os.environ["DOMINO_DB_PASSWORD"] = platform_config["domino_db"].get("DOMINO_DB_PASSWORD", "postgres")
            os.environ["DOMINO_DB_NAME"]     = platform_config["domino_db"].get("DOMINO_DB_NAME", "postgres")
            os.environ["NETWORK_MODE"]       = "bridge"

        if platform_config["domino_db"].get("DOMINO_DB_HOST") in ["localhost", "0.0.0.0", "127.0.0.1"]:
            os.environ["NETWORK_MODE"] = "host"

        os.environ["AIRFLOW_API_SERVER_PORT_HOST"] = str(platform_config["airflow"].get("AIRFLOW_API_SERVER_PORT_HOST", 8080))
        os.environ["AIRFLOW_UID"]                  = str(platform_config["airflow"].get("AIRFLOW_UID", 1000))
        os.environ["DOCKER_PROXY_PORT_HOST"]       = str(platform_config["docker_proxy"].get("DOCKER_PROXY_PORT_HOST", 2376))
        os.environ["DOMINO_FRONTEND_BASENAME"]     = str(platform_config["domino_frontend"].get("DOMINO_FRONTEND_BASENAME", "/"))
        os.environ["DOMINO_FRONTEND_PORT_HOST"]    = str(platform_config["domino_frontend"].get("DOMINO_FRONTEND_PORT_HOST", 3000))
        os.environ["DOMINO_REST_PORT_HOST"]        = str(platform_config["domino_rest"].get("DOMINO_REST_PORT_HOST", 8000))
        os.environ["FLOWER_PORT_HOST"]             = str(platform_config["flower"].get("FLOWER_PORT_HOST", 5555))

    # Create local directories
    local_path = Path(".").resolve()
    domino_dir = local_path / "domino_data"
    domino_dir.mkdir(parents=True, exist_ok=True)
    domino_dir.chmod(0o777)

    airflow_base = local_path / "airflow"
    for sub in ("logs", "dags", "plugins"):
        (airflow_base / sub).mkdir(parents=True, exist_ok=True)
    airflow_base.chmod(0o777)

    if create_database:
        docker_compose_path = Path(__file__).resolve().parent / "docker-compose.yaml"
    else:
        docker_compose_path = Path(__file__).resolve().parent / "docker-compose-without-database.yaml"
    shutil.copy(str(docker_compose_path), "./docker-compose.yaml")

    environment = os.environ.copy()
    environment["DOMINO_COMPOSE_DEV"] = "-dev" if dev else ""

    console.print("\nPulling Docker images...")
    pull_process = subprocess.Popen(["docker", "compose", "pull"], env=environment)
    pull_process.wait()
    if pull_process.returncode == 0:
        console.print(" \u2713 Docker images pulled successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
    else:
        console.print("Docker images pull failed.", style=f"bold {COLOR_PALETTE.get('error')}")

    console.print("\nStarting services...")
    cmd = ["docker", "compose", "up"]

    if debug:
        subprocess.Popen(cmd, env=environment)
    else:
        airflow_redis_ready = airflow_database_ready = airflow_init_ready = False
        airflow_triggerer_ready = airflow_worker_ready = airflow_api_ready = False
        airflow_scheduler_ready = domino_database_ready = False

        process = subprocess.Popen(cmd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def customize_message(line: str, **flags):
            line = re.sub(r"\s+", " ", line.lower())
            checks = [
                ("airflow_redis_ready",    lambda l: "airflow-redis" in l and "ready to accept connections tcp" in l,    "Airflow Redis"),
                ("airflow_database_ready", lambda l: "airflow-postgres" in l and ("ready" in l or "skipping" in l),      "Airflow database"),
                ("airflow_init_ready",     lambda l: "airflow-init" in l and "exited with code 0" in l,                  "Airflow pre-initialization"),
                ("airflow_triggerer_ready",lambda l: "airflow-triggerer" in l and "starting" in l,                       "Airflow triggerer"),
                ("airflow_worker_ready",   lambda l: "airflow-domino-worker" in l and "execute_command" in l,            "Airflow worker"),
                ("airflow_api_ready",      lambda l: "airflow-api-server" in l and "health" in l and "200" in l,         "Airflow API Server"),
                ("airflow_scheduler_ready",lambda l: "airflow-domino-scheduler" in l and "launched" in l,                "Airflow scheduler"),
                ("domino_database_ready",  lambda l: "domino-postgres" in l and ("ready" in l or "skipping" in l),       "Domino database"),
            ]
            for key, test, label in checks:
                if not flags.get(key) and test(line):
                    console.print(f" \u2713 {label} service started successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
                    flags[key] = True
            return flags

        def check_domino_processes():
            while True:
                try:
                    fe = requests.get("http://localhost:3000").status_code
                    re_ = requests.get("http://localhost:8000/health-check").status_code
                    if fe == 200 and re_ == 200:
                        console.print(" \u2713 Domino REST service started successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
                        console.print(" \u2713 Domino frontend service started successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
                        break
                except requests.exceptions.ConnectionError:
                    pass
                time.sleep(5)

        flags = dict(
            airflow_redis_ready=False, airflow_database_ready=False, airflow_init_ready=False,
            airflow_triggerer_ready=False, airflow_worker_ready=False, airflow_api_ready=False,
            airflow_scheduler_ready=False, domino_database_ready=False,
        )
        for line in process.stdout:
            flags = customize_message(line, **flags)
            if all(flags.values()):
                check_domino_processes()
                console.print("\n \u2713 All services for Domino Platform started successfully!", style=f"bold {COLOR_PALETTE.get('success')}")
                console.print("")
                console.print("You can now access them at")
                console.print("Domino UI:            http://{}:{}".format(os.environ.get("HOSTNAME", "localhost"), os.environ.get("DOMINO_FRONTEND_PORT_HOST", 3000)))
                console.print("Domino REST API:      http://{}:{}".format(os.environ.get("HOSTNAME", "localhost"), os.environ.get("DOMINO_REST_PORT_HOST", 8000)))
                console.print("Domino REST API Docs: http://{}:{}/docs".format(os.environ.get("HOSTNAME", "localhost"), os.environ.get("DOMINO_REST_PORT_HOST", 8000)))
                console.print("Airflow API Server:   http://{}:{}".format(os.environ.get("HOSTNAME", "localhost"), os.environ.get("AIRFLOW_API_SERVER_PORT_HOST", 8080)))
                console.print("")
                console.print("To stop the platform, run:")
                console.print("    $ domino platform stop-compose")
                console.print("")
                break


def stop_platform_compose() -> None:
    docker_compose_path = Path.cwd().resolve() / "docker-compose.yaml"
    if docker_compose_path.exists():
        environment = os.environ.copy()
        environment["DOMINO_COMPOSE_DEV"] = ""
        environment["DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN"] = ""
        environment["AIRFLOW_UID"] = ""
        subprocess.run(["docker", "compose", "down"], env=environment)

    def stop_and_remove_container(container_name):
        print(f"Stopping {container_name}...")
        p = subprocess.Popen(f"docker stop {container_name}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = p.communicate()
        if p.returncode == 0:
            print(stdout.decode())

        print(f"Removing {container_name}...")
        p = subprocess.Popen(f"docker rm {container_name}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _ = p.communicate()
        if p.returncode == 0:
            print(stdout.decode())

    try:
        container_names = [
            "domino-frontend", "domino-rest", "domino-postgres", "domino-docker-proxy",
            "airflow-domino-scheduler", "airflow-domino-worker", "airflow-api-server",
            "airflow-triggerer", "airflow-redis", "airflow-postgres",
            "airflow-flower", "airflow-cli", "airflow-init",
        ]
        with ThreadPoolExecutor() as executor:
            executor.map(stop_and_remove_container, container_names)
        console.print(
            "\n \u2713 Domino Platform stopped successfully. All containers were removed.\n",
            style=f"bold {COLOR_PALETTE.get('success')}",
        )
    except Exception as e:
        print(f"An error occurred: {e}")