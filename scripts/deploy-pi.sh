#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -eq 0 ]]; then
    echo "Run this script as the Raspberry Pi login user, not root." >&2
    exit 1
fi

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${HOME}/.local/share/pepper-monitor"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/pepper-monitor"
UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
TUNNEL_ENV="${CONFIG_DIR}/tunnel.env"

for command in python3 ffmpeg ffplay ssh systemctl; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "Required command not found: ${command}" >&2
        exit 1
    fi
done

mkdir -p "${INSTALL_DIR}/pi/scripts" "${CONFIG_DIR}" "${UNIT_DIR}"

python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/python" -m pip install --upgrade pip
"${INSTALL_DIR}/venv/bin/python" -m pip install -r "${REPO_ROOT}/requirements.txt"

install -m 0755 "${REPO_ROOT}"/pi/scripts/*.py "${INSTALL_DIR}/pi/scripts/"
install -m 0644 \
    "${REPO_ROOT}/pi/systemd/pepper-camera-pi.service" \
    "${REPO_ROOT}/pi/systemd/pepper-monitor-pi.service" \
    "${REPO_ROOT}/pi/systemd/rainyun-tunnel.service" \
    "${UNIT_DIR}/"

if [[ ! -e "${HOME}/.asoundrc" ]]; then
    install -m 0644 "${REPO_ROOT}/pi/asoundrc" "${HOME}/.asoundrc"
    echo "Installed the repository ALSA configuration at ${HOME}/.asoundrc."
else
    echo "Keeping existing ${HOME}/.asoundrc."
fi

if [[ ! -e "${TUNNEL_ENV}" ]]; then
    install -m 0600 "${REPO_ROOT}/pi/tunnel.env.example" "${TUNNEL_ENV}"
    echo "Created ${TUNNEL_ENV}; update it before enabling rainyun-tunnel.service."
fi

systemctl --user daemon-reload
systemctl --user enable --now pepper-camera-pi.service pepper-monitor-pi.service

if ! grep -q 'monitor\.example\.com' "${TUNNEL_ENV}"; then
    systemctl --user enable --now rainyun-tunnel.service
else
    echo "SSH tunnel wasn't enabled because ${TUNNEL_ENV} still has example values."
fi

echo "Pi deployment completed in ${INSTALL_DIR}."
