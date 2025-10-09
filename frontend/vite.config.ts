import importMetaEnv from "@import-meta-env/unplugin";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import svgrPlugin from "vite-plugin-svgr";
import viteTsconfigPaths from "vite-tsconfig-paths";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {

   // Load env file based on the current mode ('development' | 'production' etc.)
  const env = loadEnv(mode, process.cwd(), '')

  return {
    server: {
      host: "0.0.0.0",
      port: 3000,
    },
    plugins: [
      react(),
      viteTsconfigPaths(),
      svgrPlugin(),
      importMetaEnv.vite({example: ".env.production"}),
    ],
    define: {
      __APP_ENV__: JSON.stringify(env.APP_ENV),
    },
    build: {
      outDir: "build",
    },
    base: env.BASENAME
  }
})
