#!/bin/sh
set -eu

while true; do
  python3 /app/scripts/railway_sync.py || true
  sleep "${SYNC_INTERVAL_SECONDS:-600}"
done &

exec nginx -g "daemon off;"
