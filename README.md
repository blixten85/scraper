# 🕷️ Web Scraper Platform

[![Build and Push Images](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Produktionsredo web scraping-plattform med PostgreSQL, WebUI, REST API och prisbevakning.**

---

## ✨ Funktioner

| Funktion | Beskrivning |
|----------|-------------|
| 🔍 **Multi-site scraping** | Skrapa valfri e-handelssida med CSS-selektorer |
| 🎨 **WebUI** | Konfigurera och övervaka via webbgränssnitt |
| 📡 **REST API** | Hämta data programmatiskt med API-nyckel |
| 🔔 **Prisbevakning** | Discord-notiser vid prisfall |
| 🐘 **PostgreSQL** | Robust databas för produktion |
| 🐳 **Docker** | Kör allt med en docker compose up |
| 🔒 **Säkerhet** | API-autentisering, secrets, no-new-privileges |

---

## 🚀 Snabbstart - Docker (Full plattform)

```bash
# 1. Klona repot
git clone https://github.com/blixten85/scraper.git
cd scraper

# 2. Skapa .env-fil med dina inställningar
cp .env.example .env
nano .env

# 3. Skapa mappar och sätt rättigheter
mkdir -p ${DOCKER}/scraper/{logs,postgres,playwright-cache}
sudo chown -R 999:999 ${DOCKER}/scraper/postgres

# 4. Skapa Discord webhook (valfritt)
echo "din-discord-webhook-url" > ${CONFIG}/.secrets/discord_webhook

# 5. Starta
docker compose up -d

# 6. Öppna WebUI
# http://localhost:3000
```

---

🚀 Snabbstart - Enkel Python-scraper (bara .txt)

```bash
pip install playwright
playwright install chromium
```

Redigera simple_scraper.py:

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

Färdiga konfigurationer

Sajt product_selector price_selector
Inet.se a[href*='/produkt/'] text=/\d[\d\s]*\s*kr/
Komplett.se div.product-list-item span.product-price-now
Webhallen.com div.product-item span.price

---

📦 Tjänster (Docker)

Tjänst Port Beskrivning
scraper_db 5432 (intern) PostgreSQL-databas
scraper_engine 5001 (intern) Huvudmotor - skrapar sajter
scraper_api 8000 REST API + Swagger docs
scraper_webui 3000 Webbgränssnitt
scraper_alerts - Discord-notiser

---

🔐 Generera API-nyckel och lösenord

API-nyckel

```bash
# Generera en slumpmässig API-nyckel
openssl rand -base64 48
```

Databaslösenord

```bash
# Generera ett säkert lösenord
openssl rand -hex 16
```

Discord Webhook

1. Gå till din Discord-server → Kanalkugghjul → Integrationer → Webhooks
2. Skapa ny webhook och kopiera URL:en
3. Spara: echo "url" > ${CONFIG}/.secrets/discord_webhook

---

📡 API Exempel

OBS: API:et kräver X-API-Key header för alla endpoints utom /health och /docs.

```bash
# Hämta alla produkter
curl -H "X-API-Key: ${API_KEY}" http://localhost:8000/products

# Sök produkter
curl -H "X-API-Key: ${API_KEY}" "http://localhost:8000/products?search=RTX"

# Hämta prisfall
curl -H "X-API-Key: ${API_KEY}" "http://localhost:8000/deals?min_drop_percent=10"

# Exportera till CSV
curl -H "X-API-Key: ${API_KEY}" http://localhost:8000/export/csv > produkter.csv
```

API-dokumentation: http://localhost:8000/docs

---

🔧 Konfiguration (.env)

```bash
# =========================
# SÖKVÄGAR
# =========================
DOCKER=/path/to/docker/data
CONFIG=/path/to/config
DOMAIN=example.com

# =========================
# ANVÄNDARE
# =========================
PUID=1000
PGID=1000
TZ=Europe/Stockholm

# =========================
# SCRAPER
# =========================
CONCURRENT_PAGES=3
HEADLESS=true
SCRAPE_INTERVAL=3600

# =========================
# ALERTS
# =========================
ALERT_CHECK_INTERVAL=1800
MIN_DROP_PERCENT=5
MIN_DROP_AMOUNT=100
COOLDOWN_HOURS=24

# =========================
# SÄKERHET
# =========================
API_KEY=din-genererade-api-nyckel-här
```

---

🛠️ Felsökning

Postgres startar inte

```bash
# Kontrollera rättigheter
sudo chown -R 999:999 ${DOCKER}/scraper/postgres
```

API:et svarar med 401 Unauthorized

```bash
# Kontrollera att du skickar med rätt header
curl -H "X-API-Key: ${API_KEY}" http://localhost:8000/products
```

Inga produkter skrapas

```bash
# Testa selektorerna via WebUI (Testa-knappen)
# eller kolla loggarna:
docker logs scraper_engine --tail 50
```

---

📁 Databasstruktur

```sql
products (
  id SERIAL PRIMARY KEY,
  url TEXT UNIQUE,
  title TEXT,
  current_price INTEGER,
  first_seen TIMESTAMP,
  last_updated TIMESTAMP,
  site_config_id INTEGER
)

price_history (
  id SERIAL PRIMARY KEY,
  product_id INTEGER REFERENCES products(id),
  price INTEGER,
  timestamp TIMESTAMP
)

scraper_config (
  id SERIAL PRIMARY KEY,
  name TEXT UNIQUE,
  base_url TEXT,
  product_selector TEXT,
  title_selector TEXT,
  price_selector TEXT,
  link_selector TEXT,
  enabled INTEGER DEFAULT 1,
  ...
)
```

---
📝 Licens

MIT - se [LICENSE](./LICENSE)
---
Skapad av blixten85 🚀
