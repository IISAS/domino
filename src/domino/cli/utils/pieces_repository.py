import tomli
import tomli_w
import json
import jsonschema
import subprocess
import copy
import uuid
import os
import re
import shutil
import time
from pathlib import Path
from rich.console import Console
from typing import Union

from domino.cli.utils.constants import COLOR_PALETTE
from domino.utils import dict_deep_update
from domino.exceptions.exceptions import ValidationError
from domino.cli.utils import templates


console = Console()


class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


CONFIG_REQUIRED_FIELDS = {}


###############################################################################
# GIT PROVIDER ABSTRACTION
###############################################################################

SUPPORTED_PROVIDERS = ("github", "gitlab", "generic")

# Maps each provider to the env vars it uses for token and repository identity.
_PROVIDER_ENV = {
    "github": {
        "token":      ["GITHUB_TOKEN"],
        "repository": ["GITHUB_REPOSITORY"],
    },
    "gitlab": {
        "token":      ["GITLAB_TOKEN", "CI_JOB_TOKEN"],
        "repository": ["GITLAB_REPOSITORY", "CI_PROJECT_PATH"],
    },
    "generic": {
        "token":      ["GIT_TOKEN"],
        "repository": ["GIT_REPOSITORY"],
    },
}


def _get_provider() -> str:
    """Return the active git provider from env, defaulting to 'github'."""
    return os.environ.get("DOMINO_GIT_PROVIDER", "github").lower()


def _env_token(provider: str) -> str | None:
    """Return the first non-empty token env var for the given provider."""
    for key in _PROVIDER_ENV.get(provider, {}).get("token", []):
        val = os.environ.get(key)
        if val:
            return val
    return None


def _env_repository(provider: str) -> str | None:
    """Return the first non-empty repository env var for the given provider."""
    for key in _PROVIDER_ENV.get(provider, {}).get("repository", []):
        val = os.environ.get(key)
        if val:
            return val
    return None


def _make_git_client(provider: str, token: str):
    """
    Instantiate and return the appropriate REST client for the given provider.
    Raises ImportError / ValueError for unsupported providers.
    """
    if provider == "github":
        from domino.client.github_rest_client import GithubRestClient
        return GithubRestClient(token=token)
    if provider == "gitlab":
        from domino.client.gitlab_rest_client import GitlabRestClient
        return GitlabRestClient(token=token)
    raise ValueError(
        f"Unsupported git provider '{provider}'. "
        f"Choose one of: {', '.join(SUPPORTED_PROVIDERS)}"
    )


###############################################################################
# TOKEN VALIDATION
###############################################################################

def _validate_token(token: str, provider: str) -> bool:
    """
    Validate an access token for the given provider.

    Token format rules per provider:
      github    — prefix 'ghp_'       + 35-40 alphanumeric chars
      gitlab    — prefix 'glpat-'     + exactly 20 alphanumeric/hyphen/underscore chars
      generic   — any non-empty string
    """
    if not token:
        return False

    rules = {
        "github":    (r"ghp_[0-9a-zA-Z]{35,40}",    True),
        "gitlab":    (r"glpat-[0-9a-zA-Z_-]{20}",   True),
        "generic":   (r".+",                       False),
    }

    pattern_str, use_fullmatch = rules.get(provider, (r".+", False))
    fn = re.fullmatch if use_fullmatch else re.match
    return bool(fn(pattern_str, token))


# ---------------------------------------------------------------------------
# Backwards-compatible public aliases
# ---------------------------------------------------------------------------

def validate_github_token(token: str) -> bool:
    return _validate_token(token, "github")


def validate_gitlab_token(token: str) -> bool:
    return _validate_token(token, "gitlab")


###############################################################################
# ENV VAR VALIDATION
###############################################################################

def _build_env_validators() -> dict:
    """
    Build REQUIRED_ENV_VARS_VALIDATORS dynamically based on the active provider.
    Token env var names and validator functions are resolved at runtime so the
    same code works for GitHub, GitLab, or a generic provider.
    """
    provider = _get_provider()
    token_vars = _PROVIDER_ENV.get(provider, _PROVIDER_ENV["generic"])["token"]
    primary_token_var = token_vars[0]

    return {
        "DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN": {
            "depends": lambda arg: arg.get("OPERATORS_REPOSITORY_SOURCE") == provider,
            "validator_func": lambda t: _validate_token(t, provider),
        },
        primary_token_var: {
            "depends": lambda arg: arg.get("OPERATORS_REPOSITORY_SOURCE") == provider,
            "validator_func": lambda t: _validate_token(t, provider),
        },
    }


