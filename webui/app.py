#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI Control Plane - Förenklad version
"""

import os
import json
import sqlite3
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# === Konfiguration ===
DB_FILE = os.getenv('DB_FILE', '/data/products.db')
SQLITE_BUSY_TIMEOUT = int(os.getenv('SQLITE_BUSY_TIMEOUT', '5000'))

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Hämta databasanslutning"""
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"DB connection error: {e}")
        raise


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
        
        conn.close()
        
        return {
            'total_products': total_products,
            'updated_24h': updated_24h,
            'active_configs': active_configs
        }
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {
            'total_products': 0,
            'updated_24h': 0,
            'active_configs': 1
        }


@app.route('/')
def index():
    """Dashboard"""
    return render_template('index.html')


@app.route('/config')
def config_page():
    """Konfigurationssida"""
    return render_template('config.html')


@app.route('/health')
def health():
    """Hälsokontroll"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/api/configs', methods=['GET'])
def get_configs():
    """Hämta alla konfigurationer"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM scraper_config ORDER BY name")
        configs = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(configs)
    except Exception as e:
        logger.error(f"Configs error: {e}")
        return jsonify([])


@app.route('/api/stats')
def api_stats():
    """Hämta statistik"""
    return jsonify(get_stats_from_db())


@app.route('/api/products')
def get_products():
    """Hämta produkter"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    search = request.args.get('search', '')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        query = "SELECT id, title, url, current_price, last_updated FROM products"
        count_query = "SELECT COUNT(*) FROM products"
        params = []
        
        if search:
            query += " WHERE title LIKE ?"
            count_query += " WHERE title LIKE ?"
            params.append(f"%{search}%")
        
        query += " ORDER BY last_updated DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cur.execute(count_query, params[:-2] if search else [])
        total = cur.fetchone()[0]
        
        cur.execute(query, params)
        products = [dict(row) for row in cur.fetchall()]
        
        conn.close()
        
        return jsonify({
            'products': products,
            'total': total,
            'limit': limit,
            'offset': offset
        })
    except Exception as e:
        logger.error(f"Products error: {e}")
        return jsonify({'products': [], 'total': 0})


@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    """Starta manuell scraping"""
    return jsonify({'status': 'success', 'message': 'Scraping triggered (simulated)'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=False)
