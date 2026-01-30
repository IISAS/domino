import App from "providers/app";
import React from "react";
import ReactDOM from "react-dom/client";

import 'reactflow/dist/style.css';

import '@fontsource/roboto/300.css';
import '@fontsource/roboto/400.css';
import '@fontsource/roboto/500.css';
import '@fontsource/roboto/700.css';

import "./index.css";
import "tailwindcss";


import "@llamaindex/chat-ui/styles/markdown.css";
import "@llamaindex/chat-ui/styles/pdf.css";
import "@llamaindex/chat-ui/styles/editor.css";

const root = ReactDOM.createRoot(document.getElementById("root")!);
root.render(<App />);
