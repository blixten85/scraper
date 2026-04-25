#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI Control Plane - Proxyrar anrop till API och Scraper Engine
"""

import os
import logging
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

SCRAPER_API = os.getenv('SCRAPER_API', 'http://scraper_api:8000')
SCRAPER_ENGINE = os.getenv('SCRAPER_ENGINE', 'http://scraper_engine:5001')

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def read_secret(env_var, default=""):
    path = os.getenv(f"{env_var}_FILE")
    if path and os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return os.getenv(env_var, default)

API_KEY = None
def get_api_key():
    global API_KEY
    if API_KEY is None:
        API_KEY = read_secret("API_KEY")
    return API_KEY

def engine_request(method, path, **kwargs):
    url = f"{SCRAPER_ENGINE}{path}"
    return requests.request(method, url, **kwargs)

def api_request(method, path, **kwargs):
    url = f"{SCRAPER_API}{path}"
    headers = kwargs.pop('headers', {})
    headers['X-API-Key'] = get_api_key()
    return requests.request(method, url, headers=headers, **kwargs)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config')
def config_page():
    return render_template('config.html')

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()})

@app.route('/api/configs', methods=['GET'])
def get_configs():
    try:
        resp = engine_request('GET', '/config')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"Engine error: {e}")
        return jsonify([]), 200

@app.route('/api/configs', methods=['POST'])
def create_config():
    try:
        resp = engine_request('POST', '/config', json=request.json)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"Create config error: {e}")
        return jsonify({'error': 'Internal server error'}), 503

@app.route('/api/configs/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    try:
        resp = engine_request('DELETE', f'/config/{config_id}')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"Delete config error: {e}")
        return jsonify({'error': 'Internal server error'}), 503

@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    try:
        resp = engine_request('POST', '/scrape')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"Trigger scrape error: {e}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 503

@app.route('/api/test', methods=['POST'])
def test_scrape():
    try:
        resp = engine_request('POST', '/test', json=request.json)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        logger.error(f"Test scrape error: {e}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 503

@app.route('/api/stats')
def get_stats():
    try:
        resp = api_request('GET', '/stats')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'total_products': 0, 'updated_24h': 0, 'active_configs': 0})

@app.route('/api/products')
def get_products():
    try:
        resp = api_request('GET', '/products', params=request.args)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'products': [], 'total': 0})

if __name__ == '__main__':
    port = int(os.getenv('PORT', '3000'))
    app.run(host='0.0.0.0', port=port, debug=False)
