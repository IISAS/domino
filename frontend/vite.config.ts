import react from "@vitejs/plugin-react";
import {defineConfig} from "vite";
import svgrPlugin from "vite-plugin-svgr";
import viteTsconfigPaths from "vite-tsconfig-paths";

// https://vitejs.dev/config/
export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      "/rest": {
        target: "http://domino-rest-service:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "")
      }
    }
  },
  plugins: [
    react(),
    viteTsconfigPaths(),
    svgrPlugin(),
  ],
  build: {
    outDir: "build",
  },
  base: "/domino/"
});
