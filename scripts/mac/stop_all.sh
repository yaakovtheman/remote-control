#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="$ROOT_DIR/app"

pkill -f "$APP_DIR/remote_pi_client.py" || true
pkill -f "$APP_DIR/settings_server.py" || true
pkill -f "mediamtx" || true

sleep 0.3

pgrep -af "$APP_DIR/remote_pi_client.py" >/dev/null 2>&1 && pkill -9 -f "$APP_DIR/remote_pi_client.py" || true
pgrep -af "$APP_DIR/settings_server.py" >/dev/null 2>&1 && pkill -9 -f "$APP_DIR/settings_server.py" || true
pgrep -af "mediamtx" >/dev/null 2>&1 && pkill -9 -f "mediamtx" || true

echo "Stopped."
