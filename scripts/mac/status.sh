#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== Control stack status =="
echo "Root: $ROOT_DIR"
echo

check_proc () {
  local name="$1"
  local pattern="$2"

  local out=""
  out="$(pgrep -af "$pattern" || true)"

  if [[ -n "$out" ]]; then
    echo "✔ $name: RUNNING"
    echo "$out"
  else
    echo "✘ $name: NOT RUNNING"
  fi
  echo
}

check_proc "Remote client" "$ROOT_DIR/remote_pi_client.py"
check_proc "Web config server" "$ROOT_DIR/settings_server.py"
check_proc "MediaMTX" "mediamtx"

echo "== Listening ports =="
PORTS=(7000 8088 8889)

if command -v lsof >/dev/null 2>&1; then
  any=0
  for p in "${PORTS[@]}"; do
    if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      any=1
      echo "--- :$p ---"
      lsof -nP -iTCP:"$p" -sTCP:LISTEN
      echo
    fi
  done
  [[ "$any" -eq 1 ]] || echo "No expected ports listening"
else
  echo "lsof not found; install Xcode Command Line Tools or use netstat."
fi

echo
echo "== Recent logs (last 8 lines) =="
shopt -s nullglob
for f in "$ROOT_DIR"/logs/*.log; do
  echo "--- $(basename "$f") ---"
  tail -n 8 "$f" || true
  echo
done
