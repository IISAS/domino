import { type MutationConfig } from "@services/clients/react-query.client";
import { useMutation } from "@tanstack/react-query";
import { type AxiosError } from "axios";
import { type GenerateWorkflowsParams } from "features/workflowEditor/context/workflowsEditor";
import { toast } from "react-toastify";
import { dominoApiClient } from "services/clients/domino.client";

export interface ConversationMessage {
  role: "user" | "assistant";
  content: string;
}

interface SendChatMessageRequest {
  messages: ConversationMessage[];
}

export interface ChatResponse {
  message: string;
  workflow?: GenerateWorkflowsParams;
}

interface UseSendChatMessage {
  workspaceId?: string;
}

export const useSendChatMessage = (
  { workspaceId }: UseSendChatMessage,
  config: MutationConfig<SendChatMessageRequest, ChatResponse> = {},
) => {
  return useMutation({
    mutationFn: async (params) => {
      if (!workspaceId) throw new Error("No workspace selected");
      return await sendChatMessage({ ...params, workspaceId });
    },
    onError: (e: AxiosError<{ detail: string }>) => {
      const message =
        (e.response?.data?.detail ?? e?.message) || "Something went wrong";
      toast.error(message, { toastId: message });
    },
    ...config,
  });
};

const sendChatMessage = async ({
  workspaceId,
  messages,
}: SendChatMessageRequest & UseSendChatMessage): Promise<ChatResponse> => {
  return await dominoApiClient.post(
    `/workspaces/${workspaceId}/chat`,
    { messages },
  );
};
