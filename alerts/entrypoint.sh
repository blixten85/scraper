#!/bin/bash
set -e

echo "🔧 Fixing permissions for UID:GID = ${PUID}:${PGID}"

# Create /logs with correct permissions
mkdir -p /logs
chown -R ${PUID}:${PGID} /logs 2>/dev/null || true

exec python alerts.py
