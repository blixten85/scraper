#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generisk multi-site web scraper med central config i databasen
"""

import asyncio
import json
import datetime
import os
import re
import logging
import sys
import random
import sqlite3
import signal
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from flask import Flask, request, jsonify
import threading

# === Flask app för intern kommunikation ===
app = Flask(__name__)

# === Konfiguration ===
DATA_DIR = os.getenv('SCRAPER_DATA_PATH', '/data')
LOG_DIR = f"{DATA_DIR}/logs"
SQLITE_BUSY_TIMEOUT = int(os.getenv('SQLITE_BUSY_TIMEOUT', '5000'))
MAX_CONCURRENT = int(os.getenv('CONCURRENT_PAGES', '3'))
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '3600'))

DB_FILE = f"{DATA_DIR}/products.db"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# === Loggning ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/scraper.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# === Global state ===
stats = {"products": 0, "updated": 0, "skipped": 0, "errors": 0}
shutdown_event = asyncio.Event()
scraping_active = False
write_buffer = []
write_lock = asyncio.Lock()


def init_db():
    """Initiera databas med config-tabell"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # PRAGMA för bättre concurrency
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
    
    # Produkt-tabell
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT UNIQUE,
        title TEXT,
        current_price INTEGER,
        first_seen TIMESTAMP,
        last_updated TIMESTAMP,
        site_config_id INTEGER
    )
    """)
    
    # Prishistorik
    cur.execute("""
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        price INTEGER,
        timestamp TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )
    """)
    
    # CENTRAL CONFIG TABELL
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scraper_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        exclude_out_of_stock INTEGER DEFAULT 0,
        out_of_stock_selector TEXT,
        categories TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Index
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_url ON products(url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(timestamp)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_config_enabled ON scraper_config(enabled)")
    
    # Lägg till default config om tabellen är tom
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
        logger.info("Skapade default config för Inet.se")
    
    conn.commit()
    conn.close()
    logger.info("Databas initierad med config-tabell")


def get_db_connection():
    """Hämta databasanslutning med rätt PRAGMA"""
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
    conn.row_factory = sqlite3.Row
    return conn


def load_configs_from_db():
    """Ladda alla aktiva konfigurationer från databasen"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT * FROM scraper_config 
        WHERE enabled = 1
        ORDER BY name
    """)
    
    configs = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    logger.info(f"Laddade {len(configs)} aktiva konfigurationer")
    return configs


def extract_price(price_text, pattern=None):
    """Extrahera pris från text med stöd för regex"""
    if not price_text:
        return 0
    
    # Om pattern är regex-format: text=/regex/
    if pattern and pattern.startswith('text=/'):
        regex_pattern = pattern[6:-1]
        match = re.search(regex_pattern, str(price_text))
        if match:
            price_text = match.group(0)
    
    digits = re.sub(r"[^\d]", "", str(price_text))
    return int(digits) if digits else 0


async def extract_product_generic(page, element, config):
    """Generisk produkt-extrahering baserat på config"""
    try:
        # Hitta element med selektorer
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
        
        # Applicera prisfilter
        if price < config.get('min_price', 0) or price > config.get('max_price', 999999):
            return None
        
        # Kolla lagerstatus om konfigurerat
        if config.get('exclude_out_of_stock') and config.get('out_of_stock_selector'):
            stock_el = await element.query_selector(config['out_of_stock_selector'])
            if stock_el:
                return None
        
        # Bygg full URL
        url = urljoin(config['base_url'], link)
        
        return {
            'url': url,
            'title': title,
            'price': price,
            'site_config_id': config['id']
        }
        
    except Exception as e:
        logger.debug(f"Extraheringsfel: {e}")
        return None


async def handle_pagination(page, config, page_num, current_url):
    """Generisk pagineringshantering"""
    pagination_type = config.get('pagination_type', 'query')
    
    if pagination_type == 'query':
        separator = '&' if '?' in config['base_url'] else '?'
        return f"{config['base_url']}{separator}page={page_num}"
    
    elif pagination_type == 'button':
        btn_selector = config.get('pagination_selector')
        if btn_selector:
            btn = await page.query_selector(btn_selector)
            if btn and await btn.is_enabled():
                await btn.click()
                await page.wait_for_load_state("domcontentloaded")
                return True
        return False
    
    elif pagination_type == 'infinite_scroll':
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        return True
    
    return False


async def scrape_site(context, config):
    """Skrapa en hel sajt baserat på config"""
    page = await context.new_page()
    page_num = 1
    products_found = 0
    
    try:
        logger.info(f"Startar scraping av: {config['name']} ({config['base_url']})")
        
        url = config['base_url']
        max_pages = config.get('max_pages', 10)
        
        while url and page_num <= max_pages and not shutdown_event.is_set():
            logger.debug(f"Skrapar sida {page_num}: {url}")
            
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            
            # Scrolla för lazy-loading
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(0.5)
            
            # Hitta produktcontainers
            elements = await page.query_selector_all(config['product_selector'])
            logger.info(f"Sida {page_num}: Hittade {len(elements)} element")
            
            # Extrahera produkter
            for elem in elements:
                product = await extract_product_generic(page, elem, config)
                if product:
                    async with write_lock:
                        write_buffer.append(product)
                        if len(write_buffer) >= 50:
                            await flush_buffer()
                    products_found += 1
            
            # Hantera paginering
            result = await handle_pagination(page, config, page_num + 1, url)
            if isinstance(result, str):
                url = result
                page_num += 1
            elif result is True:
                page_num += 1
                url = page.url
            else:
                break
            
            await asyncio.sleep(random.uniform(1, 3))
        
        logger.info(f"Klar med {config['name']}: {products_found} produkter")
        
    except Exception as e:
        logger.error(f"Fel vid scraping av {config['name']}: {e}")
        stats['errors'] += 1
    finally:
        await page.close()


async def flush_buffer():
    """Spara buffrade produkter till databasen"""
    if not write_buffer:
        return
    
    buffer_copy = write_buffer.copy()
    write_buffer.clear()
    
    conn = get_db_connection()
    cur = conn.cursor()
    now = datetime.datetime.now()
    
    for product in buffer_copy:
        try:
            cur.execute("""
                SELECT id, current_price FROM products 
                WHERE url = ? AND site_config_id = ?
            """, (product['url'], product['site_config_id']))
            row = cur.fetchone()
            
            if row:
                product_id, old_price = row['id'], row['current_price']
                if old_price != product['price']:
                    cur.execute("""
                        UPDATE products 
                        SET current_price = ?, title = ?, last_updated = ?
                        WHERE id = ?
                    """, (product['price'], product['title'], now, product_id))
                    
                    cur.execute("""
                        INSERT INTO price_history (product_id, price, timestamp)
                        VALUES (?, ?, ?)
                    """, (product_id, product['price'], now))
                    
                    stats['updated'] += 1
                else:
                    cur.execute("""
                        UPDATE products SET last_updated = ? WHERE id = ?
                    """, (now, product_id))
                    stats['skipped'] += 1
            else:
                cur.execute("""
                    INSERT INTO products 
                    (url, title, current_price, first_seen, last_updated, site_config_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (product['url'], product['title'], product['price'], now, now, product['site_config_id']))
                
                product_id = cur.lastrowid
                cur.execute("""
                    INSERT INTO price_history (product_id, price, timestamp)
                    VALUES (?, ?, ?)
                """, (product_id, product['price'], now))
                
                stats['products'] += 1
                
        except Exception as e:
            logger.error(f"DB-fel för {product['url']}: {e}")
            stats['errors'] += 1
    
    conn.commit()
    conn.close()
    
    logger.debug(f"Sparade {len(buffer_copy)} produkter")


