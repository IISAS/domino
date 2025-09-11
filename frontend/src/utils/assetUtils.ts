import { environment } from "@config/environment.config";

/**
 * Builds an asset URL by prefixing with basename if provided,
 * ensuring that there are no duplicate slashes.
 *
 * @param basename - the base path, e.g. from environment or router
 * @param assetPath - the asset path, e.g. "/assets/main_logo_white.png"
 * @returns a properly concatenated path, e.g. "/basename/assets/main_logo_white.png"
 */
export function buildAssetSrc(assetPath: string): string {
  const basename = environment.BASENAME ?? "";
  const base = basename
    ? basename.endsWith("/")
      ? basename.slice(0, -1)
      : basename
    : "";

  const asset = assetPath.startsWith("/") ? assetPath.slice(1) : assetPath;

  return base ? `${base}/${asset}` : `/${asset}`;
}
