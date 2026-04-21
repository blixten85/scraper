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
SCRAPER_API = os.getenv('SCRAPER_API', 'http://scraper_engine:5001')

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
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return {
            'total_products': 0,
            'updated_24h': 0,
            'active_configs': 1,  # Visa att scraper är aktiv
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
    # Hämta configs från scraper API eller DB
    try:
        response = requests.get(f"{SCRAPER_API}/config", timeout=5)
        configs = response.json()
    except:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM scraper_config ORDER BY name")
        configs = [dict(row) for row in cur.fetchall()]
        conn.close()
    
    # Första config som default
    default_config = configs[0] if configs else {
        'name': 'Default',
        'enabled': True
    }
    
    return render_template('config.html', config=default_config)


@app.route('/health')
def health():
    """Hälsokontroll"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})


@app.route('/api/configs', methods=['GET'])
def get_configs():
    """Hämta alla konfigurationer"""
    try:
        response = requests.get(f"{SCRAPER_API}/config", timeout=5)
        return jsonify(response.json())
    except Exception as e:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM scraper_config ORDER BY name")
        configs = [dict(row) for row in cur.fetchall()]
        conn.close()
        return jsonify(configs)


@app.route('/api/configs', methods=['POST'])
def create_config():
    """Skapa ny konfiguration"""
    try:
        response = requests.post(
            f"{SCRAPER_API}/config",
            json=request.json,
            timeout=10
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Kunde inte nå scraper API: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 503


@app.route('/api/configs/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    """Uppdatera konfiguration"""
    try:
        response = requests.put(
            f"{SCRAPER_API}/config/{config_id}",
            json=request.json,
            timeout=10
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 503


@app.route('/api/configs/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    """Ta bort/inaktivera konfiguration"""
    try:
        response = requests.delete(
            f"{SCRAPER_API}/config/{config_id}",
            timeout=10
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 503


@app.route('/api/test', methods=['POST'])
def test_config():
    """Testa en konfiguration - preview"""
    try:
        response = requests.post(
            f"{SCRAPER_API}/test",
            json=request.json,
            timeout=30
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 503


@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    """Starta manuell scraping"""
    try:
        response = requests.post(
            f"{SCRAPER_API}/scrape",
            timeout=5
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 503


@app.route('/api/stats')
def api_stats():
    """Hämta statistik"""
    return jsonify(get_stats_from_db())


@app.route('/api/products')
def get_products():
    """Hämta produkter"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    search = request.args.get('search', '')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM products"
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=False)
