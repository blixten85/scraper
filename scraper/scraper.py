#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL-baserad multi-site scraper - Produktionsversion
"""

import asyncio
import json
import datetime
import os
import re
import logging
import sys
import random
import signal
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from flask import Flask, request, jsonify
import threading
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# === Konfiguration ===
LOG_DIR = "/logs"
SQLITE_BUSY_TIMEOUT = int(os.getenv('SQLITE_BUSY_TIMEOUT', '5000'))
MAX_CONCURRENT = int(os.getenv('CONCURRENT_PAGES', '3'))
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '3600'))

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/scraper.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

stats = {"products": 0, "updated": 0, "skipped": 0, "errors": 0}
shutdown_event = asyncio.Event()
scraping_active = False
write_buffer = []
write_lock = asyncio.Lock()


def get_db():
    """PostgreSQL-anslutning"""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        database=os.getenv("DB_NAME", "scraper"),
        user=os.getenv("DB_USER", "scraper"),
        password=os.getenv("DB_PASSWORD", "scraper_password"),
        connect_timeout=10
    )


def init_db():
    """Initiera PostgreSQL-databas"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id SERIAL PRIMARY KEY,
        url TEXT UNIQUE,
        title TEXT,
        current_price INTEGER,
        first_seen TIMESTAMP DEFAULT NOW(),
        last_updated TIMESTAMP DEFAULT NOW(),
        site_config_id INTEGER
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id SERIAL PRIMARY KEY,
        product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
        price INTEGER,
        timestamp TIMESTAMP DEFAULT NOW()
    )
    """)
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scraper_config (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        base_url TEXT NOT NULL,
        product_selector TEXT NOT NULL,
        title_selector TEXT NOT NULL,
        price_selector TEXT NOT NULL,
        link_selector TEXT NOT NULL,
        pagination_type TEXT DEFAULT 'query',
        pagination_selector TEXT,
        max_pages INTEGER DEFAULT 10,
        enabled INTEGER DEFAULT 1,
        min_price INTEGER DEFAULT 0,
        max_price INTEGER DEFAULT 999999,
        categories TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    )
    """)
    
    # Index för prestanda
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_url ON products(url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_last_updated ON products(last_updated)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(timestamp DESC)")
    
    # Default config
    cur.execute("SELECT COUNT(*) FROM scraper_config")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO scraper_config 
        (name, base_url, product_selector, title_selector, price_selector, link_selector)
        VALUES 
        ('Inet.se', 'https://www.inet.se', 
         'a[href*=''/produkt/'']', 
         'a[href*=''/produkt/'']', 
         'text=/\\d[\\d\\s]*\\s*kr/', 
         'a[href*=''/produkt/'']')
        """)
        logger.info("Skapade default config")
    
    conn.commit()
    conn.close()
    logger.info("PostgreSQL-databas initierad")


def load_configs():
    """Ladda aktiva konfigurationer"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scraper_config WHERE enabled = 1 ORDER BY name")
    columns = [desc[0] for desc in cur.description]
    configs = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()
    return configs


def extract_price(price_text, pattern=None):
    if not price_text:
        return 0
    if pattern and pattern.startswith('text=/'):
        match = re.search(pattern[6:-1], str(price_text))
        if match:
            price_text = match.group(0)
    digits = re.sub(r"[^\d]", "", str(price_text))
    return int(digits) if digits else 0


async def extract_product(page, element, config):
    try:
        title_el = await element.query_selector(config['title_selector'])
        price_el = await element.query_selector(config['price_selector'])
        link_el = await element.query_selector(config['link_selector'])
        
        title = (await title_el.inner_text()).strip() if title_el else None
        price_text = (await price_el.inner_text()).strip() if price_el else None
        link = await link_el.get_attribute("href") if link_el else None
        
        if not (title and price_text and link):
            return None
        
        price = extract_price(price_text, config['price_selector'])
        if price == 0:
            return None
        
        if price < config.get('min_price', 0) or price > config.get('max_price', 999999):
            return None
        
        url = urljoin(config['base_url'], link)
        
        return {'url': url, 'title': title, 'price': price, 'site_config_id': config['id']}
    except:
        return None


async def scrape_site(context, config):
    page = await context.new_page()
    page_num = 1
    products_found = 0
    
    try:
        logger.info(f"Startar: {config['name']}")
        url = config['base_url']
        max_pages = config.get('max_pages', 10)
        
        while url and page_num <= max_pages and not shutdown_event.is_set():
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)
            
            elements = await page.query_selector_all(config['product_selector'])
            
            for elem in elements:
                product = await extract_product(page, elem, config)
                if product:
                    async with write_lock:
                        write_buffer.append(product)
                        if len(write_buffer) >= 20:  # <- MINSKAT från 50
                            await flush_buffer()
                    products_found += 1
            
            if config.get('pagination_type') == 'query':
                separator = '&' if '?' in config['base_url'] else '?'
                url = f"{config['base_url']}{separator}page={page_num + 1}"
            else:
                break
            
            page_num += 1
            await asyncio.sleep(random.uniform(1, 3))
        
        logger.info(f"Klar med {config['name']}: {products_found} produkter")
    except Exception as e:
        logger.error(f"Fel i {config['name']}: {e}")
        stats['errors'] += 1
    finally:
        await page.close()


