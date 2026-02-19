#!/bin/sh
set -e

APP_DIR=/usr/share/nginx/html

cat <<EOF > $APP_DIR/.env
API_URL=${API_URL}
DOMINO_DEPLOY_MODE=${DOMINO_DEPLOY_MODE}
EOF

echo "Injecting runtime environment variables..."

node $APP_DIR/import-meta-env.cjs \
  -x $APP_DIR/.env \
  -e $APP_DIR/.env \
  -p $APP_DIR/index.html || true

echo "Starting nginx..."

nginx -g "daemon off;"
