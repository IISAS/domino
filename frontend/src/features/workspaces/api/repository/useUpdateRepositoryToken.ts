import { type MutationConfig } from "@services/clients/react-query.client";
import { useMutation } from "@tanstack/react-query";
import { type AxiosError } from "axios";
import { toast } from "react-toastify";
import { dominoApiClient } from "services/clients/domino.client";

export interface UpdateRepositoryTokenParams {
  repositoryId: string | number;
  git_access_token: string | null;
}

export interface UpdateRepositoryTokenResponse {
  id: number;
  is_token_filled: boolean;
}

export const useUpdateRepositoryToken = (
  config: MutationConfig<
    UpdateRepositoryTokenParams,
    UpdateRepositoryTokenResponse
  > = {},
) => {
  return useMutation({
    mutationFn: async ({ repositoryId, git_access_token }) => {
      return await patchRepositoryToken({ repositoryId, git_access_token });
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

const patchRepositoryToken = async ({
  repositoryId,
  git_access_token,
}: UpdateRepositoryTokenParams): Promise<UpdateRepositoryTokenResponse> => {
  return await dominoApiClient.patch(
    `/pieces-repositories/${repositoryId}/token`,
    { git_access_token },
  );
};
