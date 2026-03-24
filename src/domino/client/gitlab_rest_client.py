import gitlab


class GitlabRestClient:
    def __init__(self, token: str, url: str = "https://gitlab.com"):
        self._gl = gitlab.Gitlab(url, private_token=token)

    def _get_repo(self, repo_name: str):
        """
        Get a project by its path (e.g. 'namespace/project').
        """
        return self._gl.projects.get(repo_name)

    def get_releases(self, repo_name: str):
        """
        Get all releases from a repository.
        """
        repo = self._get_repo(repo_name)
        return list(repo.releases.list(all=True))

    def get_tag(self, repo_name: str, tag_name: str):
        """
        Get a tag from a repository.
        """
        repo = self._get_repo(repo_name)
        try:
            return repo.tags.get(tag_name)
        except gitlab.exceptions.GitlabGetError:
            return None

    def list_contents(self, repo_name: str, folder_path: str):
        """
        List the contents of a folder from a repository.
        """
        repo = self._get_repo(repo_name)
        return repo.repository_tree(path=folder_path, get_all=True)

    def get_contents(self, repo_name: str, file_path: str):
        """
        Get the contents of a file from a repository.
        """
        repo = self._get_repo(repo_name)
        return repo.files.get(file_path=file_path, ref="main")

    def create_file(self, repo_name: str, file_path: str, content: str):
        """
        Create a file in a repository.
        """
        repo = self._get_repo(repo_name)
        repo.files.create({
            "file_path": file_path,
            "branch": "main",
            "content": content,
            "commit_message": "Create file",
        })

    def get_commits(self, repo_name: str, number_of_commits: int = 1):
        """
        Get the latest N commits from the repository.
        """
        repo = self._get_repo(repo_name)
        return repo.commits.list(per_page=number_of_commits, get_all=False)

    def get_commit(self, repo_name: str, commit_sha: str):
        """
        Get a single commit by SHA.
        """
        repo = self._get_repo(repo_name)
        return repo.commits.get(commit_sha)

    def compare_commits(self, repo_name: str, base_sha: str, head_sha: str):
        """
        Compare two commits and return the diff.
        """
        repo = self._get_repo(repo_name)
        return repo.repository_compare(base_sha, head_sha)

    def create_release(
        self,
        repo_name: str,
        version: str,
        tag_message: str,
        release_message: str,
        target_commit_sha: str,
        release_type: str = "commit",  # kept for API compatibility, unused in GitLab
    ):
        """
        Create a tag and a release in a repository.
        GitLab requires the tag to exist before (or be created alongside) the release.
        """
        repo = self._get_repo(repo_name)

        # Create the tag first (GitLab releases are tied to existing tags)
        repo.tags.create({
            "tag_name": version,
            "ref": target_commit_sha,
            "message": tag_message,
        })

        # Create the release attached to that tag
        return repo.releases.create({
            "name": version,
            "tag_name": version,
            "description": release_message,
        })

    def delete_release_by_tag(self, repo_name: str, tag_name: str):
        """
        Delete a release associated with a specific tag.
        """
        repo = self._get_repo(repo_name)
        try:
            repo.releases.delete(tag_name)
        except gitlab.exceptions.GitlabDeleteError as e:
            raise Exception(f"An error occurred: {e}")

    def delete_tag(self, repo_name: str, tag_name: str):
        """
        Delete a tag from a GitLab repository.
        """
        repo = self._get_repo(repo_name)
        try:
            repo.tags.delete(tag_name)
            print(f"Tag '{tag_name}' deleted successfully.")
        except gitlab.exceptions.GitlabDeleteError as e:
            raise Exception(f"Error deleting tag: {e}")
