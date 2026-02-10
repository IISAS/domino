#!/bin/sh
set -e

# Ensure BASENAME exists
: "${BASENAME:=/}"  # default to / if not set

# Remove trailing slash, but leave root "/" intact
if [ "$BASENAME" != "/" ]; then
    BASENAME="${BASENAME%/}"
fi

# Show the result
echo "BASENAME: '${BASENAME}'"

APP_DIR=/usr/share/nginx/html

cat <<EOF > $APP_DIR/.env
API_URL=${API_URL}
BASENAME=${BASENAME}
DOMINO_DEPLOY_MODE=${DOMINO_DEPLOY_MODE}
EOF

echo "Injecting runtime environment variables..."

node $APP_DIR/import-meta-env.cjs \
  -x $APP_DIR/.env \
  -e $APP_DIR/.env \
  -p $APP_DIR/index.html || true

echo "Generating Nginx config from template using envsubst..."

TEMPLATE=/etc/nginx/templates/default.conf.template
OUTPUT=/etc/nginx/conf.d/default.conf
envsubst '${BASENAME}' \
    < "${TEMPLATE}" \
    > "${OUTPUT}"

echo "Starting nginx..."

nginx -g "daemon off;"
