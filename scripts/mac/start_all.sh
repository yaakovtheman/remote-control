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
APP_DIR="$ROOT_DIR/app"

VENV_PY="$ROOT_DIR/.venv/bin/python"
FIND_CAMERAS_PY="$APP_DIR/find_cameras.py"
MEDIAMTX_BIN="/opt/homebrew/bin/mediamtx"
MEDIAMTX_CFG="$APP_DIR/mediamtx.yml"
CONFIG_JSON="$APP_DIR/config.json"

CAM_USER="admin"
CAM_PASS="Aa123456!"
PI_IP=""
CAM_COUNT="0"
SUBNETS="unknown"
TARGET_URL=""

step() {
  echo
  echo "[*] ========================================================="
  echo "[*] $1"
  echo "[*] ========================================================="
}

ok() { echo "[OK] $1"; }
warn() { echo "[WARN] $1"; }
info() { echo "[INFO] $1"; }
fail() {
  echo
  echo "************************************************************"
  echo "* FAIL: $1"
  echo "************************************************************"
  exit 1
}

pulse() {
  local msg="$1"
  local i
  for i in 1 2 3; do
    printf "\r... %s %0.s*" "$msg" $(seq 1 "$i")
    sleep 0.25
  done
  printf "\r%-80s\r" ""
  echo "... $msg"
}

clear
echo "************************************************************"
echo "* ⭐ CONTROL LAUNCHER - MAC ⭐"
echo "* Smart startup with live status and progress details"
echo "************************************************************"
echo "* Project folder: $ROOT_DIR"
echo "************************************************************"

step "Environment checks"
[[ -x "$VENV_PY" ]] || fail "venv python not found: $VENV_PY"
[[ -f "$FIND_CAMERAS_PY" ]] || fail "find_cameras.py not found: $FIND_CAMERAS_PY"
[[ -f "$APP_DIR/remote_pi_client.py" ]] || fail "remote_pi_client.py not found"
[[ -f "$APP_DIR/settings_server.py" ]] || fail "settings_server.py not found"
ok "Required files were found"

step "Cleanup old processes and logs"
pkill -f "$APP_DIR/remote_pi_client.py" >/dev/null 2>&1 || true
pkill -f "$APP_DIR/settings_server.py" >/dev/null 2>&1 || true
pkill -f "mediamtx" >/dev/null 2>&1 || true
rm -f "$LOG_DIR/remote_pi_client.log" "$LOG_DIR/settings_server.log" "$LOG_DIR/mediamtx.log" "$APP_DIR/status.json"
ok "Cleanup complete"

if [[ "$LOCAL_MODE" -eq 1 ]]; then
  step "Local mode (--local)"
  info "Skipping Pi/camera discovery"
  if [[ -f "$MEDIAMTX_CFG" ]]; then
    ok "Using existing MediaMTX config: $MEDIAMTX_CFG"
  else
    echo "paths: {}" > "$MEDIAMTX_CFG"
    warn "mediamtx.yml missing, created fallback config"
  fi
else
  SUBNETS="$("$VENV_PY" -c 'import pathlib, sys; sys.path.insert(0, str(pathlib.Path("'"$APP_DIR"'"))); import find_cameras as fc; _, nets, _ = fc.get_hosts(); print(", ".join(nets) if nets else "unknown")' 2>/dev/null || echo "unknown")"

  step "Find Raspberry Pi and update config.json"
  IFS=',' read -ra PI_SUBNET_LIST <<< "$SUBNETS"
  for subnet in "${PI_SUBNET_LIST[@]}"; do
    trimmed="$(echo "$subnet" | xargs)"
    [[ -n "$trimmed" ]] && info "Pi scan: checking segment $trimmed"
  done
  pulse "Running Pi scan"
  "$VENV_PY" "$FIND_CAMERAS_PY" --pi --pretty || warn "Pi scan failed, continuing anyway"

  PI_IP="$("$VENV_PY" -c 'import json, pathlib; p=pathlib.Path("'"$CONFIG_JSON"'"); print(json.loads(p.read_text(encoding="utf-8")).get("server_ip",""))' 2>/dev/null || true)"
  if [[ -n "$PI_IP" ]]; then
    ok "Pi IP set to: $PI_IP"
  else
    warn "No Pi IP found in config.json"
  fi

  step "Scan cameras and build mediamtx.yml"
  IFS=',' read -ra CAM_SUBNET_LIST <<< "$SUBNETS"
  for subnet in "${CAM_SUBNET_LIST[@]}"; do
    trimmed="$(echo "$subnet" | xargs)"
    [[ -n "$trimmed" ]] && info "Camera scan: checking segment $trimmed"
  done
  pulse "Searching cameras in network"
  CAM_SCAN_RAW="$("$VENV_PY" "$FIND_CAMERAS_PY" --cam 2>/dev/null || true)"

  SCAN_SUMMARY="$(
    CAM_SCAN_RAW_JSON="$CAM_SCAN_RAW" "$VENV_PY" - "$MEDIAMTX_CFG" "$CAM_USER" "$CAM_PASS" <<'PY'
