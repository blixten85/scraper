#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI Control Plane - Hanterar konfiguration och övervakning
"""

import os
import json
import sqlite3
import logging
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# === Konfiguration ===
DB_FILE = os.getenv('DB_FILE', '/data/products.db')
SQLITE_BUSY_TIMEOUT = int(os.getenv('SQLITE_BUSY_TIMEOUT', '5000'))
SCRAPER_API = os.getenv('SCRAPER_API', 'http://scraper_api:8000')

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Hämta databasanslutning"""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
    conn.row_factory = sqlite3.Row
    return conn


def get_stats_from_db():
    """Hämta statistik från databasen"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM products")
        total_products = cur.fetchone()[0]
        
        cur.execute("""
            SELECT COUNT(DISTINCT product_id) 
            FROM price_history 
            WHERE timestamp >= datetime('now', '-1 day')
        """)
        updated_24h = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM scraper_config WHERE enabled = 1")
        active_configs = cur.fetchone()[0]
        
        cur.execute("SELECT MAX(timestamp) FROM price_history")
        last_run = cur.fetchone()[0]
        
        conn.close()
        
        return {
            'total_products': total_products,
            'updated_24h': updated_24h,
            'active_configs': active_configs,
            'last_run': last_run
        }
    except:
        return {
            'total_products': 0,
            'updated_24h': 0,
            'active_configs': 0,
            'last_run': None
        }


@app.route('/')
def index():
    """Dashboard"""
    stats = get_stats_from_db()
    return render_template('index.html', stats=stats)


@app.route('/config')
def config_page():
    """Konfigurationssida"""
    return render_template('config.html')


@app.route('/health')
def health():
    """Hälsokontroll"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/api/stats')
def api_stats():
    """Hämta statistik"""
    return jsonify(get_stats_from_db())


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=False)
