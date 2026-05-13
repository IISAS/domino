from typing import List, Optional
import ipaddress
import json
import socket
import threading
import time
from urllib.parse import urlparse
import tomli
from math import ceil
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import requests
from core.logger import get_configured_logger
from schemas.context.auth_context import AuthorizationContextData
from schemas.requests.piece_repository import CreateRepositoryRequest, PatchRepositoryRequest, ListRepositoryFilters
from schemas.responses.piece_repository import (
    CreateRepositoryReponse,
    GetRepositoryReleasesResponse,
    PatchRepositoryResponse,
    GetWorkspaceRepositoriesData,
    GetWorkspaceRepositoriesResponse,
    GetRepositoryReleaseDataResponse,
    GetRepositoryResponse,
    UpdateRepositoryTokenResponse,
)
from schemas.responses.base import PaginationSet
from schemas.exceptions.base import ConflictException, ResourceNotFoundException, ForbiddenException, UnauthorizedException
from services.piece_service import PieceService
from services.secret_service import SecretService
from repository.workspace_repository import WorkspaceRepository
from repository.piece_repository_repository import PieceRepositoryRepository
from repository.workflow_repository import WorkflowRepository
from repository.secret_repository import SecretRepository
from database.models.enums import RepositorySource
from database.models import PieceRepository
from clients.git_client_factory import make_git_client
from core.settings import settings


_PROVIDER_CACHE_TTL_SECONDS = 600
_PROVIDER_CACHE_MAX_ENTRIES = 256
_provider_cache: dict[str, tuple[float, str]] = {}
_provider_cache_lock = threading.Lock()


