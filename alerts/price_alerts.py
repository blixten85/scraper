#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import datetime
import requests
import os
import time
import json
import logging
import sys
import signal

# === Loggning ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/logs/alerts.log", encoding="utf-8") if os.path.exists("/logs") else logging.NullHandler(),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# === Konfiguration ===
DB_FILE = os.getenv("DB_FILE", "/data/products.db")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
SQLITE_BUSY_TIMEOUT = int(os.getenv("SQLITE_BUSY_TIMEOUT", "5000"))

MIN_DROP_PERCENT = float(os.getenv("MIN_DROP_PERCENT", "5"))
MIN_DROP_AMOUNT = int(os.getenv("MIN_DROP_AMOUNT", "100"))

COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "24"))
COOLDOWN_FILE = "/data/alert_cooldown.json"
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "1800"))

# === Metrics ===
METRICS_FILE = "/data/alerts_metrics.json"
shutdown_event = False
alerts_sent_total = 0
alerts_sent_24h = 0


def validate_config():
    """Validera att nödvändig konfiguration finns"""
    if not DISCORD_WEBHOOK:
        logger.error("DISCORD_WEBHOOK saknas! Alerts-tjänsten kan inte skicka notiser.")
        logger.error("Sätt DISCORD_WEBHOOK i din .env-fil eller som miljövariabel.")
        sys.exit(1)
    
    if not os.path.exists(DB_FILE):
        logger.error(f"Databasfilen {DB_FILE} hittades inte!")
        logger.error("Väntar på att scraper-tjänsten ska skapa databasen...")
        return False
    
    logger.info("Konfiguration validerad OK")
    return True


def get_db():
    """Hämta databasanslutning med retry-logik"""
    for attempt in range(3):
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
            conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
            return conn
        except sqlite3.Error as e:
            if attempt < 2:
                logger.warning(f"Databasanslutning misslyckades, försöker igen ({attempt + 1}/3): {e}")
                time.sleep(2)
            else:
                raise
    return None


