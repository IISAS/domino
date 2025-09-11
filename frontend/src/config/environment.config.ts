type DeployMode = "local-compose" | "local-k8s-dev" | "local-k8s";

export interface IEnvironment {
  API_URL: string;
  DOMINO_DEPLOY_MODE: DeployMode;
  BASENAME: string;
}

export const environment: IEnvironment = {
  API_URL: import.meta.env.API_URL as string,
  DOMINO_DEPLOY_MODE: import.meta.env.DOMINO_DEPLOY_MODE as DeployMode,
  BASENAME: import.meta.env.BASENAME as string,
};
