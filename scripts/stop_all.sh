#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

pkill -f "$ROOT_DIR/remote_pi_client.py" || true
pkill -f "$ROOT_DIR/settings_server.py" || true
pkill -f "mediamtx" || true

echo "Stopped."