# Keep a module-level reference for code that imports it directly, but always
# re-build inside validate_env_vars() so the provider can be set at runtime.
REQUIRED_ENV_VARS_VALIDATORS = _build_env_validators()


###############################################################################
# EXISTING HELPERS (unchanged logic, provider-agnostic)
###############################################################################

def set_config_as_env(key: str, value: Union[str, int, float]) -> None:
    key = str(key).strip().upper()
    os.environ[key] = str(value)


def validate_repository_name(name: str) -> bool:
    regex = r"^[A-Za-z0-9_]*$"
    pattern = re.compile(regex)
    return bool(pattern.match(name))


def validate_env_vars() -> None:
    """
    Validate user environment variables.
    Token env var names and format rules are resolved from the active provider.
    """
    uid = subprocess.run(["id", "-u"], capture_output=True, text=True)
    set_config_as_env("AIRFLOW_UID", int(uid.stdout))

    validators = _build_env_validators()

    for var, validator in validators.items():
        if "depends" in validator:
            should_exist = validator["depends"](CONFIG_REQUIRED_FIELDS)
        if not should_exist:
            continue
        env_var = os.environ.get(var, None)
        if env_var:
            continue
        console.print(f"{var} is not defined", style=f"bold {COLOR_PALETTE.get('warning')}")
        new_var = input(f"Enter the {var} value: ")
        while not validator["validator_func"](new_var):
            new_var = input(f"Wrong {var} format. Enter a new value: ")
        os.environ[var] = new_var


def validate_config(config_dict: dict) -> None:
    required_fields = ["REGISTRY_NAME", "REPOSITORY_NAME", "VERSION"]
    sections = config_dict.keys()
    for section in sections:
        for key, value in config_dict.get(section).items():
            if key in required_fields:
                required_fields.remove(key)
                set_config_as_env(key, value)
    if len(required_fields) > 0:
        console.print(
            "Missing required fields: {}".format(required_fields),
            style=f"bold {COLOR_PALETTE.get('error')}",
        )


def validate_repository_structure() -> None:
    organized_domino_path = Path(".") / ".domino/"
    if not organized_domino_path.is_dir():
        organized_domino_path.mkdir(parents=True, exist_ok=True)

    config_path = Path(".") / "config.toml"
    if not config_path.is_file():
        console.print("Missing config.toml file", style=f"bold {COLOR_PALETTE.get('error')}")
        raise FileNotFoundError("Missing config.toml file")

    with open(config_path, "rb") as f:
        config_dict = tomli.load(f)

    validate_config(config_dict)
    validate_env_vars()

    pieces_repository = Path(".")
    if not pieces_repository.is_dir():
        console.print("Pieces repository path does not exist", style=f"bold {COLOR_PALETTE.get('error')}")
        raise Exception("Pieces repository path does not exist")

    if not (pieces_repository / "pieces").is_dir():
        console.print("Pieces directory does not exist", style=f"bold {COLOR_PALETTE.get('error')}")
        raise Exception("Pieces directory does not exist")

    if not (pieces_repository / "dependencies").is_dir():
        console.print("Dependencies directory does not exist", style=f"bold {COLOR_PALETTE.get('error')}")
        raise Exception("Dependencies directory does not exist")


def validate_pieces_folders() -> None:
    from domino.schemas import PieceMetadata

    pieces_path = Path(".") / "pieces"
    dependencies_path = Path(".") / "dependencies"
    dependencies_files = [f.name for f in dependencies_path.glob("*")]
    name_errors = list()
    missing_file_errors = list()
    missing_dependencies_errors = list()
    for op_dir in pieces_path.glob("*Piece"):
        if op_dir.is_dir():
            files_names = [f.name for f in op_dir.glob("*")]
            if "models.py" not in files_names:
                missing_file_errors.append(f"missing 'models.py' for {op_dir.name}")
            if "piece.py" not in files_names:
                missing_file_errors.append(f"missing 'piece.py' for {op_dir.name}")
            if len(missing_file_errors) > 0:
                raise Exception("\n".join(missing_file_errors))

            if (op_dir / "metadata.json").is_file():
                with open(str(op_dir / "metadata.json"), "r") as f:
                    metadata = json.load(f)
                jsonschema.validate(instance=metadata, schema=PieceMetadata.model_json_schema())

                if metadata.get("name", None) and not metadata["name"] == op_dir.name:
                    name_errors.append(op_dir.name)

                if metadata.get("dependency", None):
                    req_file = metadata["dependency"].get("requirements_file", None)
                    if req_file and req_file != "default" and req_file not in dependencies_files:
                        missing_dependencies_errors.append(
                            f"missing dependency file {req_file} defined for {op_dir.name}"
                        )
                    dock_file = metadata["dependency"].get("dockerfile", None)
                    if dock_file and dock_file != "default" and dock_file not in dependencies_files:
                        missing_dependencies_errors.append(
                            f"missing dependency file {dock_file} defined for {op_dir.name}"
                        )

    if len(name_errors) > 0:
        raise Exception(f"The following Pieces have inconsistent names: {', '.join(name_errors)}")
    if len(missing_dependencies_errors) > 0:
        raise Exception("\n" + "\n".join(missing_dependencies_errors))


