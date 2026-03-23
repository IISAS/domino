import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/Send";
import {
  Box,
  CircularProgress,
  Divider,
  Drawer,
  IconButton,
  TextField,
  Typography,
} from "@mui/material";
import { DrawerHeader } from "components/PrivateLayout/header/drawerMenu.style";
import { useWorkspaces } from "context/workspaces";
import {
  type ConversationMessage,
  useSendChatMessage,
} from "features/workflowEditor/api/chat";
import { type GenerateWorkflowsParams } from "features/workflowEditor/context/workflowsEditor";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "react-toastify";

interface ChatDrawerProps {
  open: boolean;
  onClose: () => void;
  onWorkflowReceived: (json: GenerateWorkflowsParams) => void;
}

export const ChatDrawer: React.FC<ChatDrawerProps> = ({
  open,
  onClose,
  onWorkflowReceived,
}) => {
  const { workspace } = useWorkspaces();
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { mutate: sendMessage, isPending } = useSendChatMessage({
    workspaceId: workspace?.id ? String(workspace.id) : undefined,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isPending) return;

    const newMessages: ConversationMessage[] = [
      ...messages,
      { role: "user", content: trimmed },
    ];

    setMessages(newMessages);
    setInput("");

    sendMessage(
      { messages: newMessages },
      {
        onSuccess: (response) => {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: response.message },
          ]);
          if (response.workflow) {
            try {
              onWorkflowReceived(response.workflow);
            } catch {
              toast.error("Failed to load the received workflow.");
            }
          }
        },
        onError: () => {
          toast.error("Failed to send message.");
        },
      },
    );
  }, [input, isPending, messages, sendMessage, onWorkflowReceived]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <Drawer
      variant="temporary"
      anchor="left"
      open={open}
      onClose={onClose}
      sx={{
        "& .MuiDrawer-paper": {
          width: 360,
          display: "flex",
          flexDirection: "column",
        },
      }}
    >
      <DrawerHeader sx={{ marginTop: "4rem", justifyContent: "space-between" }}>
        <Typography variant="h1" sx={{ flex: 1 }}>
          Chat
        </Typography>
        <IconButton onClick={onClose} edge="end">
          <CloseIcon />
        </IconButton>
      </DrawerHeader>
      <Divider />

      {/* Message list */}
      <Box
        sx={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 1,
          p: 2,
        }}
      >
        {messages.map((msg, idx) => (
          <Box
            key={idx}
            sx={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%",
              bgcolor: msg.role === "user" ? "primary.main" : "grey.200",
              color: msg.role === "user" ? "primary.contrastText" : "text.primary",
              borderRadius: 2,
              px: 1.5,
              py: 1,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            <Typography variant="body2">{msg.content}</Typography>
          </Box>
        ))}
        {isPending && (
          <Box sx={{ alignSelf: "flex-start", px: 1 }}>
            <CircularProgress size={16} />
          </Box>
        )}
        <div ref={messagesEndRef} />
      </Box>

      <Divider />

      {/* Input area */}
      <Box sx={{ display: "flex", alignItems: "flex-end", p: 1, gap: 1 }}>
        <TextField
          multiline
          maxRows={4}
          fullWidth
          size="small"
          placeholder="Describe a workflow..."
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
          }}
          onKeyDown={handleKeyDown}
          disabled={isPending}
        />
        <IconButton
          color="primary"
          onClick={handleSend}
          disabled={isPending || !input.trim()}
        >
          {isPending ? <CircularProgress size={16} /> : <SendIcon />}
        </IconButton>
      </Box>
    </Drawer>
  );
};
