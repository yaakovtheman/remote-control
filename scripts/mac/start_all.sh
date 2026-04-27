#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

LOCAL_MODE=0
for arg in "$@"; do
  case "$arg" in
    --local)
      LOCAL_MODE=1
      ;;
  esac
done

mkdir -p logs
LOG_DIR="$ROOT_DIR/logs"

VENV_PY="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python not found at $VENV_PY"
  exit 1
fi

echo "Starting from $ROOT_DIR"
date

APP_DIR="$ROOT_DIR/app"

CAM_USER="admin"
CAM_PASS="Aa123456!"

FIND_CAMERAS_PY="$APP_DIR/find_cameras.py"
MEDIAMTX_BIN="/opt/homebrew/bin/mediamtx"
MEDIAMTX_CFG="$APP_DIR/mediamtx.yml"

pkill -f "$APP_DIR/remote_pi_client.py" >/dev/null 2>&1 || true
pkill -f "$APP_DIR/settings_server.py" >/dev/null 2>&1 || true
pkill -f "mediamtx" >/dev/null 2>&1 || true

if [[ "$LOCAL_MODE" -eq 1 ]]; then
  echo "Local mode enabled (--local): skipping Pi/camera discovery."
  if [[ -f "$MEDIAMTX_CFG" ]]; then
    echo "Using existing MediaMTX config: $MEDIAMTX_CFG"
  else
    echo "WARNING: $MEDIAMTX_CFG not found. MediaMTX may not start." | tee -a "$LOG_DIR/mediamtx.log"
  fi
else
  CAMERA_IPS="$("$VENV_PY" "$FIND_CAMERAS_PY" | "$VENV_PY" -c '
import sys, json
data = json.load(sys.stdin)
cams = data.get("cameras", [])
for cam in cams:
    print(cam["ip"])
')"

  if [[ -n "${CAMERA_IPS}" ]]; then
    echo "Discovered cameras:"
    echo "${CAMERA_IPS}"

    {
      echo "paths:"
      i=1
      while IFS= read -r ip; do
        [[ -z "$ip" ]] && continue
        echo "  cam${i}:"
        echo "    source: rtsp://${CAM_USER}:${CAM_PASS}@${ip}:554/profile1"
        echo "    rtspTransport: tcp"
        i=$((i + 1))
      done <<< "$CAMERA_IPS"
    } > "$MEDIAMTX_CFG"

    echo "Updated $MEDIAMTX_CFG"
  else
    echo "WARNING: no cameras found. MediaMTX config not updated." | tee -a "$LOG_DIR/mediamtx.log"
  fi
fi

nohup "$VENV_PY" "$APP_DIR/remote_pi_client.py" \
  >> "$LOG_DIR/remote_pi_client.log" 2>&1 &

nohup "$VENV_PY" "$APP_DIR/settings_server.py" \
  >> "$LOG_DIR/settings_server.log" 2>&1 &

if [[ -x "$MEDIAMTX_BIN" && -f "$MEDIAMTX_CFG" ]]; then
  nohup "$MEDIAMTX_BIN" "$MEDIAMTX_CFG" \
    >> "$LOG_DIR/mediamtx.log" 2>&1 &
else
  echo "MediaMTX not started (missing $MEDIAMTX_BIN or $MEDIAMTX_CFG)" \
    >> "$LOG_DIR/mediamtx.log"
fi

echo "Done. Logs in: $LOG_DIR"