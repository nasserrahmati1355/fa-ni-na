#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

INVENTORY="${PROJECT_ROOT}/02_ansible_setup/inventories/public.ini"
PLAYBOOK="${SCRIPT_DIR}/site_verify_after_arvan.yml"

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

"${args[@]}"
