# 🕷️ Web Scraper Platform

[![Build and Push Images](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Lättviktig, konfigurerbar web scraping-plattform med WebUI, API och prisbevakning.

## ✨ Funktioner

- 🔍 Multi-site scraping - Skrapa valfri e-handelssida med CSS-selektorer
- 🮎 WebUI - Konfigurera och övervaka via webbgränssnitt (port 3000)
- 🡠 REST API - Hämta data programmatiskt (port 8000)
- 🔶 Prisbevakning - Discord-notiser vid prisfall
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

## 🦆 Tjänster (Docker)

| Tjänst | Port | Beskrivning |
|--------|-----|-----------|
| scraper_engine | 5001 | Huvudmotor - skrapar sajter |
| scraper_api | 8000 | REST API + Swagger docs |
| scraper_webui | 3000 | Webbgränssnitt |
| scraper_alerts | - | Discord-notiser |

## 🣡 API Exempel

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

## 🤢 Konfiguration (.env)

```bash
WEBUI_PORT=3000
API_PORT=8000
CONCURRENT_PAGES=3
SCRAPE_INTERVAL=3600
MIN_DROP_PERCENT=5
MIN_DROP_AMOUNT=100
COOLDOWN_HOURS=24
```

## 📥 Licens

MIT - se [Licens](Licens)