async def run_scraper():
    """Huvudfunktion - kör alla konfigurationer parallellt"""
    global scraping_active
    
    configs = load_configs_from_db()
    if not configs:
        logger.warning("Inga aktiva konfigurationer hittades")
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context()
        
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        
        async def worker(config):
            async with sem:
                await scrape_site(context, config)
        
        tasks = [asyncio.create_task(worker(cfg)) for cfg in configs]
        
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        
        if shutdown_event.is_set():
            for task in pending:
                task.cancel()
        
        await browser.close()
    
    # Spara kvarvarande buffer
    if write_buffer:
        await flush_buffer()
    
    logger.info(f"Scraping klar. Totalt: {stats['products']} nya, {stats['updated']} uppdaterade")


async def scraper_loop():
    """Huvudloop med asyncio.sleep"""
    global scraping_active
    
    while not shutdown_event.is_set():
        scraping_active = True
        try:
            await run_scraper()
        except Exception as e:
            logger.error(f"Scraping misslyckades: {e}", exc_info=True)
        finally:
            scraping_active = False
        
        logger.info(f"Väntar {SCRAPE_INTERVAL} sekunder till nästa körning...")
        for _ in range(SCRAPE_INTERVAL):
            if shutdown_event.is_set():
                break
            await asyncio.sleep(1)


