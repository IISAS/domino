type DeployMode = "local-compose" | "local-k8s-dev" | "local-k8s";

export interface IEnvironment {
  API_URL: string;
  DOMINO_DEPLOY_MODE: DeployMode;
}

const defaults: IEnvironment = {
  API_URL: "http://localhost:8000",
  DOMINO_DEPLOY_MODE: "development" as DeployMode,
};

function getRuntimeEnv<K extends keyof IEnvironment>(key: K): IEnvironment[K] {
  return window.__RUNTIME_ENV__?.[key] as IEnvironment[K] ?? defaults[key];
}

export const environment: IEnvironment = {
  API_URL: getRuntimeEnv("API_URL"),
  DOMINO_DEPLOY_MODE: getRuntimeEnv("DOMINO_DEPLOY_MODE"),
};
