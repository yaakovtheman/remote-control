#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAC_SCRIPTS_DIR="$ROOT_DIR/scripts/mac"

START_SCRIPT="$MAC_SCRIPTS_DIR/start_all.sh"
STOP_SCRIPT="$MAC_SCRIPTS_DIR/stop_all.sh"
STATUS_SCRIPT="$MAC_SCRIPTS_DIR/status.sh"

pulse() {
  local msg="$1"
  local i
  for i in 1 2 3; do
    printf "\r⏳ %s %0.s•" "$msg" $(seq 1 "$i")
    sleep 0.2
  done
  printf "\r%-80s\r" ""
  echo "⏳ $msg"
}

banner() {
  clear
  echo "************************************************************"
  echo "* 🚜 Control Center - Mac"
  echo "* Start / Status / Stop / Restart / Cleanup"
  echo "************************************************************"
  echo "* $ROOT_DIR"
  echo "************************************************************"
  echo
}

is_running() {
  local count=0
  pgrep -af "$ROOT_DIR/app/remote_pi_client.py" >/dev/null 2>&1 && count=$((count + 1))
  pgrep -af "$ROOT_DIR/app/settings_server.py" >/dev/null 2>&1 && count=$((count + 1))
  pgrep -af "mediamtx" >/dev/null 2>&1 && count=$((count + 1))
  [[ "$count" -gt 0 ]]
}

status_en() {
  local rp="⛔"
  local ss="⛔"
  local mm="⛔"
  pgrep -af "$ROOT_DIR/app/remote_pi_client.py" >/dev/null 2>&1 && rp="✅"
  pgrep -af "$ROOT_DIR/app/settings_server.py" >/dev/null 2>&1 && ss="✅"
  pgrep -af "mediamtx" >/dev/null 2>&1 && mm="✅"
  echo "[Status] RemotePiClient: $rp"
  echo "[Status] SettingsServer:  $ss"
  echo "[Status] MediaMTX:        $mm"
}

cleanup_ghosts() {
  pulse "Cleaning ghost processes"
  "$STOP_SCRIPT" >/dev/null 2>&1 || true
  pkill -f "remote_pi_client.py" >/dev/null 2>&1 || true
  pkill -f "settings_server.py" >/dev/null 2>&1 || true
  pkill -f "mediamtx" >/dev/null 2>&1 || true
  echo "🧹 Cleanup completed."
}

run_start() {
  pulse "Starting services"
  "$START_SCRIPT"
}

run_start_no_scan() {
  pulse "Starting services (no scan)"
  "$START_SCRIPT" --no-scan
}

run_stop() {
  pulse "Stopping services"
  "$STOP_SCRIPT"
}

run_status() {
  pulse "Collecting status"
  "$STATUS_SCRIPT"
}

menu_loop() {
  while true; do
    banner
    status_en
    echo
    echo "[🎛️] Choose action:"
    echo "  1) ⚡ Quick Start  (use saved IPs, no scan)"
    echo "  2) 🚀 Full Start   (scan network first)"
    echo "  3) 🧾 Status"
    echo "  4) ⏹️  Stop"
    echo "  5) 🔁 Restart      (quick)"
    echo "  6) 🔁 Full Restart (with scan)"
    echo "  7) 🧹 Cleanup ghosts"
    echo "  8) ❌ Exit"
    echo
    read -r -p "Type 1-8 and press Enter: " choice
    case "$choice" in
      1) run_start_no_scan ;;
      2) run_start ;;
      3) run_status ;;
      4) run_stop ;;
      5) run_stop; run_start_no_scan ;;
      6) run_stop; run_start ;;
      7) cleanup_ghosts ;;
      8) echo "👋 Bye."; exit 0 ;;
      *) echo "⚠️ Invalid choice." ;;
    esac
    echo
    read -r -p "Press Enter to continue..." _
  done
}

main() {
  banner
  pulse "Checking system state"
  if is_running; then
    menu_loop
  else
    echo "🤖 No active services detected, starting automatically (Quick Start)..."
    run_start_no_scan
  fi
}

main "$@"
