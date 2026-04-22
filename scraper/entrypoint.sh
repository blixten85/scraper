#!/bin/bash
set -e

echo "🔧 Fixing permissions for UID:GID = ${PUID}:${PGID}"

# Skapa mappar med rätt ägare
mkdir -p /logs /root/.cache/ms-playwright
chown -R ${PUID}:${PGID} /logs /root/.cache/ms-playwright 2>/dev/null || true

# Ladda ner Chromium om det inte redan finns
if [ ! -d "/root/.cache/ms-playwright/chromium-"* ]; then
    echo "📦 Downloading Chromium for Playwright..."
    python -m playwright install chromium
    echo "✅ Chromium downloaded!"
else
    echo "✅ Chromium already cached!"
fi

exec python scraper.py
