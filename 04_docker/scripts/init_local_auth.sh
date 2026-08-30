#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${PROJECT_DIR}/secrets"
BACKEND_GID="${BACKEND_GID:-10001}"

mkdir -p "${SECRETS_DIR}"
touch "${SECRETS_DIR}/.gitkeep"

generate_secret() {
    local path="$1"
    local bytes="$2"

    if [[ ! -s "${path}" ]]; then
        umask 077
        openssl rand -hex "${bytes}" > "${path}"
        echo "Generated: ${path}"
    else
        echo "Preserved: ${path}"
    fi
}

generate_secret "${SECRETS_DIR}/db_password.txt" 24
generate_secret "${SECRETS_DIR}/flask_secret_key.txt" 32
generate_secret "${SECRETS_DIR}/app_admin_password.txt" 24

sudo chown root:"${BACKEND_GID}" \
    "${SECRETS_DIR}/db_password.txt" \
    "${SECRETS_DIR}/flask_secret_key.txt" \
    "${SECRETS_DIR}/app_admin_password.txt"

sudo chmod 0640 \
    "${SECRETS_DIR}/db_password.txt" \
    "${SECRETS_DIR}/flask_secret_key.txt" \
    "${SECRETS_DIR}/app_admin_password.txt"

echo
echo "Local authentication secrets are ready."
echo "Application admin username: ${APP_ADMIN_USERNAME:-admin}"
echo "Application admin password:"
sudo cat "${SECRETS_DIR}/app_admin_password.txt"
