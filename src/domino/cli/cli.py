from rich.console import Console
from pathlib import Path
import click
import os
import uuid
import tomli
from domino.cli.utils import pieces_repository, platform
import ast
import domino

from domino.cli.utils.constants import COLOR_PALETTE

console = Console()

# Ref: https://patorjk.com/software/taag/
# Font: standard
msg = r"""
==============================================
  ____                  _
 |  _ \  ___  _ __ ___ (_)_ __   ___
 | | | |/ _ \| '_ ` _ \| | '_ \ / _ \
 | |_| | (_) | | | | | | | | | | (_) |
 |____/ \___/|_| |_| |_|_|_| |_|\___/

=============================================="""


###############################################################################
# GIT PROVIDER TOKEN VALIDATION
###############################################################################

# Supported providers and their token format rules.
# Each entry: (prefix_or_None, min_length, max_length)
# If prefix is None, any non-empty token is accepted (generic/self-hosted PATs).
_TOKEN_RULES = {
    "github":    ("ghp_",   35, 40),   # classic PATs; fine-grained use "github_pat_"
    "gitlab":    ("glpat-", 20, 20),   # GitLab PATs (since 14.5)
    "generic":   (None,     1,  None), # self-hosted or other providers
}

SUPPORTED_PROVIDERS = list(_TOKEN_RULES.keys())


def validate_git_token(token: str, provider: str = "github") -> bool:
    """
    Validate a git provider access token.

    Args:
        token (str): The access token to validate.
        provider (str): One of 'github', 'gitlab', 'generic'.

    Returns:
        bool: True if the token looks valid for the given provider.
    """
    import re

    if not token:
        return False

    provider = provider.lower()
    if provider not in _TOKEN_RULES:
        # Unknown provider — accept any non-empty string
        return bool(token.strip())

    prefix, min_len, max_len = _TOKEN_RULES[provider]

    if prefix and not token.startswith(prefix):
        return False

    # Length check on the part after the prefix
    body = token[len(prefix):] if prefix else token
    if len(body) < min_len:
        return False
    if max_len is not None and len(body) > max_len:
        return False

    # GitLab: body must be alphanumeric + hyphens/underscores only
    if provider == "gitlab":
        if not re.fullmatch(r"[0-9a-zA-Z_-]+", body):
            return False

    # GitHub: body must be alphanumeric only
    if provider == "github":
        if not re.fullmatch(r"[0-9a-zA-Z]+", body):
            return False

    return True


# ---------------------------------------------------------------------------
# Backwards-compatible aliases (used internally and in tests)
# ---------------------------------------------------------------------------

def validate_github_token(value: str) -> bool:
    return validate_git_token(value, provider="github")


def validate_gitlab_token(value: str) -> bool:
    return validate_git_token(value, provider="gitlab")


###############################################################################
# ENVIRONMENT HELPERS  (provider-agnostic naming)
###############################################################################

# Env var names are now provider-agnostic ("GIT_" prefix).
# Legacy "GITHUB_" / "DOMINO_GITHUB_" names are checked as fallbacks so
# existing deployments keep working without any changes.

def _env(*keys, default=None):
    """Return the first non-empty value found among the given env var names."""
    for key in keys:
        val = os.environ.get(key)
        if val:
            return val
    return default


def get_cluster_name_from_env():
    return _env("DOMINO_KIND_CLUSTER_NAME", default="domino-cluster")


def get_cluster_http_port_from_env():
    return _env("DOMINO_KIND_CLUSTER_HTTP_PORT", default=80)


def get_cluster_https_port_from_env():
    return int(_env("DOMINO_KIND_CLUSTER_HTTPS_PORT", default=443))


def get_workflows_ssh_private_key_from_env():
    return _env(
        "DOMINO_GIT_WORKFLOWS_SSH_PRIVATE_KEY",
        "DOMINO_GIT_WORKFLOWS_SSH_PRIVATE_KEY",
        default="",
    )


def get_git_token_pieces_from_env():
    return _env(
        "DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN",
        default=None,
    )


def get_git_token_workflows_from_env():
    return _env(
        "DOMINO_GIT_ACCESS_TOKEN_WORKFLOWS",
        "DOMINO_GIT_ACCESS_TOKEN_WORKFLOWS",
        default=None,
    )


def get_workflows_repository_from_env():
    return _env(
        "DOMINO_GIT_WORKFLOWS_REPOSITORY",
        "DOMINO_GIT_WORKFLOWS_REPOSITORY",
        default=None,
    )


def get_registry_token_from_env():
    return _env(
        "CONTAINER_REGISTRY_PASSWORD",
        "CONTAINER_REGISTRY_PASSWORD",
        default="",
    )


