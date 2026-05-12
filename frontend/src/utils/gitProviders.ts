import { repositorySource } from "@context/workspaces/types";

/**
 * Detect the git provider source from a repository URL.
 * Handles github.com, gitlab.com, self-hosted GitLab, and
 * falls back to "generic" for any other host.
 */
export function detectSourceFromUrl(url: string): repositorySource {
  try {
    const { hostname } = new URL(url.trim());
    if (hostname === "github.com") return repositorySource.github;
    if (hostname === "gitlab.com" || hostname.includes("gitlab"))
      return repositorySource.gitlab;
    return repositorySource.generic;
  } catch {
    return repositorySource.github;
  }
}

/**
 * Parse a repository URL into its provider source and path (namespace/repo).
 */
export function parseRepoUrl(
  rawUrl: string,
): { source: repositorySource; path: string } {
  try {
    const { hostname, pathname } = new URL(rawUrl.trim());
    const path = pathname.replace(/^\//, "").replace(/\.git$/, "");
    return { source: detectSourceFromUrl(`https://${hostname}`), path };
  } catch {
    return { source: repositorySource.github, path: "" };
  }
}

/**
 * Extract just the path (namespace/repo) from a repository URL.
 */
export function repoPathFromUrl(url: string): string {
  try {
    return new URL(url).pathname.replace(/^\//, "").replace(/\.git$/, "");
  } catch {
    return url;
  }
}

/**
 * Extract the host (provider domain) from a repository URL, e.g.
 * "https://gitlab.example.com/foo/bar" -> "gitlab.example.com".
 * Returns an empty string when the URL is missing or unparseable.
 */
export function repoHostFromUrl(url?: string | null): string {
  if (!url) return "";
  try {
    return new URL(url.trim()).hostname;
  } catch {
    return "";
  }
}
