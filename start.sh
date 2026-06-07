#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh — Container entry point
# Substitutes $PORT from Render.com env var into nginx config, then starts
# supervisord which manages all processes.
# ─────────────────────────────────────────────────────────────────────────────
set -e

# Render.com injects PORT; default to 8080 for local testing
export PORT="${PORT:-8080}"

echo "[start.sh] Listening on port: $PORT"

# Generate nginx.conf from template (substitutes LISTEN_PORT placeholder)
sed "s/LISTEN_PORT/${PORT}/g" /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

echo "[start.sh] nginx config generated"
echo "[start.sh] Starting supervisord..."

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
