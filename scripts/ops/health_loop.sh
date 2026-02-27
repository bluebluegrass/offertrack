#!/usr/bin/env bash
set -euo pipefail

URL="${1:-https://api.offertrack.simona.life/health}"
INTERVAL="${2:-60}"

echo "Health loop started for: ${URL} (interval: ${INTERVAL}s)"
echo "Press Ctrl+C to stop."

while true; do
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if body="$(curl -fsS --max-time 20 "$URL" 2>/dev/null)"; then
    echo "${ts} OK ${body}"
  else
    echo "${ts} FAIL"
  fi
  sleep "$INTERVAL"
done
