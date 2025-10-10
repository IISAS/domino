#!/bin/sh
set -e

: "${BASENAME:=/}"
BASENAME=$(echo "${BASENAME}" | sed -E 's:/+:/:g')     # Remove repeated slashes
BASENAME="${BASENAME%/}/"                              # Remove trailing slash and add one back
export BASENAME

# Define temporary output file
TEMPLATE=/etc/nginx/templates/default.conf.template
OUTPUT=/etc/nginx/conf.d/default.conf

if [ "${BASENAME}" = "/" ]; then
  echo "Skipping location block for root path..."
  # Remove the placeholder entirely
  sed '/__LOCATION_BASENAME__/d' "${TEMPLATE}" > "${OUTPUT}"
else
  echo "Adding location block for BASENAME=${BASENAME}..."
  # Inject the location block before envsubst
  awk -v block="location ${BASENAME} {\n    rewrite ^${BASENAME}(.*)\$ /\\1 last;\n}\n" \
      '/__LOCATION_BASENAME__/ {print block; next} {print}' "${TEMPLATE}" > "${OUTPUT}"
fi

echo "DOMINO_DEPLOY_MODE=${DOMINO_DEPLOY_MODE}" >> .env.production
echo "API_URL=${API_URL}" >> .env.production
echo "BASENAME=${BASENAME}" >> .env.production

/usr/share/nginx/html/import-meta-env -x .env.production -p /usr/share/nginx/html/index.html || exit 1

echo "Generating Nginx config from template using envsubst..."
envsubst '${BASENAME}' \
    < "${OUTPUT}" \
    > "${OUTPUT}.tmp"

mv "${OUTPUT}.tmp" "${OUTPUT}"

nginx -g "daemon off;"
