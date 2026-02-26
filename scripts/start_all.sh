#!/usr/bin/env bash
set -euo pipefail

# repo root = parent of scripts/
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs
LOG_DIR="$ROOT_DIR/logs"

VENV_PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python not found at $VENV_PY"
  exit 1
fi

echo "Starting from $ROOT_DIR"
date

# Stop old ones (safe if nothing running)
pkill -f "$ROOT_DIR/remote_pi_client.py" >/dev/null 2>&1 || true
pkill -f "$ROOT_DIR/settings_server.py" >/dev/null 2>&1 || true
pkill -f "mediamtx" >/dev/null 2>&1 || true

# 1) Remote client
nohup "$VENV_PY" "$ROOT_DIR/remote_pi_client.py" \
  >> "$LOG_DIR/remote_pi_client.log" 2>&1 &

# 2) Web config server
nohup "$VENV_PY" "$ROOT_DIR/settings_server.py" \
  >> "$LOG_DIR/settings_server.log" 2>&1 &

# 3) MediaMTX (if you use it on the Mac)
# If you run MediaMTX some other way, remove this block.
MEDIAMTX_BIN="/opt/homebrew/bin/mediamtx"
MEDIAMTX_CFG="$ROOT_DIR/mediamtx.yml"

if [[ -x "$MEDIAMTX_BIN" && -f "$MEDIAMTX_CFG" ]]; then
  nohup "$MEDIAMTX_BIN" "$MEDIAMTX_CFG" \
    >> "$LOG_DIR/mediamtx.log" 2>&1 &
else
  echo "MediaMTX not started (missing $MEDIAMTX_BIN or $MEDIAMTX_CFG)" \
    >> "$LOG_DIR/mediamtx.log"
fi

echo "Done. Logs in: $LOG_DIR"
