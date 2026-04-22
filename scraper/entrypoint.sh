#!/bin/bash
set -e

export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Download Chromium if missing (first start with empty volume)
if [ ! -d "/ms-playwright/chromium-"* ] 2>/dev/null; then
    echo "📦 Downloading Chromium to persistent volume..."
    python -m playwright install chromium
    echo "✅ Chromium cached!"
fi

exec python scraper.py
