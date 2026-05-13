import { type repositorySource } from "@context/workspaces/types";
import { type MutationConfig } from "@services/clients/react-query.client";
import { useMutation } from "@tanstack/react-query";
import { type AxiosError } from "axios";
import { toast } from "react-toastify";
import { dominoApiClient } from "services/clients/domino.client";

export interface RepositoriesReleasesParams {
  source: repositorySource;
  path: string;
  url?: string;
  git_access_token?: string | null;
}

export interface RepositoriesReleasesResponse {
  version: string;
  last_modified: string;
}

interface UseRepositoriesReleases {
  workspaceId?: string;
}

export const useRepositoriesReleases = (
  { workspaceId }: UseRepositoriesReleases,
  config: MutationConfig<
    RepositoriesReleasesParams,
    RepositoriesReleasesResponse[]
  > = {},
) => {
  return useMutation({
    mutationFn: async ({ source, path, url, git_access_token }) => {
      if (!workspaceId) {
        throw new Error("No workspace selected");
      }

      return await getPiecesRepositoriesReleases({
        path,
        source,
        url,
        git_access_token,
        workspaceId,
      });
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      const message =
        (e.response?.data?.detail ?? e?.message) || "Something went wrong";

      toast.error(message, {
        toastId: message,
      });
    },
    ...config,
  });
};

const getPiecesRepositoriesReleases = async ({
  source,
  path,
  url,
  git_access_token,
  workspaceId,
}: RepositoriesReleasesParams & { workspaceId: string }): Promise<
  RepositoriesReleasesResponse[]
> => {
  const search = new URLSearchParams();
  search.set("source", source);
  search.set("path", path);
  search.set("workspace_id", workspaceId);
  if (url) search.set("url", url);

  const headers = git_access_token
    ? { "X-Repository-Access-Token": git_access_token }
    : undefined;

  return await dominoApiClient.get(
    `/pieces-repositories/releases?${search.toString()}`,
    headers ? { headers } : undefined,
  );
};
