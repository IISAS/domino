#!/bin/sh
set -e

echo "DOMINO_DEPLOY_MODE=${DOMINO_DEPLOY_MODE}" >> .env.production
echo "API_URL=${API_URL}" >> .env.production
echo "BASENAME=${BASENAME}" >> .env.production

/usr/share/nginx/html/import-meta-env -x .env.production -p /usr/share/nginx/html/index.html || exit 1

echo "Generating Nginx config from template using envsubst..."
TEMPLATE=/etc/nginx/templates/default.conf.template
OUTPUT=/etc/nginx/conf.d/default.conf
envsubst '${BASENAME}' \
    < "${TEMPLATE}" \
    > "${OUTPUT}"

nginx -g "daemon off;"