class PieceRepositoryService(object):
    def __init__(self) -> None:
        self.logger = get_configured_logger(self.__class__.__name__)
        self.piece_service = PieceService()
        self.secret_service = SecretService()
        self.workspace_repository = WorkspaceRepository()
        self.piece_repository_repository = PieceRepositoryRepository()
        self.workflow_repository = WorkflowRepository()
        self.secret_repository = SecretRepository()
        self.git_token_fernet = Fernet(settings.GIT_TOKEN_SECRET_KEY)

    def _encrypt_token(self, raw_token: Optional[str]) -> Optional[str]:
        if raw_token is None:
            return None
        raw_token = raw_token.replace("\n", "").strip()
        if not raw_token:
            return None
        return self.git_token_fernet.encrypt(raw_token.encode('utf-8')).decode('utf-8')

    def _decrypt_token(self, stored_token: Optional[str]) -> Optional[str]:
        if not stored_token:
            return None
        return self.git_token_fernet.decrypt(stored_token.encode('utf-8')).decode('utf-8')

    def _resolve_token(self, repository: PieceRepository) -> Optional[str]:
        token = self._decrypt_token(repository.git_access_token) if repository else None
        if not token:
            token = settings.DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN
        if token is not None and not token.strip():
            token = None
        return token

    @staticmethod
    def _sanitize_raw_token(raw_token: Optional[str]) -> Optional[str]:
        if raw_token is None:
            return None
        sanitized = raw_token.replace("\n", "").strip()
        return sanitized or None

    def get_piece_repository(self, piece_repository_id: int) -> GetRepositoryResponse:
        piece_repository = self.piece_repository_repository.find_by_id(piece_repository_id)
        if not piece_repository:
            raise ResourceNotFoundException()

        if not piece_repository.label:
            piece_repository.label = piece_repository.name

        data = piece_repository.to_dict()
        data['is_token_filled'] = bool(piece_repository.git_access_token)
        response = GetRepositoryResponse(**data)
        return response

    def get_pieces_repositories(
        self,
        workspace_id: int,
        page: int,
        page_size: int,
        filters: ListRepositoryFilters
    ) -> GetWorkspaceRepositoriesResponse:
        self.logger.info(f"Getting repositories for workspace {workspace_id}")
        pieces_repositories = self.piece_repository_repository.find_by_workspace_id(
            workspace_id=workspace_id,
            page=page,
            page_size=page_size,
            filters=filters.model_dump(exclude_none=True)
        )
        data = []
        for piece_repository in pieces_repositories:
            if not piece_repository[0].label:
                piece_repository[0].label = piece_repository[0].name
            row = piece_repository[0].to_dict()
            row['is_token_filled'] = bool(piece_repository[0].git_access_token)
            data.append(GetWorkspaceRepositoriesData(**row))

        count = 0 if not pieces_repositories else pieces_repositories[0].count
        metadata = PaginationSet(
            page=page,
            records=len(data),
            total=count,
            last_page=max(0, ceil(count / page_size) - 1)
        )
        response = GetWorkspaceRepositoriesResponse(data=data, metadata=metadata)
        return response

    @staticmethod
    def _host_resolves_public(host: str) -> bool:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False
        return True

    def _probe_gitlab(self, base_url: str) -> bool:
        for api_path in ("/api/v4/metadata", "/api/v4/version"):
            try:
                resp = requests.get(
                    base_url + api_path,
                    timeout=2,
                    allow_redirects=False,
                    stream=True,
                )
            except requests.RequestException:
                continue
            try:
                server_header = resp.headers.get("Server", "") or ""
                if "gitlab" in server_header.lower():
                    return True
                if resp.status_code in (200, 401, 403):
                    chunk = resp.raw.read(2048, decode_content=True) or b""
                    body = chunk.decode("utf-8", errors="replace").lower()
                    if resp.status_code == 200 and '"version"' in body:
                        return True
                    if resp.status_code in (401, 403) and ("401 unauthorized" in body or "403 forbidden" in body):
                        if "gitlab" in body or '"message"' in body:
                            return True
            finally:
                resp.close()
        return False

    def detect_provider(self, url: str) -> str:
        if not url:
            return "unknown"
        try:
            parsed = urlparse(url.strip())
        except ValueError:
            return "unknown"
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return "unknown"
        host = parsed.hostname.lower()
        if host == "github.com" or host.endswith(".github.com"):
            return "github"
        if host == "gitlab.com" or host.endswith(".gitlab.com"):
            return "gitlab"

        now = time.time()
        with _provider_cache_lock:
            cached = _provider_cache.get(host)
            if cached and (now - cached[0]) < _PROVIDER_CACHE_TTL_SECONDS:
                return cached[1]

        if not self._host_resolves_public(host):
            result = "unknown"
        else:
            base = f"{parsed.scheme}://{parsed.netloc}"
            result = "gitlab" if self._probe_gitlab(base) else "unknown"

        with _provider_cache_lock:
            if len(_provider_cache) >= _PROVIDER_CACHE_MAX_ENTRIES:
                oldest_host = min(_provider_cache, key=lambda h: _provider_cache[h][0])
                _provider_cache.pop(oldest_host, None)
            _provider_cache[host] = (now, result)
        return result

    def get_piece_repository_releases(
        self,
        source: str,
        path: str,
        auth_context: AuthorizationContextData,
        url: str | None = None,
        access_token: Optional[str] = None,
    ) -> List[GetRepositoryReleasesResponse]:
        self.logger.info(f"Getting releases for repository {path}")

        token = self._sanitize_raw_token(access_token)
        if not token:
            token = settings.DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN
        if token is not None and not token.strip():
            token = None
        git_client = make_git_client(source=source, token=token, repository_url=url)
        tags = git_client.get_tags(repo_name=path)
        if not tags:
            return []
        return [GetRepositoryReleasesResponse(version=tag.name, last_modified=tag.last_modified) for tag in tags]

    def get_piece_repository_release_data(
        self,
        version: str,
        source: str,
        path: str,
        auth_context: AuthorizationContextData,
        url: str | None = None,
        access_token: Optional[str] = None,
    ) -> GetRepositoryReleaseDataResponse:
        self.logger.info(f'Getting release data for repository {path}')

        token = self._sanitize_raw_token(access_token)
        if not token:
            token = settings.DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN
        if token is not None and not token.strip():
            token = None
        tag_data = self._read_repository_data(path=path, source=source, version=version, access_token=token, repository_url=url)
        name = tag_data.get('config_toml').get('repository').get("REPOSITORY_NAME")
        description = tag_data.get('config_toml').get('repository').get("DESCRIPTION")
        pieces_list = list(tag_data.get('compiled_metadata').keys())
        response = GetRepositoryReleaseDataResponse(
            name=name,
            description=description,
            pieces=pieces_list
        )
        return response

    def patch_piece_repository(
        self,
        repository_id: int,
        piece_repository_data: PatchRepositoryRequest
    ) -> PatchRepositoryResponse:

        repository = self.piece_repository_repository.find_by_id(id=repository_id)
        if not repository:
            raise ResourceNotFoundException()
        self.logger.info(f"Updating piece repository {repository.id} for workspace {repository.workspace_id}")

        repository_files_metadata = self._read_repository_data(
            source=repository.source,
            path=repository.path,
            version=piece_repository_data.version,
            access_token=self._resolve_token(repository),
            repository_url=repository.url,
        )
        new_repo = PieceRepository(
            created_at=datetime.now(timezone.utc),
            name=repository_files_metadata['config_toml'].get('repository').get('REPOSITORY_NAME'),
            source=repository.source,
            path=repository.path,
            version=piece_repository_data.version,
            dependencies_map=repository_files_metadata['dependencies_map'],
            compiled_metadata=repository_files_metadata['compiled_metadata'],
            git_access_token=repository.git_access_token,
            workspace_id=repository.workspace_id
        )
        repository = self.piece_repository_repository.update(piece_repository=new_repo, id=repository.id)
        self._update_repository_pieces(
            source=repository.source,
            compiled_metadata=repository_files_metadata['compiled_metadata'],
            dependencies_map=repository_files_metadata['dependencies_map'],
            repository_id=repository.id,
        )

        # Check secrets to update
        all_current_secrets = set()
        for value in repository_files_metadata['dependencies_map'].values():
            for secret in value.get('secrets'):
                all_current_secrets.add(secret)

        for secret in all_current_secrets:
            db_secret = self.secret_repository.find_by_name_and_piece_repository_id(
                name=secret,
                piece_repository_id=repository.id
            )
            # If secret exists, don't touch it
            if db_secret:
                continue
            self.secret_service.create_workspace_repository_secret(
                workspace_id=repository.workspace_id,
                repository_id=repository.id,
                secret_name=secret,
            )
        # Delete secrets that are not in the version dependencies map
        self.secret_repository.delete_by_piece_repository_id_and_not_names(
            names=all_current_secrets,
            piece_repository_id=repository.id
        )

        data = repository.to_dict()
        data['is_token_filled'] = bool(repository.git_access_token)
        return PatchRepositoryResponse(**data)

    def update_piece_repository_token(
        self,
        piece_repository_id: int,
        git_access_token: Optional[str],
    ) -> UpdateRepositoryTokenResponse:
        repository = self.piece_repository_repository.find_by_id(id=piece_repository_id)
        if not repository:
            raise ResourceNotFoundException()
        self.logger.info(f"Updating access token for piece repository {repository.id}")

        encrypted = self._encrypt_token(git_access_token)
        updated = PieceRepository(
            id=repository.id,
            created_at=repository.created_at,
            name=repository.name,
            label=repository.label,
            source=repository.source,
            path=repository.path,
            url=repository.url,
            version=repository.version,
            dependencies_map=repository.dependencies_map,
            compiled_metadata=repository.compiled_metadata,
            git_access_token=encrypted,
            workspace_id=repository.workspace_id,
        )
        saved = self.piece_repository_repository.update(piece_repository=updated, id=repository.id)
        return UpdateRepositoryTokenResponse(
            id=saved.id,
            is_token_filled=bool(saved.git_access_token),
        )

    def create_default_storage_repository(self, workspace_id: int):
        """
        Create default storage repository for workspace.
        Creating a repository will create all pieces and secrets to this repository.
        """
        self.logger.info(f"Creating default storage repository")

        new_repo = PieceRepository(
            name=settings.DEFAULT_STORAGE_REPOSITORY['name'],
            created_at=datetime.now(timezone.utc),
            workspace_id=workspace_id,
            path=settings.DEFAULT_STORAGE_REPOSITORY['path'],
            source=settings.DEFAULT_STORAGE_REPOSITORY['source'],
            version=settings.DEFAULT_STORAGE_REPOSITORY['version'],
            url=settings.DEFAULT_STORAGE_REPOSITORY['url']
        )

        default_storage_repository = self.piece_repository_repository.create(piece_repository=new_repo)
        pieces = self.piece_service.create_default_storage_pieces(
            piece_repository_id=default_storage_repository.id,
        )
        self.secret_service.create_default_storage_pieces_secrets(
            pieces=pieces,
            workspace_id=workspace_id,
            repository_id=default_storage_repository.id
        )
        return default_storage_repository

    def create_piece_repository(
        self,
        piece_repository_data: CreateRepositoryRequest,
        auth_context: AuthorizationContextData
    ) -> CreateRepositoryReponse:

        self.logger.info(f"Creating piece repository for workspace {piece_repository_data.workspace_id}")
        repository = self.piece_repository_repository.find_by_path_and_workspace_id(
            path=piece_repository_data.path,
            workspace_id=piece_repository_data.workspace_id
        )
        if repository:
            raise ConflictException(message=f"Repository {piece_repository_data.path} already exists for this workspace")

        raw_token = self._sanitize_raw_token(getattr(piece_repository_data, 'git_access_token', None))
        token = raw_token if raw_token else settings.DOMINO_DEFAULT_PIECES_REPOSITORY_TOKEN
        if token is not None and not token.strip():
            token = None
        repository_files_metadata = self._read_repository_data(
            source=piece_repository_data.source,
            path=piece_repository_data.path,
            version=piece_repository_data.version,
            access_token=token,
            repository_url=piece_repository_data.url,
        )
        encrypted_token = self._encrypt_token(raw_token)
        new_repo = PieceRepository(
            created_at=datetime.now(timezone.utc),
            name=repository_files_metadata['config_toml'].get('repository').get('REPOSITORY_NAME'),
            source=piece_repository_data.source,
            path=piece_repository_data.path,
            label=repository_files_metadata['config_toml'].get('repository').get('REPOSITORY_LABEL'),
            version=piece_repository_data.version,
            dependencies_map=repository_files_metadata['dependencies_map'],
            compiled_metadata=repository_files_metadata['compiled_metadata'],
            git_access_token=encrypted_token,
            workspace_id=piece_repository_data.workspace_id,
            url=piece_repository_data.url
        )
        repository = self.piece_repository_repository.create(piece_repository=new_repo)
        try:
            # Create pieces for this repository in database
            self._update_repository_pieces(
                repository_id=repository.id,
                source=piece_repository_data.source,
                compiled_metadata=repository_files_metadata['compiled_metadata'],
                dependencies_map=repository_files_metadata['dependencies_map'],
            )
            # Create secrets for the repository with null values
            secrets_to_update = list()
            for value in repository_files_metadata['dependencies_map'].values():
                for secret in value.get('secrets'):
                    secrets_to_update.append(secret)
            secrets_to_update = list(set(secrets_to_update))

            for secret in secrets_to_update:
                self.secret_service.create_workspace_repository_secret(
                    workspace_id=piece_repository_data.workspace_id,
                    repository_id=repository.id,
                    secret_name=secret,
                )

            response_data = repository.to_dict()
            response_data['is_token_filled'] = bool(repository.git_access_token)
            response = CreateRepositoryReponse(**response_data)
            return response
        except (BaseException, ForbiddenException, UnauthorizedException, ResourceNotFoundException) as e:
            self.logger.exception(e)
            self.piece_repository_repository.delete(id=repository.id)
            raise e

    def _read_data_from_git(self, source: str, path: str, version: str, access_token: str = None, repository_url: str = None) -> dict:
        """Read piece repository metadata files at a specific tagged version.

        Returns:
            dict with keys: dependencies_map, compiled_metadata, config_toml
        """
        git_client = make_git_client(source=source, token=access_token, repository_url=repository_url)
        tag = git_client.get_tag(repo_name=path, tag_name=version)
        if not tag:
            raise ResourceNotFoundException(message=f"Version {version} not found in repository {path}")

        commit_sha_ref = str(tag.commit.sha)
        dependencies_map = git_client.get_contents(
            repo_name=path,
            file_path='.domino/dependencies_map.json',
            commit_sha=commit_sha_ref
        )
        dependencies_map = json.loads(dependencies_map.decoded_content.decode('utf-8'))
        compiled_metadata = git_client.get_contents(
            repo_name=path,
            file_path='.domino/compiled_metadata.json',
            commit_sha=commit_sha_ref
        )
        compiled_metadata = json.loads(compiled_metadata.decoded_content.decode('utf-8'))

        config_toml = git_client.get_contents(
            repo_name=path,
            file_path='config.toml',
            commit_sha=commit_sha_ref
        )
        config_toml = tomli.loads(config_toml.decoded_content.decode('utf-8'))

        return {
            "dependencies_map": dependencies_map,
            "compiled_metadata": compiled_metadata,
            "config_toml": config_toml,
        }

    def _update_repository_pieces(
        self,
        source: str,
        compiled_metadata: dict,
        dependencies_map: dict,
        repository_id: int,
    ):
        self.piece_service.check_pieces_to_update(
            repository_id=repository_id,
            compiled_metadata=compiled_metadata,
            dependencies_map=dependencies_map,
        )

    def _read_repository_data(self, source: str, path: str, version: str, access_token: str, repository_url: str = None):
        return self._read_data_from_git(
            source=source,
            path=path,
            version=version,
            access_token=access_token,
            repository_url=repository_url,
        )

    def delete_repository(self, piece_repository_id: int):
        repository = self.piece_repository_repository.find_by_id(id=piece_repository_id)
        if not repository:
            raise ResourceNotFoundException()

        if getattr(repository, 'source') == RepositorySource.default.value:
            raise ForbiddenException(message="Default repository can not be deleted.")

        results = self.workflow_repository.count_piece_repository_dependent_workflows(piece_repository_id=repository.id)
        if results > 0:
            raise ConflictException(message=f"Repository {repository.name} is used in {results} workflow{'' if results == 1 else 's'}, delete {'it' if results == 1 else 'them'} first.")

        self.piece_repository_repository.delete(id=piece_repository_id)