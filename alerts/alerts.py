#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alert-tjänst med asyncio loop och stöd för flera notifieringstjänster
"""

import asyncio
import sqlite3
import datetime
import requests
import os
import time
import json
import logging
import sys
import signal

# === Konfiguration ===
DB_FILE = os.getenv('DB_FILE', '/data/products.db')
SQLITE_BUSY_TIMEOUT = int(os.getenv('SQLITE_BUSY_TIMEOUT', '5000'))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '1800'))

# Notifieringsinställningar
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

MIN_DROP_PERCENT = float(os.getenv('MIN_DROP_PERCENT', '5'))
MIN_DROP_AMOUNT = int(os.getenv('MIN_DROP_AMOUNT', '100'))
COOLDOWN_HOURS = int(os.getenv('COOLDOWN_HOURS', '24'))

COOLDOWN_FILE = "/data/alert_cooldown.json"
LOG_DIR = "/logs"

os.makedirs(LOG_DIR, exist_ok=True)

# === Loggning ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/alerts.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# === Global state ===
shutdown_event = asyncio.Event()
alerts_sent = 0


def get_db_connection():
    """Hämta databasanslutning med rätt PRAGMA"""
    for attempt in range(3):
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            if attempt < 2:
                logger.warning(f"DB-anslutning misslyckades ({attempt + 1}/3): {e}")
                time.sleep(2)
            else:
                raise
    return None


def load_cooldown():
    """Ladda cooldown-data"""
    try:
        with open(COOLDOWN_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}


def save_cooldown(data):
    """Spara cooldown-data"""
    try:
        with open(COOLDOWN_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Kunde inte spara cooldown: {e}")


def send_discord_notification(webhook, title, old_price, new_price, url, drop_percent, drop_amount):
    """Skicka Discord-notis"""
    payload = {
        "embeds": [{
            "title": "💸 Prisfall upptäckt!",
            "description": f"**{title}**",
            "color": 16711680,
            "fields": [
                {"name": "📊 Gamla priset", "value": f"{old_price:,} kr".replace(",", " "), "inline": True},
                {"name": "💰 Nya priset", "value": f"{new_price:,} kr".replace(",", " "), "inline": True},
                {"name": "📉 Nedgång", "value": f"-{drop_amount:,} kr ({drop_percent:.1f}%)".replace(",", " "), "inline": True},
                {"name": "🔗 Länk", "value": url}
            ],
            "timestamp": datetime.datetime.utcnow().isoformat()
        }]
    }
    
    try:
        response = requests.post(webhook, json=payload, timeout=10)
        return response.status_code == 204
    except Exception as e:
        logger.error(f"Discord-fel: {e}")
        return False


def send_slack_notification(webhook, title, old_price, new_price, url, drop_percent, drop_amount):
    """Skicka Slack-notis"""
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💰 Prisfall upptäckt!"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*<{url}|{title}>*"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Gamla priset:*\n{old_price:,} kr".replace(",", " ")},
                    {"type": "mrkdwn", "text": f"*Nya priset:*\n{new_price:,} kr".replace(",", " ")},
                    {"type": "mrkdwn", "text": f"*Nedgång:*\n-{drop_amount:,} kr ({drop_percent:.1f}%)".replace(",", " ")}
                ]
            }
        ]
    }
    
    try:
        response = requests.post(webhook, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Slack-fel: {e}")
        return False


def send_telegram_notification(bot_token, chat_id, title, old_price, new_price, url, drop_percent, drop_amount):
    """Skicka Telegram-notis"""
    message = (
        f"💸 *Prisfall upptäckt!*\n\n"
        f"*{title}*\n"
        f"[🔗 Öppna produkt]({url})\n\n"
        f"📊 Gamla priset: {old_price:,} kr\n"
        f"💰 Nya priset: {new_price:,} kr\n"
        f"📉 Nedgång: -{drop_amount:,} kr \\({drop_percent:.1f}%\\)"
    ).replace(",", " ")
    
    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False
    }
    
    try:
        response = requests.post(telegram_url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram-fel: {e}")
        return False


async def check_price_drops():
    """Kolla efter prisfall och skicka notiser"""
    global alerts_sent
    
    conn = get_db_connection()
    if not conn:
        logger.error("Kunde inte ansluta till databasen")
        return 0
    
    try:
        cur = conn.cursor()
        cooldown = load_cooldown()
        now = time.time()
        
        # Hitta prisfall
        cur.execute("""
            SELECT 
                p.id, p.title, p.url,
                ph1.price AS old_price,
                ph2.price AS new_price
            FROM products p
            JOIN price_history ph1 ON p.id = ph1.product_id
            JOIN price_history ph2 ON p.id = ph2.product_id
            WHERE ph1.id < ph2.id
            AND ph2.timestamp = (
                SELECT MAX(timestamp) FROM price_history WHERE product_id = p.id
            )
            AND ph1.timestamp = (
                SELECT MAX(timestamp) FROM price_history 
                WHERE product_id = p.id AND id < ph2.id
            )
            AND ph2.price < ph1.price
        """)
        
        rows = cur.fetchall()
        alerts_this_run = 0
        
        for row in rows:
            product_id = row['id']
            title = row['title']
            url = row['url']
            old_price = row['old_price']
            new_price = row['new_price']
            
            drop_amount = old_price - new_price
            drop_percent = (drop_amount / old_price) * 100
            
            # Kontrollera tröskelvärden
            if drop_percent < MIN_DROP_PERCENT and drop_amount < MIN_DROP_AMOUNT:
                continue
            
            # Kontrollera cooldown
            last_alert = cooldown.get(str(product_id), 0)
            if now - last_alert < COOLDOWN_HOURS * 3600:
                continue
            
            # Skicka notiser
            sent = False
            
            if DISCORD_WEBHOOK:
                if send_discord_notification(DISCORD_WEBHOOK, title, old_price, new_price, url, drop_percent, drop_amount):
                    sent = True
            
            if SLACK_WEBHOOK:
                if send_slack_notification(SLACK_WEBHOOK, title, old_price, new_price, url, drop_percent, drop_amount):
                    sent = True
            
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                if send_telegram_notification(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, title, old_price, new_price, url, drop_percent, drop_amount):
                    sent = True
            
            if sent:
                cooldown[str(product_id)] = now
                alerts_this_run += 1
                alerts_sent += 1
                logger.info(f"Alert skickad: {title[:50]}... (-{drop_amount} kr, -{drop_percent:.1f}%)")
                
                # Liten fördröjning mellan notiser
                await asyncio.sleep(1)
        
        save_cooldown(cooldown)
        
        logger.info(f"Alerts-koll klar: {alerts_this_run} skickade")
        return alerts_this_run
        
    except Exception as e:
        logger.error(f"Fel vid alerts-koll: {e}", exc_info=True)
        return 0
    finally:
        conn.close()


async def alerts_loop():
    """Huvudloop med asyncio"""
    logger.info("=" * 60)
    logger.info("🚀 Startar Alert-tjänst")
    logger.info(f"📁 Databas: {DB_FILE}")
    logger.info(f"🔄 Intervall: {CHECK_INTERVAL} sekunder")
    logger.info("=" * 60)
    
    while not shutdown_event.is_set():
        try:
            await check_price_drops()
        except Exception as e:
            logger.error(f"Kritiskt fel i loop: {e}", exc_info=True)
        
        # Vänta med möjlighet att avbryta
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=CHECK_INTERVAL)
        except asyncio.TimeoutError:
            pass
    
    logger.info(f"👋 Alert-tjänst avslutad. Totalt skickade: {alerts_sent}")


def signal_handler():
    """Hantera shutdown-signaler"""
    logger.info("Mottog shutdown-signal")
    shutdown_event.set()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Registrera signalhanterare
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        loop.run_until_complete(alerts_loop())
    except KeyboardInterrupt:
        logger.info("Avbruten av användare")
    finally:
        loop.close()
