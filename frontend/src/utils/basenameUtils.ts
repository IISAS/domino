import { environment } from "@config/environment.config";

/**
 * Get the app basename from environment, ensure no trailing slash.
 * If the basename is undefined or empty, defaults to '/' (root).
 * Ensures result always starts with '/' unless empty.
 */
export function getBasename(): string {
  const raw = environment.BASENAME ?? "/";

  // Ensure it starts with a forward slash
  let base = raw.startsWith("/") ? raw : "/" + raw;

  // Remove trailing slash if it's not just "/"
  if (base.length > 1 && base.endsWith("/")) {
    base = base.slice(0, -1);
  }

  return base;
}
