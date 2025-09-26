#!/bin/sh
set -e

: "${BASENAME:=/}"
BASENAME=$(echo "${BASENAME}" | sed -E 's:/+:/:g')     # Remove repeated slashes
BASENAME="${BASENAME%/}/"                              # Remove trailing slash and add one back
export BASENAME

echo "DOMINO_DEPLOY_MODE=${DOMINO_DEPLOY_MODE}" >> .env.production
echo "API_URL=${API_URL}" >> .env.production
echo "BASENAME=${BASENAME}" >> .env.production

/usr/share/nginx/html/import-meta-env -x .env.production -p /usr/share/nginx/html/index.html || exit 1

echo "Generating Nginx config from template using envsubst..."
envsubst '${BASENAME}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

nginx -g "daemon off;"
