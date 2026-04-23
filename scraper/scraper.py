#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL-based multi-site scraper - Production version
with proxy support, retry/backoff and periodic flush
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
from psycopg2.pool import ThreadedConnectionPool

app = Flask(__name__)

# === Configuration ===
LOG_DIR = "/logs"
MAX_CONCURRENT = int(os.getenv('CONCURRENT_PAGES', '2'))
HEADLESS = os.getenv('HEADLESS', 'true').lower() == 'true'
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '3600'))
PROXY_URL = os.getenv('PROXY_URL', '')

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

stats = {"products": 0, "updated": 0, "skipped": 0, "errors": 0, "retries": 0}
shutdown_event = asyncio.Event()
scraping_active = False
write_buffer = []
write_lock = asyncio.Lock()


def read_secret(env_var, default=""):
    """Read secret from file or env"""
    path = os.getenv(f"{env_var}_FILE")
    if path and os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return os.getenv(env_var, default)


db_pool = None

def init_db_pool():
    global db_pool
    db_password = read_secret("DB_PASSWORD")
    
    db_pool = ThreadedConnectionPool(
        minconn=1, maxconn=10,
        host=os.getenv("DB_HOST", "postgres"),
        database=os.getenv("DB_NAME", "scraper"),
        user=os.getenv("DB_USER", "scraper"),
        password=db_password,
        connect_timeout=10
    )
    logger.info("Database connection pool initialized")


def get_db():
    """Get connection from pool"""
    return db_pool.getconn()


def return_db(conn):
    """Return connection to pool"""
    db_pool.putconn(conn)


def init_db():
    """Initialize PostgreSQL database"""
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
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS alert_cooldown (
        product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
        last_alert TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (product_id)
    )
    """)
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_url ON products(url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_products_last_updated ON products(last_updated)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_history_time ON price_history(timestamp DESC)")
    
    cur.execute("SELECT COUNT(*) FROM scraper_config")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO scraper_config 
        (name, base_url, product_selector, title_selector, price_selector, link_selector, max_pages)
        VALUES 
        ('Inet.se', 'https://www.inet.se/kategori/datorkomponenter',
         'a[href*=\"/produkt/\"]', '', 'text=/\\d[\\d\\s]*\\s*kr/', '', 5)
        """)
        cur.execute("""
        INSERT INTO scraper_config 
        (name, base_url, product_selector, title_selector, price_selector, link_selector, max_pages)
        VALUES 
        ('Komplett.se', 'https://www.komplett.se/category/10000/datorkomponenter',
         'div.product', 'h2', 'span.product-price', 'a', 5)
        """)
        cur.execute("""
        INSERT INTO scraper_config 
        (name, base_url, product_selector, title_selector, price_selector, link_selector, max_pages)
        VALUES 
        ('Webhallen', 'https://www.webhallen.com/se/category/3-Datorkomponenter',
         'div.product-item', 'h2.product-title', 'span.price', 'a.product-link', 5)
        """)
        cur.execute("""
        INSERT INTO scraper_config 
        (name, base_url, product_selector, title_selector, price_selector, link_selector, max_pages)
        VALUES 
        ('Bookstore', 'https://books.toscrape.com',
         'article.product_pod', 'h3 a', 'p.price_color', 'h3 a', 50)
        """)
        logger.info("Created default configs")
    
    conn.commit()
    return_db(conn)
    logger.info("PostgreSQL database initialized")


