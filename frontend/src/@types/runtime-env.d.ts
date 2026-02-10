export {};

declare global {
  interface Window {
    import_meta_env?: {
      API_URL?: string;
      DOMINO_DEPLOY_MODE?: string;
    };
  }
}
