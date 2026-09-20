#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" -m py_compile \
  judicex_memory_os/agent_runtime.py \
  judicex_memory_os/store.py \
  judicex_memory_os/web_app.py \
  judicex_memory_os/llm_provider.py \
  judicex_memory_os/stream_runner.py \
  judicex_memory_os/ollama_agent.py \
  judicex_memory_os/cli.py \
  scripts/run_public_benchmark.py

if command -v node >/dev/null 2>&1; then
  node --check judicex_memory_os/static/app.js
fi

"$PYTHON_BIN" -m unittest discover -s tests
