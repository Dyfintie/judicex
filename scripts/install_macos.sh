#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/Judicex}"
PORT="${PORT:-5050}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v python3 >/dev/null 2>&1 || {
  echo "Python 3.11+ is required. Install it with Homebrew or python.org." >&2
  exit 1
}

mkdir -p "$INSTALL_DIR"
cd "$ROOT_DIR"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/.venv/bin/python" -m pip install -e ".[crypto]"

cat > "$INSTALL_DIR/run_judicex.command" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export JUDICEX_DB="\$HOME/Judicex/memory.db"
"$INSTALL_DIR/.venv/bin/python" -m judicex_memory_os.web_app --db "\$JUDICEX_DB" --area civile --bind 127.0.0.1 --port "$PORT"
EOF
chmod +x "$INSTALL_DIR/run_judicex.command"

echo "Done. Start Judicex with:"
echo "  $INSTALL_DIR/run_judicex.command"
echo "Then open http://127.0.0.1:$PORT"
