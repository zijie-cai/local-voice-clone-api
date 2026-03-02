#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SERVER_DIR}/.venv"
ENV_FILE="${SERVER_DIR}/.env"
ENV_EXAMPLE="${SERVER_DIR}/.env.example"
WITH_LAUNCHD="${WITH_LAUNCHD:-1}"
USE_CAFFEINATE="${USE_CAFFEINATE:-0}"
PYTHON_BIN="${PYTHON_BIN:-}"

log() { printf '[xtts-install] %s\n' "$*"; }
err() { printf '[xtts-install] ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || err "Missing command: $1"
}

find_python() {
  if [[ -n "${PYTHON_BIN}" ]]; then
    command -v "${PYTHON_BIN}" >/dev/null 2>&1 || err "PYTHON_BIN not found: ${PYTHON_BIN}"
    echo "${PYTHON_BIN}"
    return
  fi

  for candidate in python3.12 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      local major minor
      major="$("${candidate}" -c 'import sys; print(sys.version_info.major)')"
      minor="$("${candidate}" -c 'import sys; print(sys.version_info.minor)')"
      if [[ "${major}" == "3" && "${minor}" -ge 10 && "${minor}" -le 12 ]]; then
        echo "${candidate}"
        return
      fi
    fi
  done
  err "Python 3.10-3.12 is required. Install Python 3.12 and retry."
}

upsert_env() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "${ENV_FILE}"; then
    sed -i.bak -E "s|^${key}=.*|${key}=${value}|" "${ENV_FILE}"
    rm -f "${ENV_FILE}.bak"
  else
    printf '\n%s=%s\n' "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

generate_token() {
  local py="$1"
  "${py}" - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
}

main() {
  [[ "$OSTYPE" == darwin* ]] || err "This installer currently supports macOS only."
  need_cmd awk
  need_cmd sed

  local py
  py="$(find_python)"
  log "Using Python: ${py}"

  if [[ ! -f "${ENV_FILE}" ]]; then
    [[ -f "${ENV_EXAMPLE}" ]] || err ".env.example not found."
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    log "Created ${ENV_FILE} from .env.example"
  fi

  if ! grep -qE '^XTTS_AUTH_TOKEN=' "${ENV_FILE}"; then
    upsert_env "XTTS_AUTH_TOKEN" "$(generate_token "${py}")"
    log "Generated XTTS_AUTH_TOKEN"
  else
    local current
    current="$(awk -F= '/^XTTS_AUTH_TOKEN=/{print $2; exit}' "${ENV_FILE}")"
    if [[ -z "${current}" || "${current}" == "change-me-now" ]]; then
      upsert_env "XTTS_AUTH_TOKEN" "$(generate_token "${py}")"
      log "Replaced placeholder XTTS_AUTH_TOKEN"
    fi
  fi

  if [[ ! -d "${VENV_DIR}" ]]; then
    log "Creating virtual environment at ${VENV_DIR}"
    "${py}" -m venv "${VENV_DIR}"
  fi

  # shellcheck disable=SC1091
  source "${VENV_DIR}/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  pip install -r "${SERVER_DIR}/requirements.txt"
  log "Dependencies installed"

  if ! command -v ffmpeg >/dev/null 2>&1; then
    log "Optional: install ffmpeg for broader audio conversion support (brew install ffmpeg)"
  fi

  if [[ "${WITH_LAUNCHD}" == "1" ]]; then
    local mode
    if [[ "${USE_CAFFEINATE}" == "1" ]]; then
      mode="caffeinate"
    else
      mode="normal"
    fi
    log "Installing launchd agent (${mode})"
    "${SERVER_DIR}/scripts/install_launchd.sh"
  else
    log "Skipping launchd setup (WITH_LAUNCHD=0)"
  fi

  log "Setup complete."
  log "Health check: curl -s http://127.0.0.1:8020/v1/health"
  log "Token: grep '^XTTS_AUTH_TOKEN=' ${ENV_FILE}"
}

main "$@"