def _validate_piece_name(name: str):
    if len(name) == 0:
        raise ValidationError("Piece name must have at least one character.")
    regex = r"^[A-Za-z_][A-Za-z0-9_]*Piece$"
    pattern = re.compile(regex)
    if not pattern.match(name):
        raise ValidationError(
            f"{name} is not a valid piece name. "
            "Piece name must be a valid Python class name and must end with 'Piece'."
        )


def create_piece(name: str, piece_repository: str):
    try:
        _validate_piece_name(name)
        piece_dir = os.path.join(piece_repository, name)
        os.mkdir(piece_dir)

        with open(f"{piece_dir}/piece.py", "x") as f:
            f.write(templates.piece_function(name))
        with open(f"{piece_dir}/models.py", "x") as f:
            f.write(templates.piece_models(name))
        with open(f"{piece_dir}/test_{name}.py", "x") as f:
            f.write(templates.piece_test(name))
        with open(f"{piece_dir}/metadata.json", "x") as f:
            json.dump(templates.piece_metadata(name), f, indent=4)

        console.print(
            f"{name} is created in {piece_repository}.",
            style=f"bold {COLOR_PALETTE.get('success')}",
        )
    except ValidationError as err:
        console.print(f"{err}", style=f"bold {COLOR_PALETTE.get('error')}")
    except OSError as err:
        if err.errno == 17:
            console.print(
                f"{name} already exists in {piece_repository}.",
                style=f"bold {COLOR_PALETTE.get('error')}",
            )
        elif err.errno == 2:
            console.print(
                f"{piece_repository} is not a valid repository path.",
                style=f"bold {COLOR_PALETTE.get('error')}",
            )
        else:
            console.print(f"{err}", style=f"bold {COLOR_PALETTE.get('error')}")


def create_pieces_repository(repository_name: str, container_registry: str) -> None:
    while not validate_repository_name(repository_name):
        repository_name = (
            input(
                "\nInvalid repository name. Should have only numbers, letters and underscores.\n"
                "Enter a new repository name: "
            )
            or f"new_repository_{str(uuid.uuid4())[0:8]}"
        )
    cwd = Path.cwd()
    repository_folder = cwd / repository_name
    if repository_folder.is_dir():
        raise Exception("Repository folder already exists")
    console.print(f"Cloning template Pieces repository at: {repository_folder}")
    subprocess.run(
        [
            "git", "clone",
            "https://github.com/Tauffer-Consulting/domino_pieces_repository_template.git",
            repository_name,
        ],
        capture_output=True,
        text=True,
    )
    shutil.rmtree(f"{repository_name}/.git")

    with open(f"{repository_name}/config.toml", "rb") as f:
        repo_config = tomli.load(f)

    repo_config["repository"]["REPOSITORY_NAME"] = repository_name
    repo_config["repository"]["REGISTRY_NAME"] = (
        container_registry if container_registry else "enter-your-registry-name-here"
    )

    with open(f"{repository_name}/config.toml", "wb") as f:
        tomli_w.dump(repo_config, f)

    console.print(
        f"Pieces repository successfully created at: {repository_folder}",
        style=f"bold {COLOR_PALETTE.get('success')}",
    )
    console.print("")


