#!/bin/bash
set -e
export PORT="${PORT:-8080}"
echo "[start.sh] PORT=$PORT"
exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