def get_registry_username_from_env():
    return _env(
        "CONTAINER_REGISTRY_USERNAME",
        "CONTAINER_REGISTRY_USERNAME",
        default="",
    )


def get_git_provider_from_env():
    return _env("DOMINO_GIT_PROVIDER", default="github")


def get_git_token_pieces_from_config_or_env():
    if Path("config-domino-local.toml").is_file():
        with open("config-domino-local.toml", "rb") as f:
            config = tomli.load(f)
        git_section = config.get("git") or config.get("github") or {}
        token = git_section.get("DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN")
        if token:
            return token
    return get_git_token_pieces_from_env()


###############################################################################
# DOMINO PLATFORM
###############################################################################

@click.command()
@click.option(
    "--cluster-name",
    prompt="Local cluster name",
    default=get_cluster_name_from_env,
    help="Define the name for the local k8s cluster.",
)
@click.option(
    "--http-port",
    prompt="Local cluster HTTP port",
    default=get_cluster_http_port_from_env,
    help="Define the HTTP port for the local k8s cluster.",
)
@click.option(
    "--https-port",
    prompt="Local cluster HTTPS port",
    default=get_cluster_https_port_from_env,
    help="Define the HTTPS port for the local k8s cluster.",
)
@click.option(
    "--git-provider",
    prompt="Git provider (github | gitlab | generic)",
    default=get_git_provider_from_env,
    type=click.Choice(SUPPORTED_PROVIDERS, case_sensitive=False),
    help="Git provider for workflows and pieces repositories.",
)
@click.option(
    "--workflows-repository",
    prompt="Workflows repository",
    default=get_workflows_repository_from_env,
    help="Git repository where the Domino workflows will be stored.",
)
@click.option(
    "--workflows-ssh-private-key",
    prompt=(
        "SSH private key for Workflows repository. "
        "If none, a new key pair will be created."
    ),
    default=get_workflows_ssh_private_key_from_env,
    help=(
        "SSH private key for GitSync read/write operations on the Workflows repository. "
        "The corresponding public key must be added to the repository deploy keys."
    ),
)
@click.option(
    "--default-pieces-repository-token",
    prompt="Access token for Pieces repository",
    default=get_git_token_pieces_from_env,
    help="Access token for read operations on Pieces repositories.",
)
@click.option(
    "--workflows-token",
    prompt="Access token for Workflows repository",
    default=get_git_token_workflows_from_env,
    help="Access token for read/write operations on the Workflows repository.",
)
@click.option(
    "--deploy-mode",
    prompt="Deploy mode",
    default="local-k8s",
    help='Deploy mode — either "local-k8s" or "remote".',
)
@click.option(
    "--local-pieces-repository-path",
    prompt='Local pieces repository paths. Example: ["/path/to/repo1", "/path/to/repo2"]',
    default=[],
    help="List of local pieces repository paths.",
)
@click.option(
    "--local-domino-path",
    prompt="Local Domino path",
    default="",
    help="Local Domino path. Used only in dev mode for hot reloading.",
)
@click.option(
    "--local-rest-image",
    prompt="Local Domino REST image (local-k8s-dev mode only)",
    default="",
    help="Local Domino REST image to use in local-k8s-dev deploy mode.",
)
@click.option(
    "--local-frontend-image",
    prompt="Local Domino Frontend image (local-k8s-dev mode only)",
    default="",
    help="Local Domino Frontend image to use in local-k8s-dev deploy mode.",
)
@click.option(
    "--local-airflow-image",
    prompt="Local Domino Airflow image (local-k8s-dev mode only)",
    default="",
    help="Local Domino Airflow image to use in local-k8s-dev deploy mode.",
)
def cli_prepare_platform(
    cluster_name,
    http_port,
    https_port,
    git_provider,
    workflows_repository,
    workflows_ssh_private_key,
    default_pieces_repository_token,
    workflows_token,
    deploy_mode,
    local_pieces_repository_path,
    local_domino_path,
    local_rest_image,
    local_frontend_image,
    local_airflow_image,
):
    """Prepare local folder for running a Domino platform."""
    platform.prepare_platform(
        cluster_name=cluster_name,
        http_port=int(http_port),
        https_port=int(https_port),
        git_provider=git_provider,
        workflows_repository=workflows_repository,
        github_workflows_ssh_private_key=workflows_ssh_private_key,   # keep kwarg name for platform compat
        github_default_pieces_repository_token=default_pieces_repository_token,
        github_workflows_token=workflows_token,
        deploy_mode=deploy_mode,
        local_pieces_repository_path=ast.literal_eval(local_pieces_repository_path),
        local_domino_path=local_domino_path,
        local_rest_image=local_rest_image,
        local_frontend_image=local_frontend_image,
        local_airflow_image=local_airflow_image,
    )


