#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

INVENTORY="${PROJECT_ROOT}/02_ansible_setup/inventories/public.ini"
PLAYBOOK="${SCRIPT_DIR}/site_cleanup_legacy_basic_auth.yml"
OUTPUT="${SCRIPT_DIR}/cleanup_legacy_basic_auth_output.txt"

if [[ -f "${PROJECT_ROOT}/02_ansible_setup/ansible.cfg" ]]; then
    export ANSIBLE_CONFIG="${PROJECT_ROOT}/02_ansible_setup/ansible.cfg"
fi

args=(
    ansible-playbook
    -i "${INVENTORY}"
    "${PLAYBOOK}"
    --limit ubuntu_public
    --ask-become-pass
    -v
)

if [[ "${ASK_SSH_PASSWORD:-0}" == "1" ]]; then
    args+=(--ask-pass)
fi

"${args[@]}" 2>&1 | tee "${OUTPUT}"
