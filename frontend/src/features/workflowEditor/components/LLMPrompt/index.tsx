import { SettingsSuggest } from "@mui/icons-material";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import React, { useState } from "react";

interface LLMPromptProps {
  /** Function that calls the LLM API and returns the response */
  callLLM: (prompt: string) => Promise<string>;
  placeholder?: string;
  label?: string;
}

const LLMPrompt: React.FC<LLMPromptProps> = ({
  callLLM,
  placeholder = "Type your prompt here...",
  label = "LLM Prompt",
}) => {
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setResponse(null);
    setError(null);

    if (!prompt.trim()) return;

    setLoading(true);
    try {
      const result = await callLLM(prompt);
      setResponse(result);
    } catch (err) {
      console.error(err);
      setError("Failed to get response from LLM.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4 border rounded-md shadow-sm max-w-md mx-auto">
      <label className="font-semibold">{label}</label>
      <form onSubmit={handleSubmit} className="flex flex-col gap-2">
        <textarea
          style={{ width: "100%" }}
          className="border rounded-md p-2 resize-none"
          rows={4}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={placeholder}
        />
        <Button
            variant="contained"            
            type="submit"
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} /> : <SettingsSuggest/>}
          >
            {loading ? "Generating..." : "Submit"}
        </Button>
      </form>

      {error && <p className="text-red-600">{error}</p>}
      {response && (
        <div className="mt-2 p-2 border rounded bg-gray-50 whitespace-pre-wrap">
          {response}
        </div>
      )}
    </div>
  );
};

export default LLMPrompt;
