import { ChatMessage, ChatMessages, ChatSection, useChatUI } from '@llamaindex/chat-ui'
import { useChat } from '@ai-sdk/react'
import { motion, AnimatePresence } from 'framer-motion'

export const AIComposerPrompt = () => {
  const handler = useChat()
  return (
    <ChatSection
      className="h-screen overflow-hidden p-0 md:p-5"
      handler={handler}
    />
  )
};

function CustomChatMessages() {
  const { messages } = useChatUI()
  return (
    <ChatMessages>
      <ChatMessages.List className="px-0 md:px-16">
        <AnimatePresence>
          {messages.map((message, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, delay: index * 0.1 }}
            >
              <ChatMessage
                message={message}
                isLast={index === messages.length - 1}
                className="items-start"
              >
                <ChatMessage.Avatar>
                  <img
                    className="border-1 rounded-full border-[#e711dd]"
                    alt="LlamaIndex"
                    src="/llama.png"
                  />
                </ChatMessage.Avatar>
                <ChatMessage.Content>
                  <ChatMessage.Part.File />
                  <ChatMessage.Part.Markdown />
                </ChatMessage.Content>
                <ChatMessage.Actions />
              </ChatMessage>
            </motion.div>
          ))}
        </AnimatePresence>
      </ChatMessages.List>
    </ChatMessages>
  )
}