#!/bin/sh
set -eu

python3 /app/scripts/railway_sync.py

while true; do
  sleep "${SYNC_INTERVAL_SECONDS:-600}"
  python3 /app/scripts/railway_sync.py || true
done &

exec nginx -g "daemon off;"
