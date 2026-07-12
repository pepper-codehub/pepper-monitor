#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root (for example: sudo -E $0)." >&2
    exit 1
fi

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/webcam-dashboard"
CERT_FILE="${CERT_FILE:-}"
KEY_FILE="${KEY_FILE:-}"
AVATAR_FILE="${AVATAR_FILE:-}"

for command in python3 systemctl; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "Required command not found: ${command}" >&2
        exit 1
    fi
done

for source_file in "${CERT_FILE}" "${KEY_FILE}" "${AVATAR_FILE}"; do
    if [[ -n "${source_file}" && ! -f "${source_file}" ]]; then
        echo "Deployment asset not found: ${source_file}" >&2
        exit 1
    fi
done

if [[ -z "${CERT_FILE}" && ! -f "${INSTALL_DIR}/cert.pem" ]]; then
    echo "Set CERT_FILE to the TLS certificate path for the first deployment." >&2
    exit 1
fi
if [[ -z "${KEY_FILE}" && ! -f "${INSTALL_DIR}/key.pem" ]]; then
    echo "Set KEY_FILE to the TLS private-key path for the first deployment." >&2
    exit 1
fi

install -d -m 0755 "${INSTALL_DIR}/templates"
install -m 0755 \
    "${REPO_ROOT}/remote/server_async_simple_fix.py" \
    "${REPO_ROOT}/remote/ws_audio_proxy_fixed.py" \
    "${INSTALL_DIR}/"
install -m 0644 "${REPO_ROOT}"/remote/templates/*.html "${INSTALL_DIR}/templates/"

if [[ -n "${CERT_FILE}" ]]; then
    install -m 0644 "${CERT_FILE}" "${INSTALL_DIR}/cert.pem"
fi
if [[ -n "${KEY_FILE}" ]]; then
    install -m 0600 "${KEY_FILE}" "${INSTALL_DIR}/key.pem"
fi
if [[ -n "${AVATAR_FILE}" ]]; then
    install -m 0644 "${AVATAR_FILE}" "${INSTALL_DIR}/avatar.jpg"
fi
if [[ ! -e "${INSTALL_DIR}/sessions.json" ]]; then
    install -m 0600 /dev/null "${INSTALL_DIR}/sessions.json"
fi

install -m 0644 "${REPO_ROOT}"/remote/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ws-audio-proxy.service pepper-monitor.service

echo "Remote deployment completed in ${INSTALL_DIR}."
