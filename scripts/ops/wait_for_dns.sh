#!/usr/bin/env bash
set -euo pipefail

HOSTNAME="${1:?usage: wait_for_dns.sh <hostname> <expected_ip> [attempts] [sleep_seconds]}"
EXPECTED_IP="${2:?usage: wait_for_dns.sh <hostname> <expected_ip> [attempts] [sleep_seconds]}"
ATTEMPTS="${3:-30}"
SLEEP_SECONDS="${4:-10}"

echo "Waiting for DNS: ${HOSTNAME} -> ${EXPECTED_IP}"

for ((i=1; i<=ATTEMPTS; i++)); do
  resolved="$(dig +short "$HOSTNAME" | tail -n 1 | tr -d '[:space:]')"
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if [[ "$resolved" == "$EXPECTED_IP" ]]; then
    echo "${ts} OK ${HOSTNAME} resolves to ${resolved}"
    exit 0
  fi
  echo "${ts} attempt ${i}/${ATTEMPTS}: got '${resolved:-<empty>}'"
  sleep "$SLEEP_SECONDS"
done

echo "DNS did not resolve to expected IP in time."
exit 1
