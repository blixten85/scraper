#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alert service with cooldown in PostgreSQL
"""

import asyncio
import datetime
import os
import logging
import sys
import signal
import requests
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

# === Configuration ===
LOG_DIR = "/logs"
DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_NAME = os.getenv('DB_NAME', 'scraper')
DB_USER = os.getenv('DB_USER', 'scraper')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '1800'))
MIN_DROP_PERCENT = float(os.getenv('MIN_DROP_PERCENT', '5'))
MIN_DROP_AMOUNT = int(os.getenv('MIN_DROP_AMOUNT', '100'))
COOLDOWN_HOURS = int(os.getenv('COOLDOWN_HOURS', '24'))

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/alerts.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()
alerts_sent = 0
db_pool = None


# === Helper function for secrets ===
def read_secret(env_var, default=""):
    """Read secret from file or env"""
    path = os.getenv(f"{env_var}_FILE")
    if path and os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return os.getenv(env_var, default)


def init_db_pool():
    global db_pool
    db_password = read_secret("DB_PASSWORD")
    
    db_pool = ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=db_password,
        connect_timeout=10
    )


def get_db():
    return db_pool.getconn()


def return_db(conn):
    db_pool.putconn(conn)


def get_webhook():
    """Get Discord webhook from secret or env"""
    return read_secret("DISCORD_WEBHOOK")


def send_discord(webhook, title, old_price, new_price, url):
    drop = old_price - new_price
    percent = round((drop / old_price) * 100, 1)
    
    payload = {
        "embeds": [{
            "title": "💸 Price Drop!",
            "description": f"**{title}**",
            "color": 16711680,
            "fields": [
                {"name": "Old", "value": f"{old_price:,} kr".replace(",", " "), "inline": True},
                {"name": "New", "value": f"{new_price:,} kr".replace(",", " "), "inline": True},
                {"name": "Drop", "value": f"-{drop:,} kr ({percent}%)".replace(",", " "), "inline": True},
                {"name": "Link", "value": url}
            ]
        }]
    }
    
    try:
        return requests.post(webhook, json=payload, timeout=10).status_code == 204
    except:
        return False


async def check_drops():
    global alerts_sent
    
    webhook = get_webhook()
    if not webhook:
        logger.error("No webhook configured")
        return 0
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cur.execute("""
            WITH price_drops AS (
                SELECT 
                    p.id,
                    p.title,
                    p.url,
                    ph.price AS new_price,
                    LAG(ph.price) OVER (PARTITION BY p.id ORDER BY ph.timestamp) AS old_price
                FROM products p
                JOIN price_history ph ON p.id = ph.product_id
            )
            SELECT * FROM price_drops
            WHERE old_price IS NOT NULL AND new_price < old_price
        """)
        
        alerts_this_run = 0
        
        for row in cur.fetchall():
            drop_amount = row['old_price'] - row['new_price']
            drop_percent = (drop_amount / row['old_price']) * 100
            
            if drop_percent < MIN_DROP_PERCENT or drop_amount < MIN_DROP_AMOUNT:
                continue
            
            cur.execute("""
                INSERT INTO alert_cooldown (product_id, last_alert)
                VALUES (%s, NOW())
                ON CONFLICT (product_id) DO UPDATE SET
                    last_alert = NOW()
                WHERE alert_cooldown.last_alert < NOW() - INTERVAL '%s hours'
                RETURNING product_id
            """, (row['id'], COOLDOWN_HOURS))
            
            if cur.fetchone():
                if send_discord(webhook, row['title'], row['old_price'], row['new_price'], row['url']):
                    alerts_this_run += 1
                    alerts_sent += 1
                    logger.info(f"Alert sent: {row['title'][:50]}...")
                    await asyncio.sleep(1)
        
        conn.commit()
        return alerts_this_run
    finally:
        return_db(conn)


async def alerts_loop():
    logger.info(f"Alerts started. Interval: {CHECK_INTERVAL}s")
    
    while not shutdown_event.is_set():
        try:
            sent = await check_drops()
            if sent:
                logger.info(f"Sent {sent} alerts")
        except Exception as e:
            logger.error(f"Error: {e}")
        
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=CHECK_INTERVAL)
        except asyncio.TimeoutError:
            pass
    
    logger.info(f"Alerts stopped. Total sent: {alerts_sent}")


def signal_handler():
    shutdown_event.set()


async def main():
    init_db_pool()
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    await alerts_loop()
    
    if db_pool:
        db_pool.closeall()


if __name__ == "__main__":
    asyncio.run(main())
