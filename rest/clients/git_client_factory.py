from urllib.parse import urlparse


def make_git_client(source: str, token: str | None, repository_url: str | None = None):
    """Return the appropriate Git provider REST client for the given source.

    Args:
        source: One of 'github', 'gitlab', 'generic'.
        token: Personal access token (or equivalent) for the provider.
        repository_url: Full HTML URL of the repository (e.g.
            'https://gitlab.mycompany.com/ns/repo'). Used to derive the
            API base URL for self-hosted GitLab instances. Ignored for
            github.
    """
    if source == "github":
        from clients.github_rest_client import GithubRestClient
        return GithubRestClient(token=token)

    if source == "gitlab":
        from clients.gitlab_rest_client import GitlabRestClient
        base_url = "https://gitlab.com"
        if repository_url:
            parsed = urlparse(repository_url)
            if parsed.scheme and parsed.netloc:
                base_url = f"{parsed.scheme}://{parsed.netloc}"
        return GitlabRestClient(token=token, url=base_url)

    raise ValueError(f"Unsupported git source '{source}'.")