@click.command()
@click.option(
    "--install-airflow",
    default=True,
    help="Install Airflow services.",
)
@click.option(
    "--use-gpu",
    is_flag=True,
    help="Allow the platform to use GPUs. Installs NVIDIA plugins.",
    default=False,
)
def cli_create_platform(install_airflow, use_gpu):
    """Create cluster, install services and run Domino platform."""
    platform.create_platform(install_airflow, use_gpu)


@click.command()
def cli_destroy_platform():
    """Destroy Kind cluster."""
    platform.destroy_platform()


@click.command()
@click.option(
    "--use-config-file",
    is_flag=True,
    help="Use config file to run platform.",
    default=False,
)
@click.option(
    "--dev",
    is_flag=True,
    help="Run platform in dev mode.",
    default=False,
)
@click.option(
    "--debug",
    is_flag=True,
    help="Print docker compose messages on terminal.",
    default=False,
)
@click.option(
    "--stop",
    is_flag=True,
    help="Stop and remove containers.",
    default=False,
)
@click.option(
    "--git-token",
    prompt="Access token for default pieces repositories",
    help="Access token for default pieces repositories.",
    default=get_git_token_pieces_from_config_or_env,
)
def cli_run_platform_compose(use_config_file, dev, debug, stop, git_token):
    """Run Domino platform locally with docker compose. Do NOT use in production."""
    if stop:
        platform.stop_platform_compose()
    else:
        platform.run_platform_compose(
            github_token=git_token,   # keep kwarg name for platform compat
            use_config_file=use_config_file,
            dev=dev,
            debug=debug,
        )


@click.command()
def cli_stop_platform_compose():
    """Stop Domino platform locally with docker compose. Do NOT use in production."""
    platform.stop_platform_compose()


@click.group()
@click.pass_context
def cli_platform(ctx):
    """Domino platform actions."""
    if ctx.invoked_subcommand == "prepare":
        console.print("Let's get you started configuring a local Domino platform:")
    elif ctx.invoked_subcommand == "create":
        console.print("Your local Domino platform is being created. This might take a while...")


cli_platform.add_command(cli_prepare_platform, name="prepare")
cli_platform.add_command(cli_create_platform, name="create")
cli_platform.add_command(cli_destroy_platform, name="destroy")
cli_platform.add_command(cli_run_platform_compose, name="run-compose")
cli_platform.add_command(cli_stop_platform_compose, name="stop-compose")


###############################################################################
# PIECES REPOSITORY
###############################################################################

def generate_random_repo_name():
    return f"new_repository_{str(uuid.uuid4())[0:8]}"


@click.command()
@click.option("--name", default="ExamplePiece", help="Piece name.")
@click.option("--repository-path", default=None, help="Path of piece repository.")
def cli_create_piece(name: str, repository_path: str = None):
    """Create piece."""
    try:
        if repository_path is not None:
            pieces_repository.create_piece(name, f"{repository_path}/pieces")
        elif not (Path.cwd() / "pieces").is_dir():
            if Path.cwd().name == "pieces":
                pieces_repository.create_piece(name, str(Path.cwd()))
            else:
                raise FileNotFoundError("No pieces directory found.")
        else:
            pieces_repository.create_piece(name, f"{Path.cwd()}/pieces")
    except FileNotFoundError as err:
        console.print(err, style=f"bold {COLOR_PALETTE.get('error')}")


@click.group()
def cli_pieces():
    """Manage pieces in a repository."""
    pass


cli_pieces.add_command(cli_create_piece, name="create")


@click.command()
@click.option(
    "--name",
    prompt="Repository's name",
    default=generate_random_repo_name,
    help="Repository's name.",
)
@click.option(
    "--container-registry",
    prompt="Container registry name",
    default="",
    help="Container registry name (e.g. ghcr.io/myorg or registry.gitlab.com/myorg).",
)
def cli_create_piece_repository(name, container_registry):
    """Create a basic Pieces repository with placeholder files."""
    pieces_repository.create_pieces_repository(
        repository_name=name, container_registry=container_registry
    )


