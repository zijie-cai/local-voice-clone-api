#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${0}")" && pwd)"
SERVER_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "$SERVER_DIR"
source .venv/bin/activate
exec caffeinate -dimsu uvicorn app.main:app --host "${XTTS_HOST:-0.0.0.0}" --port "${XTTS_PORT:-8020}" --workers 1
