import fs from "fs";

const runtimeEnv = {
  API_URL: process.env.API_URL ?? "http://localhost:8000",
  DOMINO_DEPLOY_MODE: process.env.DOMINO_DEPLOY_MODE ?? "local-compose",
};

const html = fs.readFileSync("index.html", "utf-8");

fs.writeFileSync(
  "index.html",
  html.replace(
    '"import_meta_env_placeholder"',
    JSON.stringify(runtimeEnv).replace(/"/g, '\\"')
  )
);

console.log("Injected runtime env:", runtimeEnv);

