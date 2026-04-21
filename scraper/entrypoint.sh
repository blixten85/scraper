#!/bin/bash
set -e

echo "🔧 Fixing permissions for UID:GID = ${PUID}:${PGID}"

mkdir -p /logs /root/.cache/ms-playwright
chown -R ${PUID}:${PGID} /logs /root/.cache/ms-playwright 2>/dev/null || true

exec python scraper.py
