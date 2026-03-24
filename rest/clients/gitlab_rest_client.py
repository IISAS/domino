import base64
from dataclasses import dataclass
from typing import Optional

import gitlab
import gitlab.exceptions

from core.logger import get_configured_logger
from schemas.exceptions.base import ResourceNotFoundException, ForbiddenException, BaseException as DominoBaseException


@dataclass
class _CommitRef:
    sha: str


@dataclass
class _TagRef:
    name: str
    last_modified: Optional[str]
    commit: _CommitRef


@dataclass
class _FileContent:
    decoded_content: bytes


class GitlabRestClient:
    def __init__(self, token: str | None = None, url: str = "https://gitlab.com"):
        if token is not None:
            token = token.strip().replace("\n", "") or None
        self._gl = gitlab.Gitlab(url, private_token=token)
        self.logger = get_configured_logger(self.__class__.__name__)

    def _handle_exceptions(self, e: Exception):
        if isinstance(e, gitlab.exceptions.GitlabAuthenticationError):
            raise ForbiddenException(
                message='GitLab access token is invalid or does not have the required permissions.'
            )
        if isinstance(e, gitlab.exceptions.GitlabGetError):
            if e.response_code == 404:
                raise ResourceNotFoundException()
            if e.response_code in (401, 403):
                raise ForbiddenException(
                    message='GitLab access token is invalid or does not have the required permissions.'
                )
        raise DominoBaseException('Error connecting to GitLab service.')

    def _get_repo(self, repo_name: str):
        try:
            return self._gl.projects.get(repo_name)
        except (gitlab.exceptions.GitlabGetError, gitlab.exceptions.GitlabAuthenticationError) as e:
            self._handle_exceptions(e)

    def get_tags(self, repo_name: str) -> list[_TagRef]:
        try:
            repo = self._get_repo(repo_name)
            tags = repo.tags.list(get_all=True)
            return [
                _TagRef(
                    name=t.name,
                    last_modified=t.commit.get('committed_date') if t.commit else None,
                    commit=_CommitRef(sha=t.commit['id'] if t.commit else t.target),
                )
                for t in tags
            ]
        except (gitlab.exceptions.GitlabGetError, gitlab.exceptions.GitlabAuthenticationError) as e:
            self.logger.exception('Could not get tags in GitLab: %s', e)
            self._handle_exceptions(e)

    def get_tag(self, repo_name: str, tag_name: str) -> Optional[_TagRef]:
        try:
            repo = self._get_repo(repo_name)
            t = repo.tags.get(tag_name)
            return _TagRef(
                name=t.name,
                last_modified=t.commit.get('committed_date') if t.commit else None,
                commit=_CommitRef(sha=t.commit['id'] if t.commit else t.target),
            )
        except gitlab.exceptions.GitlabGetError:
            return None

    def get_contents(self, repo_name: str, file_path: str, commit_sha: str | None = None) -> _FileContent:
        try:
            repo = self._get_repo(repo_name)
            ref = commit_sha or "main"
            f = repo.files.get(file_path=file_path, ref=ref)
            return _FileContent(decoded_content=base64.b64decode(f.content))
        except (gitlab.exceptions.GitlabGetError, gitlab.exceptions.GitlabAuthenticationError) as e:
            self._handle_exceptions(e)

    def create_file(self, repo_name: str, file_path: str, content: str):
        try:
            repo = self._get_repo(repo_name)
            repo.files.create({
                "file_path": file_path,
                "branch": "main",
                "content": content,
                "commit_message": "Create file",
            })
        except (gitlab.exceptions.GitlabCreateError, gitlab.exceptions.GitlabAuthenticationError) as e:
            self.logger.info('Could not create file in GitLab: %s', e)
            self._handle_exceptions(e)

    def delete_file(self, repo_name: str, file_path: str):
        try:
            repo = self._get_repo(repo_name)
            repo.files.delete(
                file_path=file_path,
                branch="main",
                commit_message="Remove file",
            )
        except (gitlab.exceptions.GitlabDeleteError, gitlab.exceptions.GitlabAuthenticationError) as e:
            self.logger.info('Could not delete file in GitLab: %s', e)
            self._handle_exceptions(e)