def create_compiled_pieces_metadata(source_url: str | None = None) -> None:
    from domino.scripts.load_piece import load_piece_models_from_path
    from domino.utils.metadata_default import metadata_default

    pieces_path = Path(".") / "pieces"
    compiled_metadata = dict()
    for op_dir in pieces_path.glob("*Piece"):
        if op_dir.is_dir():
            piece_name = op_dir.name
            metadata = copy.deepcopy(metadata_default)
            if (op_dir / "metadata.json").is_file():
                with open(str(op_dir / "metadata.json"), "r") as f:
                    metadata_op = json.load(f)
                metadata_op["name"] = metadata_op.get("name", piece_name)
                dict_deep_update(metadata, metadata_op)
            else:
                metadata["name"] = piece_name

            input_model_class, output_model_class, secrets_model_class = load_piece_models_from_path(
                pieces_folder_path=str(pieces_path),
                piece_name=op_dir.name,
            )
            metadata["input_schema"] = input_model_class.model_json_schema()
            metadata["output_schema"] = output_model_class.model_json_schema()
            metadata["secrets_schema"] = (
                secrets_model_class.model_json_schema() if secrets_model_class else None
            )

            metadata["source_url"] = None
            if source_url and len(source_url) > 0:
                metadata["source_url"] = source_url + f"/tree/main/pieces/{piece_name}"

            compiled_metadata[piece_name] = metadata

    organized_domino_path = Path(".") / ".domino/"
    with open(str(organized_domino_path / "compiled_metadata.json"), "w") as f:
        json.dump(compiled_metadata, f, indent=4)


def create_dependencies_map(save_map_as_file: bool = True) -> None:
    organized_domino_path = Path(".") / ".domino/"
    with open(organized_domino_path / "compiled_metadata.json", "r") as f:
        compiled_metadata = json.load(f)

    pieces_images_map = {}
    for op_i, (piece_name, piece_metadata) in enumerate(compiled_metadata.items()):
        if piece_metadata.get("secrets_schema"):
            piece_secrets = set(piece_metadata.get("secrets_schema")["properties"].keys())
        else:
            piece_secrets = set()

        if op_i == 0:
            pieces_images_map = {
                "group0": {
                    "dependency": piece_metadata["dependency"],
                    "pieces": [piece_name],
                    "secrets": piece_secrets,
                }
            }
        else:
            existing_keys = pieces_images_map.keys()
            skip_new_image = False
            for dep_key in existing_keys:
                if all(
                    piece_metadata["dependency"][k] == pieces_images_map[dep_key]["dependency"][k]
                    for k in piece_metadata["dependency"].keys()
                ):
                    pieces_images_map[dep_key]["pieces"].append(piece_name)
                    pieces_images_map[dep_key]["secrets"].update(piece_secrets)
                    skip_new_image = True
                    continue
            if not skip_new_image:
                pieces_images_map[f"group{len(existing_keys)}"] = {
                    "dependency": piece_metadata["dependency"],
                    "pieces": [piece_name],
                    "secrets": piece_secrets,
                }

    if not pieces_images_map:
        raise ValueError("No pieces found in the Pieces Repository")

    if save_map_as_file:
        map_file_path = organized_domino_path / "dependencies_map.json"
        with open(map_file_path, "w") as outfile:
            json.dump(pieces_images_map, outfile, indent=4, cls=SetEncoder)


def build_docker_images(tag_overwrite: str | None = None, dev: bool = False) -> None:
    from domino.scripts.build_docker_images_pieces import build_images_from_pieces_repository

    console.print("Building Docker images and generating map file...")
    return build_images_from_pieces_repository(tag_overwrite=tag_overwrite, dev=dev)


def publish_docker_images() -> None:
    from domino.scripts.build_docker_images_pieces import publish_image

    pieces_images_map = json.loads(os.environ.get("PIECES_IMAGES_MAP", "{}"))
    if not pieces_images_map:
        raise ValueError("No images found to publish.")

    console.print("Publishing Docker images...")
    all_images = set(pieces_images_map.values())
    for image in all_images:
        console.print(f"Publishing image {image}...")
        publish_image(source_image_name=image)


def validate_repo_name(repo_name: str) -> None:
    if any(a.isspace() for a in repo_name):
        raise ValueError("Repository name should not contain blank spaces")
    forbidden = set('!@#$%^&*()+={}`[]:;\'"<>?/\\|~')
    if any(a in forbidden for a in repo_name):
        raise ValueError("Repository name should not contain special characters")


