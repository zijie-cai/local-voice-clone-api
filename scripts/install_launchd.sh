#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_AGENTS_DIR}/com.xtts.server.plist"
PLIST_TEMPLATE="${SERVER_DIR}/launchd/com.xtts.server.plist.template"
RUN_SCRIPT="${SERVER_DIR}/scripts/run_server.sh"
C_RUN_SCRIPT="${SERVER_DIR}/scripts/run_server_caffeinate.sh"

USE_CAFFEINATE="${USE_CAFFEINATE:-0}"

log() { printf '[xtts-launchd] %s\n' "$*"; }
err() { printf '[xtts-launchd] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "${PLIST_TEMPLATE}" ]] || err "Missing template: ${PLIST_TEMPLATE}"
[[ -x "${RUN_SCRIPT}" ]] || chmod +x "${RUN_SCRIPT}"
[[ -x "${C_RUN_SCRIPT}" ]] || chmod +x "${C_RUN_SCRIPT}"

mkdir -p "${LAUNCH_AGENTS_DIR}"

RUN_TARGET="${RUN_SCRIPT}"
if [[ "${USE_CAFFEINATE}" == "1" ]]; then
  RUN_TARGET="${C_RUN_SCRIPT}"
fi

sed \
  -e "s|__SERVER_DIR__|${SERVER_DIR}|g" \
  -e "s|__RUN_SCRIPT__|${RUN_TARGET}|g" \
  "${PLIST_TEMPLATE}" > "${PLIST_PATH}"

if launchctl print "gui/$(id -u)/com.xtts.server" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/com.xtts.server" >/dev/null 2>&1 || true
fi

launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl enable "gui/$(id -u)/com.xtts.server"
launchctl kickstart -k "gui/$(id -u)/com.xtts.server"

log "Installed: ${PLIST_PATH}"
log "Status: launchctl print gui/$(id -u)/com.xtts.server"
log "Logs: tail -f /tmp/xtts.out.log /tmp/xtts.err.log"
