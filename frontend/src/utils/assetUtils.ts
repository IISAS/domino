import { getBasename } from "@utils/basenameUtils";

/**
 * Builds an asset URL by prefixing with basename,
 * ensuring that there are no duplicate slashes.
 *
 * @param assetPath - the asset path, e.g. "/assets/main_logo_white.png"
 * @returns a properly concatenated path, e.g. "/basename/assets/main_logo_white.png"
 */
export function buildAssetSrc(assetPath: string): string {
  return getBasename() + (assetPath.startsWith("/") ? assetPath : "/" + assetPath);
}
