## 🕷️ WEB Scraper Playform
[![Build and Push Images](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Lättviktig, konfigurerbar web scraping-plattform med WebUI, API och prisbevakning.

## ✨ Funktioner

- 🔍 Multi-site scraping - Skrapa valfri e-handelssida med CSS-selektorer
- 🎨 WebUI - Konfigurera och övervaka via webbgränssnitt (port 3000)
- 📡 REST API - Hämta data programmatiskt (port 8000)
- 📉 Prisbevakning - Discord-notiser vid prisfall
- 💾 SQLite - Enkel, filbaserad databas - ingen extra infrastruktur
- 🐳 Docker - Kör allt med en docker compose up

## 🚀 Snabbstart - Docker (Full plattform)

```bash
git clone https://github.com/blixten85/scraper.git
cd scraper
mkdir -p secrets data logs
echo "din-discord-webhook-url" > secrets/discord_webhook.txt
docker compose up -d
```

Öppna sedan: `http://localhost:3000`

## 🚀 Snabbstart - Enkel Python-scraper (bara .txt)

```bash
pip install playwright
playwright install chromium
```

Redigera `simple_scraper.py` och ändra URLen:

```python
CONFIG = {
    "url": "https://www.inet.se/kategori/datorkomponenter",
    "max_products": 50,
    "output_file": "products.txt"
}
```

Kör:

```bash
python simple_scraper.py
```

### Färdiga konfigurationer

- `Inet.se:` product_selector="a[href*='/produkt/']", price_selector="text=/\d[\d\s]*\s*kr/"
- `Komplett.se:` product_selector="div.product-list-item", price_selector="span.product-price-now"
- `Webhallen.com:` product_selector="div.product-item", price_selector="span.price"

## 📦 Tjänster (Docker)

| Tjänst | Port | Beskrivning |
|--------|-----|-----------|
| scraper_engine | 5001 | Huvudmotor - skrapar sajter |
| scraper_api | 8000 | REST API + Swagger docs |
| scraper_webui | 3000 | Webbgränssnitt |
| scraper_alerts | - | Discord-notiser |

## 📡 API Exempel

```bash
# Hämta alla produkter
curl http://localhost:8000/products

# Söck produkter
curl "http://localhost:8000/products?search=RTX"

# Hämta prisfall
curl http://localhost:8000/deals?min_drop_percent=10

# Exportera till CSV
curl http://localhost:8000/export/csv > produkter.csv
```

API-dokumentation: `http://localhost:8000/docs`

## 🔧 Konfiguration (.env)

```bash
# =========================
# DATA DIRECTORY
# =========================
DOCKER=/path/to/docker/data
CONFIG=/path/to/config

# =========================
# SCRAPER CONFIGURATION
# =========================
CONCURRENT_PAGES=3
HEADLESS=true
SCRAPE_INTERVAL=3600

# =========================
# ALERTS CONFIGURATION
# =========================
ALERT_CHECK_INTERVAL=1800
MIN_DROP_PERCENT=5
MIN_DROP_AMOUNT=100
COOLDOWN_HOURS=24

# =========================
# PORTS
# =========================
WEBUI_PORT=3000
API_PORT=8000
DOMAIN=example.com
```

## 📜 docker-compose.yml

```bash
version: "3.9"

services:
  scraper:
    image: ghcr.io/blixten85/scraper:latest
    container_name: scraper_engine
    restart: unless-stopped
    pull_policy: always
    security_opt:
      - no-new-privileges:true
    environment:
      TZ: ${TZ}
      PUID: ${PUID}
      PGID: ${PGID}
      SCRAPER_DATA_PATH: /data
      CONCURRENT_PAGES: ${CONCURRENT_PAGES:-3}
      HEADLESS: ${HEADLESS:-true}
      SCRAPE_INTERVAL: ${SCRAPE_INTERVAL:-3600}
    volumes:
      - ${DOCKER}/scraper:/data
      - ${DOCKER}/scraper/logs:/logs
      - ${DOCKER}/scraper/playwright-cache:/root/.cache/ms-playwright  # ← NY!
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
      interval: 60s
      timeout: 10s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    network_mode: "service:gluetun"
    depends_on:
      - gluetun

  api:
    image: ghcr.io/blixten85/scraper-api:latest
    container_name: scraper_api
    restart: unless-stopped
    pull_policy: always
    security_opt:
      - no-new-privileges:true
    environment:
      TZ: ${TZ}
      PUID: ${PUID}
      PGID: ${PGID}
      DB_FILE: /data/products.db
    volumes:
      - ${DOCKER}/scraper:/data:ro
    #ports:
      #- "${API_PORT:-8000}:8000"
    networks:
      - scraper_net
    depends_on:
      scraper:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  webui:
    image: ghcr.io/blixten85/scraper-webui:latest
    container_name: scraper_webui
    restart: unless-stopped
    pull_policy: always
    security_opt:
      - no-new-privileges:true
    environment:
      TZ: ${TZ}
      PUID: ${PUID}
      PGID: ${PGID}
      DB_FILE: /data/products.db
      SCRAPER_API: http://gluetun:5001   # <-- VIKTIGT! Använd gluetun!
    volumes:
      - ${DOCKER}/scraper:/data:rw
    #ports:
      #- "${WEBUI_PORT:-3000}:3000"
    networks:
      - scraper_net
    depends_on:
      - scraper
      - api
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    labels:
      swag: "enable"
      swag_address: "scraper_webui"
      swag_port: "3000"
      swag_url: "scraper.${DOMAIN}"

  alerts:
    image: ghcr.io/blixten85/scraper-alerts:latest
    container_name: scraper_alerts
    restart: unless-stopped
    pull_policy: always
    security_opt:
      - no-new-privileges:true
    environment:
      TZ: ${TZ}
      PUID: ${PUID}
      PGID: ${PGID}
      DB_FILE: /data/products.db
      DISCORD_WEBHOOK_FILE: /run/secrets/discord_webhook
      CHECK_INTERVAL: ${ALERT_CHECK_INTERVAL:-1800}
      MIN_DROP_PERCENT: ${MIN_DROP_PERCENT:-5}
      MIN_DROP_AMOUNT: ${MIN_DROP_AMOUNT:-100}
      COOLDOWN_HOURS: ${COOLDOWN_HOURS:-24}
    volumes:
      - ${DOCKER}/scraper:/data
      - ${DOCKER}/scraper/logs:/logs
    secrets:
      - discord_webhook
    networks:
      - scraper_net
    depends_on:
      scraper:
        condition: service_healthy
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

networks:
  scraper_net:
    driver: bridge
    name: scraper_net

secrets:
  discord_webhook:
    file: ${CONFIG}/.secrets/discord_webhook
```

## 📝 Licens

MIT - se [Licens](Licens)
