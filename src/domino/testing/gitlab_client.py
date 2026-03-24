"""
Tests for GitlabRestClient.

All GitLab API calls are mocked via unittest.mock — no real network access required.

Run with:
    pytest test_gitlab_client.py -v
"""

from unittest.mock import MagicMock, patch

import gitlab
import pytest

from domino.client.gitlab_rest_client import GitlabRestClient

REPO = "mygroup/myproject"
TOKEN = "fake-token"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_gl():
    """Patch gitlab.Gitlab so no real HTTP calls are made."""
    with patch("gitlab.Gitlab") as MockGitlab:
        yield MockGitlab


@pytest.fixture
def client(mock_gl):
    """Return a GitlabRestClient backed by a fully mocked Gitlab instance."""
    return GitlabRestClient(token=TOKEN)


@pytest.fixture
def mock_project(client):
    """Return the mock project that _get_repo() will hand back."""
    project = MagicMock()
    client._gl.projects.get.return_value = project
    return project


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_gitlab_instance_with_token(self, mock_gl):
        GitlabRestClient(token="mytoken")
        mock_gl.assert_called_once_with("https://gitlab.com", private_token="mytoken")

    def test_creates_gitlab_instance_with_custom_url(self, mock_gl):
        GitlabRestClient(token="mytoken", url="https://gitlab.mycompany.com")
        mock_gl.assert_called_once_with(
            "https://gitlab.mycompany.com", private_token="mytoken"
        )


# ---------------------------------------------------------------------------
# _get_repo
# ---------------------------------------------------------------------------

class TestGetRepo:
    def test_calls_projects_get_with_repo_name(self, client, mock_project):
        result = client._get_repo(REPO)
        client._gl.projects.get.assert_called_once_with(REPO)
        assert result is mock_project


# ---------------------------------------------------------------------------
# get_releases
# ---------------------------------------------------------------------------

class TestGetReleases:
    def test_returns_list_of_releases(self, client, mock_project):
        fake_releases = [MagicMock(name="v1.0"), MagicMock(name="v2.0")]
        mock_project.releases.list.return_value = fake_releases

        result = client.get_releases(REPO)

        mock_project.releases.list.assert_called_once_with(all=True)
        assert result == fake_releases

    def test_returns_empty_list_when_no_releases(self, client, mock_project):
        mock_project.releases.list.return_value = []
        assert client.get_releases(REPO) == []


# ---------------------------------------------------------------------------
# get_tag
# ---------------------------------------------------------------------------

class TestGetTag:
    def test_returns_tag_when_found(self, client, mock_project):
        fake_tag = MagicMock()
        mock_project.tags.get.return_value = fake_tag

        result = client.get_tag(REPO, "v1.0")

        mock_project.tags.get.assert_called_once_with("v1.0")
        assert result is fake_tag

    def test_returns_none_when_tag_not_found(self, client, mock_project):
        mock_project.tags.get.side_effect = gitlab.exceptions.GitlabGetError(
            "404 Tag Not Found", 404
        )

        result = client.get_tag(REPO, "nonexistent")

        assert result is None

    def test_propagates_unexpected_exceptions(self, client, mock_project):
        mock_project.tags.get.side_effect = RuntimeError("unexpected")
        with pytest.raises(RuntimeError):
            client.get_tag(REPO, "v1.0")


# ---------------------------------------------------------------------------
# list_contents
# ---------------------------------------------------------------------------

class TestListContents:
    def test_returns_tree_for_folder(self, client, mock_project):
        fake_tree = [{"name": "file.txt", "type": "blob"}]
        mock_project.repository_tree.return_value = fake_tree

        result = client.list_contents(REPO, "src/")

        mock_project.repository_tree.assert_called_once_with(path="src/", get_all=True)
        assert result == fake_tree

    def test_returns_empty_list_for_empty_folder(self, client, mock_project):
        mock_project.repository_tree.return_value = []
        assert client.list_contents(REPO, "empty/") == []


# ---------------------------------------------------------------------------
# get_contents
# ---------------------------------------------------------------------------

class TestGetContents:
    def test_returns_file_object(self, client, mock_project):
        fake_file = MagicMock()
        mock_project.files.get.return_value = fake_file

        result = client.get_contents(REPO, "README.md")

        mock_project.files.get.assert_called_once_with(
            file_path="README.md", ref="main"
        )
        assert result is fake_file


# ---------------------------------------------------------------------------
# create_file
# ---------------------------------------------------------------------------

class TestCreateFile:
    def test_calls_files_create_with_correct_payload(self, client, mock_project):
        client.create_file(REPO, "docs/new.md", "# Hello")

        mock_project.files.create.assert_called_once_with({
            "file_path": "docs/new.md",
            "branch": "main",
            "content": "# Hello",
            "commit_message": "Create file",
        })

    def test_returns_none(self, client, mock_project):
        mock_project.files.create.return_value = None
        result = client.create_file(REPO, "f.txt", "content")
        assert result is None


