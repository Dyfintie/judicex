#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

DB="${JUDICEX_DB:-./memory.db}"
AREA="${JUDICEX_AREA:-civile}"
BIND="${JUDICEX_BIND:-127.0.0.1}"
PORT="${JUDICEX_PORT:-5051}"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m judicex_memory_os.web_app --db "$DB" --area "$AREA" --bind "$BIND" --port "$PORT"