@click.command()
@click.option(
    "--build-images",
    is_flag=True,
    prompt="Build Docker images?",
    expose_value=True,
    default=False,
    help="If set, builds Docker images.",
)
@click.option(
    "--source-url",
    prompt="URL of source repository",
    default="",
    help="The base URL for this Pieces repository.",
)
@click.option(
    "--tag-overwrite",
    default="",
    help="Overwrite tag for release.",
)
@click.option(
    "--dev",
    is_flag=True,
    default=False,
    help="Build pieces images using development base piece image.",
)
def cli_organize_pieces_repository(build_images: bool, source_url: str, tag_overwrite: str, dev: bool):
    """Organize Pieces repository."""
    pieces_repository.organize_pieces_repository(build_images, source_url, tag_overwrite, dev)


@click.command()
@click.option(
    "--registry-token",
    prompt="Container registry token",
    default=get_registry_token_from_env,
    help="Access token (password) for the container registry where images will be published.",
)
@click.option(
    "--registry-username",
    default=get_registry_username_from_env,
    help="Username for the container registry (read from CONTAINER_REGISTRY_USERNAME if not set).",
)
def cli_publish_images(registry_token: str, registry_username: str):
    """Publish images to container registry from mapping."""
    if registry_token:
        os.environ["CONTAINER_REGISTRY_PASSWORD"] = registry_token
    if registry_username:
        os.environ["CONTAINER_REGISTRY_USERNAME"] = registry_username
    console.print("Using registry token to publish images")
    pieces_repository.publish_docker_images()


@click.command()
@click.option("--tag-name", default="", help="Tag name.")
@click.option("--commit-sha", default="", help="Commit SHA.")
@click.option(
    "--git-provider",
    default=get_git_provider_from_env,
    type=click.Choice(SUPPORTED_PROVIDERS, case_sensitive=False),
    help="Git provider to use for creating the release.",
)
def cli_create_release(tag_name: str, commit_sha: str, git_provider: str):
    """
    Get release version for the Pieces repository in CI stdout format.
    Used by CI pipelines to set the release version.

    Requires the following env vars depending on provider:
      GitHub:    GITHUB_TOKEN, GITHUB_REPOSITORY
      GitLab:    GITLAB_TOKEN, GITLAB_REPOSITORY (or CI_PROJECT_PATH)
    """
    pieces_repository.create_release(tag_name=tag_name, commit_sha=commit_sha)


@click.command()
@click.option("--tag-name", help="Tag name.")
@click.option(
    "--git-provider",
    default=get_git_provider_from_env,
    type=click.Choice(SUPPORTED_PROVIDERS, case_sensitive=False),
    help="Git provider to use for deleting the release.",
)
def cli_delete_release(tag_name: str, git_provider: str):
    """
    Delete a release with the given tag name via CI pipeline.

    Requires the following env vars depending on provider:
      GitHub:    GITHUB_TOKEN, GITHUB_REPOSITORY
      GitLab:    GITLAB_TOKEN, GITLAB_REPOSITORY (or CI_PROJECT_PATH)
    """
    pieces_repository.delete_release(tag_name=tag_name)


@click.group()
@click.pass_context
def cli_piece_repository(ctx):
    """Pieces repository actions."""
    if ctx.invoked_subcommand == "organize":
        console.print(f"Organizing Pieces Repository at: {Path('.').resolve()}")
    elif ctx.invoked_subcommand == "create":
        pass


cli_piece_repository.add_command(cli_organize_pieces_repository, name="organize")
cli_piece_repository.add_command(cli_create_release, name="release")
cli_piece_repository.add_command(cli_delete_release, name="delete-release")
cli_piece_repository.add_command(cli_publish_images, name="publish-images")


###############################################################################
# RUN PIECE
###############################################################################

@click.command()
def cli_run_piece_k8s():
    """Run Piece on Kubernetes Pod."""
    from domino.scripts.run_piece_docker import run_piece as run_piece_in_docker
    console.print("Running Piece inside K8s pod...")
    run_piece_in_docker()


@click.command()
def cli_run_piece_docker():
    """Run Piece on Docker container."""
    from domino.scripts.run_piece_docker import run_piece as run_piece_in_docker
    console.print("Running Piece inside Docker container...")
    run_piece_in_docker()


###############################################################################
# PARENT GROUP
###############################################################################

@click.group()
@click.version_option(domino.__version__)
@click.pass_context
def cli(ctx):
    console.print("")
    console.print("Welcome to Domino! :red_heart-emoji:")
    console.print("")


cli.add_command(cli_platform, name="platform")
cli.add_command(cli_piece_repository, name="piece-repository")
cli.add_command(cli_pieces, name="pieces")
cli.add_command(cli_run_piece_k8s, name="run-piece-k8s")
cli.add_command(cli_run_piece_docker, name="run-piece-docker")


if __name__ == "__main__":
    cli()