async def flush_buffer():
    """Spara buffrade produkter till PostgreSQL"""
    if not write_buffer:
        return
    
    buffer_copy = write_buffer.copy()
    write_buffer.clear()
    
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.now()
    
    for product in buffer_copy:
        try:
            cur.execute("""
                INSERT INTO products (url, title, current_price, site_config_id, last_updated)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    current_price = EXCLUDED.current_price,
                    title = EXCLUDED.title,
                    last_updated = EXCLUDED.last_updated
                RETURNING id, (xmax = 0) AS is_new
            """, (product['url'], product['title'], product['price'], product['site_config_id'], now))
            
            row = cur.fetchone()
            product_id, is_new = row[0], row[1]
            
            cur.execute("""
                INSERT INTO price_history (product_id, price, timestamp)
                VALUES (%s, %s, %s)
            """, (product_id, product['price'], now))
            
            if is_new:
                stats['products'] += 1
            else:
                stats['updated'] += 1
                
        except Exception as e:
            logger.error(f"DB-fel: {e}")
            stats['errors'] += 1
    
    conn.commit()
    conn.close()


async def periodic_flush():
    """Flusha buffern var 10:e sekund"""
    while not shutdown_event.is_set():
        await asyncio.sleep(10)
        if write_buffer:
            async with write_lock:
                if write_buffer:
                    await flush_buffer()


async def run_scraper():
    """Huvudfunktion"""
    configs = load_configs()
    if not configs:
        logger.warning("Inga aktiva konfigurationer")
        return
    
    flush_task = asyncio.create_task(periodic_flush())
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context()
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        
        async def worker(cfg):
            async with sem:
                await scrape_site(context, cfg)
        
        tasks = [asyncio.create_task(worker(cfg)) for cfg in configs]
        await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()
    
    flush_task.cancel()
    if write_buffer:
        await flush_buffer()
    
    logger.info(f"Klar. Nya: {stats['products']}, Uppdaterade: {stats['updated']}")


async def scraper_loop():
    global scraping_active
    while not shutdown_event.is_set():
        scraping_active = True
        try:
            await run_scraper()
        except Exception as e:
            logger.error(f"Scraping misslyckades: {e}")
        finally:
            scraping_active = False
        
        for _ in range(SCRAPE_INTERVAL):
            if shutdown_event.is_set():
                break
            await asyncio.sleep(1)


# === Flask API ===
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'active': scraping_active, 'stats': stats})


@app.route('/config', methods=['GET'])
def get_configs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scraper_config ORDER BY name")
    columns = [desc[0] for desc in cur.description]
    configs = [dict(zip(columns, row)) for row in cur.fetchall()]
    conn.close()
    return jsonify(configs)


@app.route('/config', methods=['POST'])
def create_config():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO scraper_config 
            (name, base_url, product_selector, title_selector, price_selector, link_selector,
             pagination_type, pagination_selector, max_pages, min_price, max_price, categories)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data['name'], data['base_url'],
            data['product_selector'], data['title_selector'],
            data['price_selector'], data['link_selector'],
            data.get('pagination_type', 'query'),
            data.get('pagination_selector'),
            data.get('max_pages', 10),
            data.get('min_price', 0),
            data.get('max_price', 999999),
            json.dumps(data.get('categories', []))
        ))
        config_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'status': 'success', 'id': config_id})
    except psycopg2.errors.UniqueViolation:
        return jsonify({'status': 'error', 'message': 'Name already exists'}), 400
    finally:
        conn.close()


@app.route('/config/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE scraper_config SET
            name = %s, base_url = %s, product_selector = %s, title_selector = %s,
            price_selector = %s, link_selector = %s, pagination_type = %s,
            pagination_selector = %s, max_pages = %s, enabled = %s,
            min_price = %s, max_price = %s, categories = %s, updated_at = NOW()
        WHERE id = %s
    """, (
        data['name'], data['base_url'],
        data['product_selector'], data['title_selector'],
        data['price_selector'], data['link_selector'],
        data.get('pagination_type', 'query'),
        data.get('pagination_selector'),
        data.get('max_pages', 10),
        data.get('enabled', 1),
        data.get('min_price', 0),
        data.get('max_price', 999999),
        json.dumps(data.get('categories', [])),
        config_id
    ))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})


@app.route('/config/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE scraper_config SET enabled = 0 WHERE id = %s", (config_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})


@app.route('/test', methods=['POST'])
async def test_scrape():
    config = request.json
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(config['base_url'], timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            elements = await page.query_selector_all(config['product_selector'])
            products = []
            for elem in elements[:5]:
                product = await extract_product(page, elem, config)
                if product:
                    products.append(product)
            await browser.close()
            return jsonify({'status': 'success', 'elements_found': len(elements), 'preview': products})
        except Exception as e:
            await browser.close()
            return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    global scraping_active
    if scraping_active:
        return jsonify({'status': 'error', 'message': 'Already running'}), 409
    
    def run():
        asyncio.run(run_scraper())
    
    threading.Thread(target=run).start()
    return jsonify({'status': 'success'})


def signal_handler(signum, frame):
    logger.info(f"Signal {signum}, stänger ner...")
    shutdown_event.set()


if __name__ == "__main__":
    init_db()
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5001, debug=False), daemon=True).start()
    asyncio.run(scraper_loop())