def load_configs():
    """Load active configurations"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scraper_config WHERE enabled = 1 ORDER BY name")
    columns = [desc[0] for desc in cur.description]
    configs = [dict(zip(columns, row)) for row in cur.fetchall()]
    return_db(conn)
    return configs


def extract_price(price_text, pattern=None):
    if not price_text:
        return 0
    if pattern and pattern.startswith('text=/'):
        safe_pattern = re.escape(pattern[6:-1])
        match = re.search(safe_pattern, str(price_text))
        if match:
            price_text = match.group(0)
    digits = re.sub(r"[^\d]", "", str(price_text))
    return int(digits) if digits else 0


async def extract_product(page, element, config):
    try:
        title_el = await element.query_selector(config['title_selector'])
        price_el = await element.query_selector(config['price_selector'])
        link_el = await element.query_selector(config['link_selector'])
        
        title = (await title_el.inner_text()).strip() if title_el else ""
        if not title and config['title_selector'] == '':
            title = (await element.inner_text()).strip()
        
        price_text = (await price_el.inner_text()).strip() if price_el else ""
        if not price_text and config['price_selector'].startswith('text=/'):
            parent_text = await element.evaluate("el => el.closest('article, div')?.innerText || ''")
            safe_pattern = re.escape(config['price_selector'][6:-1])
            match = re.search(safe_pattern, parent_text)
            price_text = match.group(0) if match else ""
        
        link = await link_el.get_attribute("href") if link_el else await element.get_attribute("href")
        
        if not (title and price_text and link):
            return None
        
        price = extract_price(price_text, config['price_selector'])
        if price == 0:
            return None
        
        if price < config.get('min_price', 0) or price > config.get('max_price', 999999):
            return None
        
        url = urljoin(config['base_url'], link)
        
        return {'url': url, 'title': title[:200], 'price': price, 'site_config_id': config['id']}
    except Exception as e:
        logger.debug(f"Extraction error: {e}")
        return None


async def scrape_page_with_retry(context, url, max_retries=3):
    """Scrape page with exponential backoff - always closes page on failure"""
    for attempt in range(max_retries):
        page = None
        try:
            page = await context.new_page()
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 5000))
            return page
        except Exception as e:
            if page:
                await page.close()
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5 + random.uniform(1, 3)
                logger.warning(f"Retry {attempt+1}/{max_retries} for {url} after {wait_time:.1f}s: {e}")
                stats['retries'] += 1
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"All retries failed for {url}: {e}")
                return None
    return None


async def scrape_site(context, config):
    page_num = 1
    products_found = 0
    known_urls = set()
    page = None
    
    try:
        logger.info(f"Starting: {config['name']}")
        url = config['base_url']
        max_pages = config.get('max_pages', 10)
        
        while url and page_num <= max_pages and not shutdown_event.is_set():
            logger.info(f"  Page {page_num}/{max_pages}: {url}")
            page = await scrape_page_with_retry(context, url)
            if not page:
                break
            
            try:
                for _ in range(random.randint(2, 4)):
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                
                elements = await page.query_selector_all(config['product_selector'])
                logger.info(f"  Found {len(elements)} elements")
                
                for elem in elements:
                    product = await extract_product(page, elem, config)
                    if product:
                        was_known = product['url'] in known_urls
                        known_urls.add(product['url'])
                        async with write_lock:
                            write_buffer.append((product, was_known))
                            if len(write_buffer) >= 10:
                                await flush_buffer()
                        products_found += 1
            finally:
                await page.close()
                page = None
            
            if config.get('pagination_type') == 'query':
                separator = '&' if '?' in config['base_url'] else '?'
                url = f"{config['base_url']}{separator}page={page_num + 1}"
            else:
                url = None
            
            page_num += 1
            await asyncio.sleep(random.uniform(3, 7))
        
        logger.info(f"Done with {config['name']}: {products_found} products")
    except Exception as e:
        logger.error(f"Error in {config['name']}: {e}")
        stats['errors'] += 1
    finally:
        if page:
            await page.close()


async def flush_buffer():
    """Save buffered products to PostgreSQL"""
    if not write_buffer:
        return
    
    buffer_copy = write_buffer.copy()
    write_buffer.clear()
    
    conn = get_db()
    cur = conn.cursor()
    now = datetime.datetime.now()
    
    known_urls_list = [p[0]['url'] for p in buffer_copy if p[1]]
    current_prices = {}
    
    if known_urls_list:
        cur.execute("SELECT url, current_price FROM products WHERE url = ANY(%s::text[])", (known_urls_list,))
        for row in cur.fetchall():
            current_prices[row[0]] = row[1]
    
    for product, was_known in buffer_copy:
        try:
            current_price = current_prices.get(product['url']) if was_known else None
            
            if current_price == product['price']:
                stats['skipped'] += 1
                continue
            
            cur.execute("""
                INSERT INTO products (url, title, current_price, site_config_id, last_updated)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    current_price = EXCLUDED.current_price,
                    title = EXCLUDED.title,
                    last_updated = EXCLUDED.last_updated
                RETURNING id
            """, (product['url'], product['title'], product['price'], product['site_config_id'], now))
            
            product_id = cur.fetchone()[0]
            
            cur.execute("INSERT INTO price_history (product_id, price, timestamp) VALUES (%s, %s, %s)",
                       (product_id, product['price'], now))
            
            if was_known:
                stats['updated'] += 1
            else:
                stats['products'] += 1
                
        except Exception as e:
            logger.error(f"DB error: {e}")
            stats['errors'] += 1
    
    conn.commit()
    return_db(conn)


async def periodic_flush():
    """Flush buffer every 5 seconds"""
    while not shutdown_event.is_set():
        await asyncio.sleep(5)
        if write_buffer:
            async with write_lock:
                if write_buffer:
                    await flush_buffer()


async def run_scraper():
    """Main function"""
    configs = load_configs()
    if not configs:
        logger.warning("No active configurations")
        return
    
    flush_task = asyncio.create_task(periodic_flush())
    
    proxy = None
    if PROXY_URL:
        proxy = {"server": PROXY_URL}
        logger.info(f"Using proxy: {PROXY_URL.split('@')[-1] if '@' in PROXY_URL else PROXY_URL}")
    
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-http2',
                    '--ignore-certificate-errors',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-zygote',
                ],
                proxy=proxy
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='sv-SE',
                timezone_id='Europe/Stockholm',
                extra_http_headers={
                    'Accept-Language': 'sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'DNT': '1',
                }
            )
            sem = asyncio.Semaphore(MAX_CONCURRENT)
            
            async def worker(cfg):
                async with sem:
                    await scrape_site(context, cfg)
            
            tasks = [worker(cfg) for cfg in configs]
            await asyncio.gather(*tasks)
    finally:
        if browser:
            await browser.close()
    
    flush_task.cancel()
    if write_buffer:
        await flush_buffer()
    
    logger.info(f"Done. New: {stats['products']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}")


async def scraper_loop():
    global scraping_active
    while not shutdown_event.is_set():
        scraping_active = True
        try:
            await run_scraper()
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
        finally:
            scraping_active = False
        
        for _ in range(SCRAPE_INTERVAL):
            if shutdown_event.is_set():
                break
            await asyncio.sleep(1)


# === Flask API ===
@app.route('/health')
def health():
    return jsonify({'status': 'healthy' if db_pool else 'degraded', 'active': scraping_active, 'stats': stats})


@app.route('/config', methods=['GET'])
def get_configs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM scraper_config ORDER BY name")
    columns = [desc[0] for desc in cur.description]
    configs = [dict(zip(columns, row)) for row in cur.fetchall()]
    return_db(conn)
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
        conn.rollback()
        return jsonify({'status': 'error', 'message': 'Name already exists'}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        return_db(conn)


@app.route('/config/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    try:
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
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        return_db(conn)


@app.route('/config/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE scraper_config SET enabled = 0 WHERE id = %s", (config_id,))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        return_db(conn)


@app.route('/test', methods=['POST'])
def test_scrape_sync():
    """Test scraping - sync wrapper for async"""
    config = request.json
    
    async def _test():
        browser = None
        try:
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
                    return {'status': 'success', 'elements_found': len(elements), 'preview': products}
                finally:
                    await page.close()
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
        finally:
            if browser:
                await browser.close()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_test())
    finally:
        loop.close()
    return jsonify(result)


@app.route('/scrape', methods=['POST'])
def trigger_scrape():
    global scraping_active
    if scraping_active:
        return jsonify({'status': 'error', 'message': 'Already running'}), 409
    
    def run():
        try:
            asyncio.run(run_scraper())
        except Exception as e:
            logger.error(f"Scrape thread failed: {e}")
    
    threading.Thread(target=run, daemon=True).start()
    return jsonify({'status': 'success'})


@app.route('/trigger-scrape', methods=['POST'])
def trigger_scrape_alias():
    """Alias for /scrape"""
    return trigger_scrape()


@app.route('/export/<site_name>')
def export_site_csv(site_name):
    """Export products for a specific site to CSV"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("""
        SELECT p.title, p.current_price, p.url
        FROM products p
        JOIN scraper_config c ON p.site_config_id = c.id
        WHERE c.name = %s AND p.current_price > 0
        ORDER BY p.current_price ASC
    """, (site_name,))
    
    products = cur.fetchall()
    return_db(conn)
    
    import csv
    from io import StringIO
    from flask import Response
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Product', 'Price (SEK)', 'Link'])
    
    for p in products:
        writer.writerow([p['title'], p['current_price'], p['url']])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={site_name}_{datetime.datetime.now().strftime("%Y%m%d")}.csv'}
    )


def signal_handler(signum, frame):
    logger.info(f"Signal {signum}, shutting down...")
    shutdown_event.set()


if __name__ == "__main__":
    init_db_pool()
    init_db()
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5001, debug=False), daemon=True).start()
    asyncio.run(scraper_loop())
