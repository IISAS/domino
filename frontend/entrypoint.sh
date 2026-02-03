#!/bin/sh
set -e

APP_DIR=/usr/share/nginx/html

echo "Injecting runtime environment variables..."

node $APP_DIR/import-meta-env.cjs \
  -x $APP_DIR/.env.production \
  -e /dev/null \
  -p $APP_DIR/index.html || true

echo "Generating Nginx config from template using envsubst..."

TEMPLATE=/etc/nginx/templates/default.conf.template
OUTPUT=/etc/nginx/conf.d/default.conf
envsubst '${BASENAME}' \
    < "${TEMPLATE}" \
    > "${OUTPUT}"

echo "Starting nginx..."

nginx -g "daemon off;"
