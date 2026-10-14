#!/usr/bin/env bash
# Dev launcher: uvicorn + Vite together. Ctrl-C stops both.
# PORT = frontend port (default 5173), BACKEND_PORT = API port (default 8000).
set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-python3.12}
[ -d .venv ] || { "$PY" -m venv .venv && .venv/bin/pip install -q ".[dev]"; }
[ -d frontend/node_modules ] || (cd frontend && npm install --silent)

export BACKEND_PORT=${BACKEND_PORT:-8000}
.venv/bin/uvicorn backend.main:app --port "$BACKEND_PORT" --reload &
BACKEND=$!
(cd frontend && npx vite --port "${PORT:-5173}" --strictPort) &
FRONTEND=$!
trap 'kill $BACKEND $FRONTEND 2>/dev/null' INT TERM EXIT
wait