# === Flask API för intern kommunikation och WebUI ===
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'active': scraping_active,
        'stats': stats
    })


@app.route('/config', methods=['GET'])
def get_configs():
    """Hämta alla konfigurationer"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scraper_config ORDER BY name")
    configs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(configs)


@app.route('/config', methods=['POST'])
def create_config():
    """Skapa ny konfiguration"""
    data = request.json
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO scraper_config 
            (name, base_url, product_selector, title_selector, price_selector, 
             link_selector, pagination_type, pagination_selector, max_pages,
             min_price, max_price, exclude_out_of_stock, out_of_stock_selector, categories)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['name'], data['base_url'],
            data['product_selector'], data['title_selector'],
            data['price_selector'], data['link_selector'],
            data.get('pagination_type', 'query'),
            data.get('pagination_selector'),
            data.get('max_pages', 10),
            data.get('min_price', 0),
            data.get('max_price', 999999),
            data.get('exclude_out_of_stock', 0),
            data.get('out_of_stock_selector'),
            json.dumps(data.get('categories', []))
        ))
        conn.commit()
        config_id = cur.lastrowid
        conn.close()
        
        return jsonify({'status': 'success', 'id': config_id})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Name already exists'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/config/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    """Uppdatera konfiguration"""
    data = request.json
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE scraper_config SET
            name = ?, base_url = ?,
            product_selector = ?, title_selector = ?,
            price_selector = ?, link_selector = ?,
            pagination_type = ?, pagination_selector = ?,
            max_pages = ?, enabled = ?,
            min_price = ?, max_price = ?,
            exclude_out_of_stock = ?, out_of_stock_selector = ?,
            categories = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
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
        data.get('exclude_out_of_stock', 0),
        data.get('out_of_stock_selector'),
        json.dumps(data.get('categories', [])),
        config_id
    ))
    
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})


@app.route('/config/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    """Inaktivera konfiguration (soft delete)"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE scraper_config SET enabled = 0 WHERE id = ?", (config_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})


@app.route('/test', methods=['POST'])
async def test_scrape():
    """Testa en konfiguration - preview av produkter"""
    config = request.json
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(config['base_url'], timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            
            elements = await page.query_selector_all(config['product_selector'])
            products = []
            
            for elem in elements[:10]:  # Max 10 för preview
                product = await extract_product_generic(page, elem, config)
                if product:
                    products.append(product)
            
            await browser.close()
            
            return jsonify({
                'status': 'success',
                'elements_found': len(elements),
                'products_found': len(products),
                'preview': products
            })
            
        except Exception as e:
            await browser.close()
            return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    """Trigga manuell scraping"""
    global scraping_active
    
    if scraping_active:
        return jsonify({'status': 'error', 'message': 'Scraping already running'}), 409
    
    def run_async():
        asyncio.run(run_scraper())
    
    thread = threading.Thread(target=run_async)
    thread.start()
    
    return jsonify({'status': 'success', 'message': 'Scraping started'})


def run_flask():
    """Kör Flask i separat tråd"""
    app.run(host='0.0.0.0', port=5001, debug=False)


def signal_handler(signum, frame):
    logger.info(f"Mottog signal {signum}, stänger ner...")
    shutdown_event.set()


if __name__ == "__main__":
    init_db()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    try:
        asyncio.run(scraper_loop())
    except KeyboardInterrupt:
        logger.info("Avbruten")
    except Exception as e:
        logger.error(f"Ohanterat fel: {e}", exc_info=True)
    
    logger.info("Scraper avslutad")
