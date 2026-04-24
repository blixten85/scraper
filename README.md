# 🕷️ Web Scraper Platform

[![Scraper](https://github.com/blixten85/scraper/actions/workflows/scraper-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/scraper-build.yml)
[![API](https://github.com/blixten85/scraper/actions/workflows/api-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/api-build.yml)
[![WebUI](https://github.com/blixten85/scraper/actions/workflows/webui-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/webui-build.yml)
[![Alerts](https://github.com/blixten85/scraper/actions/workflows/alerts-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/alerts-build.yml)
<br>
![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/blixten85/scraper?utm_source=oss&utm_medium=github&utm_campaign=blixten85%2Fscraper&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)
[![Release](https://img.shields.io/github/v/release/blixten85/scraper)](https://github.com/blixten85/scraper/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dependabot](https://img.shields.io/badge/Dependabot-active-brightgreen)](https://github.com/blixten85/scraper/network/updates)
[![Auto-merge](https://img.shields.io/badge/Auto--merge-enabled-blue)](https://github.com/blixten85/scraper/blob/main/.github/workflows/auto-merge.yml)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/blixten85/scraper/blob/main/CONTRIBUTING.md)
<br>
[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0.0-lightgrey)](https://flask.palletsprojects.com/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40.0-2EAD33)](https://playwright.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-316192)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-24.0-2496ED)](https://www.docker.com/)
<br>
[![Stars](https://img.shields.io/github/stars/blixten85/scraper?style=social)](https://github.com/blixten85/scraper)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-%23db61a2.svg?logo=github)](https://github.com/sponsors/blixten85)

**Production-ready web scraping platform with PostgreSQL, WebUI, REST API, and price monitoring.**

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Multi-site scraping** | Scrape any e-commerce site with CSS selectors |
| 🎨 **WebUI** | Configure and monitor via web interface |
| 📡 **REST API** | Programmatic data access with API key authentication |
| 🔔 **Price alerts** | Discord notifications for price drops |
| 🐘 **PostgreSQL** | Production-grade database |
| 🐳 **Docker** | Run everything with a single docker compose up |
| 🔒 **Security** | API authentication, secrets, no-new-privileges |
| 🌐 **Proxy support** | Optional HTTP/HTTPS proxy for anti-bot protection |

---

## 🚀 Quick Start - Docker (Full Platform)

```bash
# 1. Clone the repository
git clone https://github.com/blixten85/scraper.git
cd scraper

# 2. Create .env file with your settings
cp .env.example .env
nano .env

# 3. Create directories and set permissions
mkdir -p ${DOCKER}/scraper/{logs,postgres,playwright-cache}
sudo chown -R 999:999 ${DOCKER}/scraper/postgres

# 4. Create Discord webhook (optional)
echo "url" > ${CONFIG}/.secrets/discord_webhook

# 5. Start the platform
docker compose up -d

# 6. Open WebUI
# http://localhost:3000
```

---

## 📦 Services (Docker)

| Service | Port | Description |
|---------|------|-------------|
| `scraper_db` | 5432 (internal) | PostgreSQL database |
| `scraper_engine` | 5001 (internal) | Main engine - scrapes sites |
| `scraper_api` | 8000 | REST API + Swagger docs |
| `scraper_webui` | 3000 | Web interface |
| `scraper_alerts` | - | Discord notifications |

---

## 🔐 Generate API Key and Passwords

### API Key

```bash
# Generate a random API key
openssl rand -base64 48
```

### Database Password

```bash
# Generate a secure password
openssl rand -hex 16
```

### Discord Webhook

1. Go to your Discord server → Channel settings → Integrations → Webhooks
2. Create new webhook and copy the URL
3. Save it: `echo "url" > ${CONFIG}/.secrets/discord_webhook`

---

## 📡 API Examples

*Note: API requires X-API-Key header for all endpoints except /health and /docs.*

```bash
# Get all products
curl -H "X-API-Key: ${API_KEY}" http://localhost:8000/products

# Search products
curl -H "X-API-Key: ${API_KEY}" "http://localhost:8000/products?search=RTX"

# Get price drops
curl -H "X-API-Key: ${API_KEY}" "http://localhost:8000/deals?min_drop_percent=10"

# Export to CSV
curl -H "X-API-Key: ${API_KEY}" http://localhost:8000/export/csv > products.csv
```

API Documentation: http://localhost:8000/docs

---

## 🔧 Configuration (.env)

```bash
# =========================
# PATHS
# =========================
DOCKER=/path/to/docker/data
CONFIG=/path/to/config
DOMAIN=example.com

# =========================
# USER
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
# PROXY (optional)
# =========================
# Format: http://user:pass@proxy-ip:port
PROXY_URL=
```

### Proxy Service Examples

| Service | Format |
|---------|--------|
| BrightData | `http://user-country-ignore:pass@zproxy.lum-superproxy.io:22225` |
| IPRoyal | `http://username:password@geo.iproyal.com:12321` |
| Proxy-Cheap | `http://user:pass@proxy.example.com:3128` |

---

## 🛠️ Troubleshooting

### Postgres won't start

```bash
# Check permissions
sudo chown -R 999:999 ${DOCKER}/scraper/postgres
```

### API returns 401 Unauthorized

```bash
# Verify you're sending the correct header
curl -H "X-API-Key: ${API_KEY}" http://localhost:8000/products
```

### No products are scraped

```bash
# Test selectors via WebUI (Test button)
# Or check the logs:
docker logs scraper_engine --tail 50
```

---

## 📁 Database Schema

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

## 🐛 Bugs and Feature Requests

Found a bug or want to suggest a feature?

· Bugs: Create an issue
· Feature requests: Create an issue
· Discussions: Start a discussion

---

## 🤝 Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

1. Fork the repo
2. Create a feature branch (git checkout -b feature/AmazingFeature)
3. Commit your changes (git commit -m 'Add some AmazingFeature')
4. Push to the branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📊 Project Status

| | |
|--|--|
| **Version** | [![Version](https://img.shields.io/github/v/tag/blixten85/scraper?label=version)](https://github.com/blixten85/scraper/tags) |
| **Status** | ✅ Production Ready |
| **Last Updated** | [![Last Commit](https://img.shields.io/github/last-commit/blixten85/scraper)](https://github.com/blixten85/scraper/commits) |

---

## ⭐ Support the Project

If you like this project, give it a ⭐ on GitHub!

---

## 📝 License

MIT - see [LICENSE](LICENSE)

---

Created by blixten85 🚀