def load_cooldown():
    """Ladda cooldown-data"""
    try:
        with open(COOLDOWN_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.info("Ingen cooldown-fil hittades, skapar ny")
        return {}
    except json.JSONDecodeError:
        logger.warning("Cooldown-filen är korrupt, skapar ny")
        return {}


def save_cooldown(data):
    """Spara cooldown-data"""
    try:
        with open(COOLDOWN_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Kunde inte spara cooldown: {e}")


def load_metrics():
    """Ladda metrics från tidigare körningar"""
    global alerts_sent_total, alerts_sent_24h
    try:
        with open(METRICS_FILE, "r") as f:
            data = json.load(f)
            alerts_sent_total = data.get("total", 0)
            # Rensa 24h-räknaren vid uppstart
            alerts_sent_24h = 0
    except:
        pass


def save_metrics():
    """Spara metrics till fil"""
    try:
        with open(METRICS_FILE, "w") as f:
            json.dump({
                "total": alerts_sent_total,
                "last_updated": datetime.datetime.utcnow().isoformat()
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Kunde inte spara metrics: {e}")


def send_discord(title, old_price, new_price, url):
    """Skicka Discord-notis om prisfall"""
    global alerts_sent_total, alerts_sent_24h
    
    if not DISCORD_WEBHOOK:
        logger.error("Ingen Discord webhook konfigurerad")
        return False

    drop = old_price - new_price
    percent = round((drop / old_price) * 100, 1)

    payload = {
        "embeds": [
            {
                "title": "💸 Prisfall upptäckt!",
                "description": f"**{title}**",
                "color": 16711680,  # Röd
                "fields": [
                    {"name": "📊 Gamla priset", "value": f"{old_price:,} kr".replace(",", " "), "inline": True},
                    {"name": "💰 Nya priset", "value": f"{new_price:,} kr".replace(",", " "), "inline": True},
                    {"name": "📉 Nedgång", "value": f"-{drop:,} kr ({percent}%)".replace(",", " "), "inline": True},
                    {"name": "🔗 Länk", "value": url}
                ],
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "footer": {"text": "Inet.se Price Tracker"}
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if response.status_code == 204:
            logger.info(f"✅ Alert skickad: {title[:50]}... (-{drop} kr, -{percent}%)")
            alerts_sent_total += 1
            alerts_sent_24h += 1
            save_metrics()
            return True
        else:
            logger.error(f"Discord API fel: {response.status_code} - {response.text}")
            return False
    except requests.exceptions.Timeout:
        logger.error("Timeout vid anslutning till Discord")
        return False
    except Exception as e:
        logger.error(f"Discord fel: {e}")
        return False


def cleanup_old_cooldown(cooldown, now, max_age_days=7):
    """Ta bort gamla cooldown-poster"""
    cutoff = now - (max_age_days * 24 * 3600)
    cleaned = {k: v for k, v in cooldown.items() if v > cutoff}
    
    if len(cleaned) < len(cooldown):
        logger.info(f"Rensade {len(cooldown) - len(cleaned)} gamla cooldown-poster")
    
    return cleaned


def check_price_drops():
    """Huvudfunktion för att kolla prisfall"""
    global alerts_sent_total, alerts_sent_24h
    
    if not validate_config():
        return 0
    
    conn = None
    try:
        conn = get_db()
        if not conn:
            logger.error("Kunde inte ansluta till databasen")
            return 0
            
        cur = conn.cursor()

        cooldown = load_cooldown()
        now = time.time()
        
        # Rensa gamla cooldowns (äldre än 7 dagar)
        cooldown = cleanup_old_cooldown(cooldown, now)

        # Hämta alla prisfall
        cur.execute("""
            SELECT 
                p.id, 
                p.title, 
                p.url,
                ph1.price AS old_price,
                ph2.price AS new_price,
                ph1.timestamp AS old_date,
                ph2.timestamp AS new_date
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
            ORDER BY ((ph1.price - ph2.price) * 100.0 / ph1.price) DESC
        """)

        rows = cur.fetchall()
        alerts_sent = 0
        skipped_cooldown = 0
        skipped_threshold = 0

        logger.info(f"Hittade {len(rows)} potentiella prisfall")

        for row in rows:
            product_id, title, url, old_price, new_price, old_date, new_date = row

            if not old_price or not new_price or old_price <= 0:
                continue

            drop_percent = ((old_price - new_price) / old_price) * 100
            drop_amount = old_price - new_price

            # Kontrollera tröskelvärden
            if drop_percent < MIN_DROP_PERCENT and drop_amount < MIN_DROP_AMOUNT:
                skipped_threshold += 1
                continue

            # Kontrollera cooldown
            last_alert = cooldown.get(str(product_id), 0)
            if now - last_alert < COOLDOWN_HOURS * 3600:
                skipped_cooldown += 1
                continue

            # Skicka alert
            if send_discord(title, old_price, new_price, url):
                cooldown[str(product_id)] = now
                alerts_sent += 1
                
                # Lite fördröjning mellan alerts för att inte överbelasta Discord
                time.sleep(1)

        # Spara uppdaterad cooldown
        save_cooldown(cooldown)

        logger.info("=" * 60)
        logger.info(f"✅ Prisfallscheck klar!")
        logger.info(f"   📨 Skickade alerts: {alerts_sent}")
        logger.info(f"   ⏭️  Skippade (cooldown): {skipped_cooldown}")
        logger.info(f"   📊 Skippade (under tröskel): {skipped_threshold}")
        logger.info(f"   📈 Totalt skickade alerts: {alerts_sent_total}")
        logger.info("=" * 60)

        return alerts_sent

    except sqlite3.Error as e:
        logger.error(f"Databasfel: {e}")
        return 0
    except Exception as e:
        logger.error(f"Ohanterat fel i check_price_drops: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()


def signal_handler(signum, frame):
    """Hantera shutdown-signaler"""
    global shutdown_event
    logger.info(f"Mottog signal {signum}, stänger ner...")
    shutdown_event = True
    save_metrics()


def run_loop():
    """Huvudloop för tjänsten"""
    # Registrera signalhanterare
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Ladda tidigare metrics
    load_metrics()
    
    logger.info("=" * 60)
    logger.info("🚀 Startar Inet.se Price Alerts-tjänst")
    logger.info(f"📁 Databas: {DB_FILE}")
    logger.info(f"📊 Min drop: {MIN_DROP_PERCENT}% eller {MIN_DROP_AMOUNT} kr")
    logger.info(f"⏱️  Cooldown: {COOLDOWN_HOURS} timmar")
    logger.info(f"🔄 Intervall: {SLEEP_INTERVAL} sekunder")
    logger.info("=" * 60)

    while not shutdown_event:
        try:
            check_price_drops()
        except Exception as e:
            logger.error(f"Kritiskt fel i huvudloopen: {e}", exc_info=True)
        
        # Vänta med uppdelad sleep för att kunna hantera shutdown
        if not shutdown_event:
            for _ in range(SLEEP_INTERVAL):
                if shutdown_event:
                    break
                time.sleep(1)

    logger.info(f"👋 Alerts-tjänst avslutad. Totalt skickade alerts: {alerts_sent_total}")
    save_metrics()


if __name__ == "__main__":
    run_loop()