# ---------------------------------------------------------------------------
# get_commits
# ---------------------------------------------------------------------------

class TestGetCommits:
    def test_returns_one_commit_by_default(self, client, mock_project):
        fake_commit = MagicMock()
        mock_project.commits.list.return_value = [fake_commit]

        result = client.get_commits(REPO)

        mock_project.commits.list.assert_called_once_with(per_page=1, get_all=False)
        assert result == [fake_commit]

    def test_respects_number_of_commits_param(self, client, mock_project):
        mock_project.commits.list.return_value = [MagicMock()] * 5

        result = client.get_commits(REPO, number_of_commits=5)

        mock_project.commits.list.assert_called_once_with(per_page=5, get_all=False)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# get_commit
# ---------------------------------------------------------------------------

class TestGetCommit:
    def test_returns_commit_by_sha(self, client, mock_project):
        sha = "abc123"
        fake_commit = MagicMock()
        mock_project.commits.get.return_value = fake_commit

        result = client.get_commit(REPO, sha)

        mock_project.commits.get.assert_called_once_with(sha)
        assert result is fake_commit


# ---------------------------------------------------------------------------
# compare_commits
# ---------------------------------------------------------------------------

class TestCompareCommits:
    def test_returns_comparison_result(self, client, mock_project):
        fake_diff = MagicMock()
        mock_project.repository_compare.return_value = fake_diff

        result = client.compare_commits(REPO, "base_sha", "head_sha")

        mock_project.repository_compare.assert_called_once_with("base_sha", "head_sha")
        assert result is fake_diff


# ---------------------------------------------------------------------------
# create_release
# ---------------------------------------------------------------------------

class TestCreateRelease:
    def test_creates_tag_then_release(self, client, mock_project):
        fake_release = MagicMock()
        mock_project.releases.create.return_value = fake_release

        result = client.create_release(
            repo_name=REPO,
            version="v1.0.0",
            tag_message="Release v1.0.0",
            release_message="First stable release",
            target_commit_sha="deadbeef",
        )

        mock_project.tags.create.assert_called_once_with({
            "tag_name": "v1.0.0",
            "ref": "deadbeef",
            "message": "Release v1.0.0",
        })
        mock_project.releases.create.assert_called_once_with({
            "name": "v1.0.0",
            "tag_name": "v1.0.0",
            "description": "First stable release",
        })
        assert result is fake_release

    def test_tag_is_created_before_release(self, client, mock_project):
        """Ensure tag creation always precedes release creation."""
        call_order = []
        mock_project.tags.create.side_effect = lambda *a, **kw: call_order.append("tag")
        mock_project.releases.create.side_effect = lambda *a, **kw: call_order.append("release")

        client.create_release(REPO, "v2.0", "msg", "desc", "sha123")

        assert call_order == ["tag", "release"]

    def test_release_type_param_is_accepted_but_unused(self, client, mock_project):
        """release_type exists for API compatibility — it should not raise."""
        client.create_release(REPO, "v1.0", "msg", "desc", "sha", release_type="branch")
        assert mock_project.tags.create.called


# ---------------------------------------------------------------------------
# delete_release_by_tag
# ---------------------------------------------------------------------------

class TestDeleteReleaseByTag:
    def test_calls_releases_delete_with_tag_name(self, client, mock_project):
        client.delete_release_by_tag(REPO, "v1.0.0")
        mock_project.releases.delete.assert_called_once_with("v1.0.0")

    def test_raises_exception_on_delete_error(self, client, mock_project):
        mock_project.releases.delete.side_effect = gitlab.exceptions.GitlabDeleteError(
            "404 Release Not Found", 404
        )
        with pytest.raises(Exception, match="An error occurred"):
            client.delete_release_by_tag(REPO, "nonexistent")


# ---------------------------------------------------------------------------
# delete_tag
# ---------------------------------------------------------------------------

class TestDeleteTag:
    def test_calls_tags_delete_with_tag_name(self, client, mock_project, capsys):
        client.delete_tag(REPO, "v1.0.0")

        mock_project.tags.delete.assert_called_once_with("v1.0.0")
        captured = capsys.readouterr()
        assert "v1.0.0" in captured.out

    def test_prints_success_message(self, client, mock_project, capsys):
        client.delete_tag(REPO, "v3.0.0")
        captured = capsys.readouterr()
        assert "deleted successfully" in captured.out

    def test_raises_exception_on_delete_error(self, client, mock_project):
        mock_project.tags.delete.side_effect = gitlab.exceptions.GitlabDeleteError(
            "404 Tag Not Found", 404
        )
        with pytest.raises(Exception, match="Error deleting tag"):
            client.delete_tag(REPO, "ghost-tag")
