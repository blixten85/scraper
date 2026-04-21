# Inet.se Price Tracker

[![Build and Push Images](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Komplett prisbevakningssystem för Inet.se med scraping, databas, API och Discord-notifieringar.

## ✨ Funktioner

- 🔍 **Automatisk scraping** - Skannar alla produktkategorier på Inet.se
- 💾 **SQLite-databas** - Lagrar produkter och komplett prishistorik
- 📉 **Prisbevakning** - Upptäcker prisfall och skickar Discord-notiser
- 🚀 **REST API** - Hämta data och statistik via HTTP
- 🐳 **Docker** - Enkel deployment med docker-compose
- 🔄 **CI/CD** - Automatiska byggen via GitHub Actions
- 📊 **Metrics** - Detaljerad statistik och övervakning

## 🚀 Snabbstart

### Förutsättningar
- Docker och Docker Compose
- Git (valfritt)
- Discord Webhook URL (för notiser)

### Installation

```bash
# 1. Klona repot
git clone https://github.com/blixten85/scraper.git
cd scraper

# 2. Skapa miljövariabler
cp .env.example .env
nano .env  # Redigera med din Discord Webhook

# 3. Skapa datamappar
mkdir -p data/scraper/data data/scraper/logs

# 4. Starta tjänsterna
docker-compose up -d

# 5. Kolla status
docker-compose ps
docker-compose logs -f scraper
