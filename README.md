# 🕷️ Web Scraper Platform

[![Build and Push Images](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml/badge.svg)](https://github.com/blixten85/scraper/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Lättviktig, konfigurerbar web scraping-plattform med WebUI, API och prisbevakning.**

## ✨ Funktioner

| Funktion | Beskrivning |
|----------|-------------|
| 🔍 **Multi-site scraping** | Skrapa valfri e-handelssida med CSS-selektorer |
| 🎨 **WebUI** | Konfigurera och övervaka via webbgränssnitt (port 3000) |
| 📡 **REST API** | Hämta data programmatiskt (port 8000) |
| 🔔 **Prisbevakning** | Discord-notiser vid prisfall |
| 💾 **SQLite** | Enkel, filbaserad databas - ingen extra infrastruktur |
| 🐳 **Docker** | Kör allt med en docker compose up |
| 🏷️ **Generisk** | Fungerar med Inet.se, Komplett, Webhallen, m.fl. |

## 🚀 Snabbstart

```bash
# 1. Klona repot
git clone https://github.com/blixten85/scraper.git
cd scraper

# 2. Skapa secrets-mapp och Discord webhook
mkdir -p secrets
echo "din-discord-webhook-url" > secrets/discord_webhook.txt

# 3. Skapa data-mappar
mkdir -p data logs

# 4. Starta
docker compose up -d

# 5. Öppna WebUI
# http://localhost:3000

```markdown
## 🚀 Quick Start - Simple Scraper

Want to just scrape a site and save to a text file? Use the simple scraper!

### 1. Install dependencies
```bash
pip install playwright
playwright install chromium
```

2. Configure your site

Edit simple_scraper.py and change the CONFIG section at the top:

```python
CONFIG = {
    "url": "https://www.inet.se/kategori/datorkomponenter",  # Change this!
    "product_selector": "a[href*='/produkt/']",               # Product container
    "title_selector": "",                                      # Leave empty to use link text
    "price_selector": "text=/\\d[\\d\\s]*\\s*kr/",            # Price regex
    "link_selector": "",                                       # Leave empty to use href
    "max_products": 50,                                        # How many products?
    "output_file": "products.txt"                              # Output filename
}
```

3. Run it!

```bash
python simple_scraper.py
```

Example Output (products.txt)

```
Scraped from: https://www.inet.se/kategori/datorkomponenter
================================================================================

Product              Price       Link
--------------------------------------------------------------------------------
ASUS GeForce RTX 4070    7490 kr     https://www.inet.se/produkt/...
AMD Ryzen 7 7800X3D      4790 kr     https://www.inet.se/produkt/...
```

Pre-made Configs

Site product_selector price_selector
Inet.se a[href*='/produkt/'] text=/\\d[\\d\\s]*\\s*kr/
Komplett.se div.product-list-item span.product-price-now
Webhallen.com div.product-item span.price
Amazon.se div[data-component-type="s-search-result"] span.a-price-whole

Need help finding selectors?

1. Open the website in Chrome
2. Right-click on a product → "Inspect"
3. Find the CSS class/ID that contains the product
4. Use that as your product_selector

```
