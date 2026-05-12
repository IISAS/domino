import { skipToken, useQuery } from "@tanstack/react-query";
import { dominoApiClient } from "services/clients/domino.client";

export type DetectedProvider = "github" | "gitlab" | "unknown";

interface DetectProviderResponse {
  provider: DetectedProvider;
}

const hostFromUrl = (url: string): string | null => {
  try {
    return new URL(url.trim()).host.toLowerCase();
  } catch {
    return null;
  }
};

export const useDetectProvider = ({
  url,
  workspaceId,
  enabled = true,
}: {
  url: string;
  workspaceId?: string;
  enabled?: boolean;
}) => {
  const host = hostFromUrl(url);
  const canRun = !!host && !!workspaceId && enabled;
  return useQuery({
    queryKey: ["detect-provider", host],
    queryFn: canRun
      ? async () => await fetchProvider(url, workspaceId as string)
      : skipToken,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  });
};

const fetchProvider = async (
  url: string,
  workspaceId: string,
): Promise<DetectedProvider> => {
  const search = new URLSearchParams();
  search.set("url", url);
  search.set("workspace_id", workspaceId);
  const data = (await dominoApiClient.get(
    `/pieces-repositories/detect-provider?${search.toString()}`,
  )) as unknown as DetectProviderResponse;
  return data?.provider ?? "unknown";
};