def organize_pieces_repository(
    build_images: bool,
    source_url: str,
    tag_overwrite: str | None = None,
    dev: bool = False,
) -> None:
    console.print("Validating repository structure and files...")
    validate_repository_structure()
    validate_pieces_folders()
    console.print("Validation successful!", style=f"bold {COLOR_PALETTE.get('success')}")

    with open("config.toml", "rb") as f:
        repo_config = tomli.load(f)

    repo_name = repo_config["repository"]["REPOSITORY_NAME"]
    validate_repo_name(repo_name)

    if tag_overwrite:
        repo_config["repository"]["VERSION"] = tag_overwrite

    create_compiled_pieces_metadata(source_url=source_url)
    create_dependencies_map(save_map_as_file=True)
    console.print(
        "Metadata and dependencies organized successfully!",
        style=f"bold {COLOR_PALETTE.get('success')}",
    )

    if build_images:
        updated_dependencies_map = build_docker_images(tag_overwrite=tag_overwrite, dev=dev)
        map_file_path = Path(".") / ".domino/dependencies_map.json"
        with open(map_file_path, "w") as outfile:
            json.dump(updated_dependencies_map, outfile, indent=4)


###############################################################################
# RELEASE MANAGEMENT  (provider-agnostic)
###############################################################################

def _resolve_client_and_repo(provider: str | None = None):
    """
    Resolve the git provider, instantiate the right REST client, and return
    both along with the repository identifier string.

    Raises ValueError for missing token or repository env vars.
    """
    if provider is None:
        provider = _get_provider()

    token = _env_token(provider)
    if not token:
        token_vars = _PROVIDER_ENV.get(provider, {}).get("token", ["GIT_TOKEN"])
        raise ValueError(
            f"No token found for provider '{provider}'. "
            f"Set one of: {', '.join(token_vars)}"
        )

    repository = _env_repository(provider)
    if not repository:
        repo_vars = _PROVIDER_ENV.get(provider, {}).get("repository", ["GIT_REPOSITORY"])
        raise ValueError(
            f"No repository found for provider '{provider}'. "
            f"Set one of: {', '.join(repo_vars)}"
        )

    client = _make_git_client(provider, token)
    return client, repository


def create_release(tag_name: str | None = None, commit_sha: str | None = None):
    """
    Create a new release and tag in the repository for the latest commit.
    Works with GitHub, GitLab, or any generic provider by reading
    DOMINO_GIT_PROVIDER (defaults to 'github').
    """
    provider = _get_provider()
    client, repository = _resolve_client_and_repo(provider)

    with open("config.toml", "rb") as f:
        repo_config = tomli.load(f)

    version = repo_config.get("repository", {}).get("VERSION", None)
    if not version:
        raise ValueError("VERSION not found in config.toml")

    if tag_name:
        version = tag_name

    tag = client.get_tag(repo_name=repository, tag_name=version)
    if tag:
        raise ValueError(f"Tag {version} already exists")

    if not commit_sha:
        latest_commit = client.get_commits(repo_name=repository, number_of_commits=1)[0]
        # Normalise: GitHub returns objects with .sha; GitLab returns dicts or objects with .id
        commit_sha = getattr(latest_commit, "sha", None) or getattr(latest_commit, "id", None)
    if not commit_sha:
        raise ValueError("Commit SHA not found")

    release = client.create_release(
        repo_name=repository,
        version=version,
        tag_message=f"Release {version}",
        release_message=f"Release {version}",
        target_commit_sha=commit_sha,
    )
    console.print(
        f"Release {version} created successfully!",
        style=f"bold {COLOR_PALETTE.get('success')}",
    )
    return release


def delete_release(tag_name: str):
    """
    Delete a release (and its tag) from the repository.
    Works with GitHub, GitLab, or any generic provider by reading
    DOMINO_GIT_PROVIDER (defaults to 'github').
    """
    provider = _get_provider()
    client, repository = _resolve_client_and_repo(provider)

    tag = client.get_tag(repo_name=repository, tag_name=tag_name)
    if not tag:
        console.print(
            f"Release {tag_name} not found. Skipping deletion.",
            style=f"bold {COLOR_PALETTE.get('warning')}",
        )
        return

    client.delete_release_by_tag(repo_name=repository, tag_name=tag_name)
    client.delete_tag(repo_name=repository, tag_name=tag_name)
    console.print(f"Attempting to delete release {tag_name}...", style="bold")

    timeout = 30
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not client.get_tag(repo_name=repository, tag_name=tag_name):
            console.print(
                f"Release {tag_name} deleted successfully!",
                style=f"bold {COLOR_PALETTE.get('success')}",
            )
            return
        time.sleep(5)

    console.print(
        f"Deletion error: Release {tag_name} still exists after {timeout} seconds.",
        style=f"bold {COLOR_PALETTE.get('warning')}",
    )