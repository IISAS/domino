export {};

declare global {
  interface Window {
    __RUNTIME_ENV__?: {
      API_URL?: string;
      BASENAME?: string;
      DOMINO_DEPLOY_MODE?: string;
    };
  }
}
