#!/usr/bin/env sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

usage() {
  cat <<'EOF'
Usage:
  ./cutover-to-domain.sh <domain> <acme-email>

Example:
  ./cutover-to-domain.sh quiz.example.com admin@example.com

This script updates deploy/oracle/.env for a domain-based HTTPS deployment,
recreates the containers, and prints the Spotify callback URL to register.
EOF
}

if [ "${1:-}" = "" ] || [ "${2:-}" = "" ]; then
  usage
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE"
  echo "Create it from .env.example before running this script."
  exit 1
fi

DOMAIN="$1"
ACME_EMAIL="$2"
APP_ORIGIN="https://$DOMAIN"

update_env_value() {
  key="$1"
  value="$2"

  if grep -q "^$key=" "$ENV_FILE"; then
    sed -i.bak "s|^$key=.*|$key=$value|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

update_env_value "DEBUG" "false"
update_env_value "APP_HOST" "$DOMAIN"
update_env_value "APP_ORIGIN" "$APP_ORIGIN"
update_env_value "APP_DOMAIN" "$DOMAIN"
update_env_value "ACME_EMAIL" "$ACME_EMAIL"

rm -f "$ENV_FILE.bak"

echo "Updated $ENV_FILE for $APP_ORIGIN"
echo "Recreating the Oracle stack..."

cd "$SCRIPT_DIR"
docker compose up -d --force-recreate backend worker frontend caddy

echo
echo "Current container status:"
docker compose ps

echo
echo "Spotify callback URL:"
echo "  $APP_ORIGIN/api/spotify/callback/"
echo
echo "Next checks:"
echo "  1. DNS A record for $DOMAIN points at the Oracle VM public IP."
echo "  2. Oracle ingress allows TCP 80 and 443."
echo "  3. Spotify app callback URL matches the value above exactly."