import json, os, pathlib, sys

cfg_path = pathlib.Path(sys.argv[1])
user = sys.argv[2]
pw = sys.argv[3]
raw = os.environ.get("CAM_SCAN_RAW_JSON", "").strip()

count = 0
subnets = []
cams = []
data = {}

if raw:
    try:
        data = json.loads(raw)
    except Exception:
        data = {}

if isinstance(data, dict):
    subnets = data.get("subnets", []) or []
    cams = data.get("cameras", []) or []

lines = ["paths:"]
i = 1
for cam in cams:
    ip = cam.get("ip")
    if not ip:
        continue
    lines.extend([
        f"  cam{i}:",
        f"    source: rtsp://{user}:{pw}@{ip}:554/profile2",
        "    rtspTransport: tcp",
    ])
    i += 1

count = i - 1
if count == 0:
    cfg_path.write_text("paths: {}\n", encoding="utf-8")
else:
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(f"CAM_COUNT={count}")
print(f"SUBNETS={', '.join(subnets) if subnets else 'unknown'}")
PY
  )"

  while IFS='=' read -r k v; do
    [[ -z "${k:-}" ]] && continue
    case "$k" in
      CAM_COUNT) CAM_COUNT="$v" ;;
      SUBNETS) SUBNETS="$v" ;;
    esac
  done <<< "$SCAN_SUMMARY"

  info "Found $CAM_COUNT cameras"
  if [[ "$CAM_COUNT" == "0" ]]; then
    warn "No cameras found - fallback MediaMTX config was created"
  else
    ok "Built MediaMTX config with $CAM_COUNT cameras"
  fi
fi

step "Start services"
nohup "$VENV_PY" "$APP_DIR/remote_pi_client.py" \
  >> "$LOG_DIR/remote_pi_client.log" 2>&1 &
ok "remote_pi_client.py started (log: logs/remote_pi_client.log)"

nohup "$VENV_PY" "$APP_DIR/settings_server.py" \
  >> "$LOG_DIR/settings_server.log" 2>&1 &
ok "settings_server.py started (log: logs/settings_server.log)"

if [[ -x "$MEDIAMTX_BIN" && -f "$MEDIAMTX_CFG" ]]; then
  nohup "$MEDIAMTX_BIN" "$MEDIAMTX_CFG" \
    >> "$LOG_DIR/mediamtx.log" 2>&1 &
  ok "MediaMTX started"
else
  warn "MediaMTX not started (missing binary/config)"
  echo "MediaMTX not started (missing $MEDIAMTX_BIN or $MEDIAMTX_CFG)" \
    >> "$LOG_DIR/mediamtx.log"
fi

step "Check web server and open browser"
if [[ -n "$PI_IP" ]]; then
  TARGET_URL="http://${PI_IP}:8088/"
else
  TARGET_URL="http://127.0.0.1:8088/"
fi

info "Target URL: $TARGET_URL"
HTTP_CODE="$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$TARGET_URL" || true)"
if [[ "$HTTP_CODE" =~ ^2|3 ]]; then
  ok "HTTP check succeeded: $HTTP_CODE"
else
  warn "HTTP check returned: ${HTTP_CODE:-ERR}"
fi
open "$TARGET_URL" >/dev/null 2>&1 || warn "Could not open browser automatically"

echo
echo "************************************************************"
echo "* ✅ Startup completed"
echo "* Pi IP: ${PI_IP:-not found}"
echo "* Cameras: $CAM_COUNT"
echo "* Subnets: $SUBNETS"
echo "* Browser: $TARGET_URL"
echo "* Logs: $LOG_DIR"
echo "************************************************************"