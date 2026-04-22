#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI Control Plane
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/config')
def config_page():
    return render_template('config.html')

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/api/configs')
def get_configs():
    try:
        resp = engine_request('GET', '/config')
        return jsonify(resp.json())
    except:
        return jsonify([])

@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    try:
        resp = engine_request('POST', '/scrape')
        return jsonify(resp.json())
    except:
        return jsonify({'status': 'error'}), 503

@app.route('/api/stats')
def get_stats():
    try:
        resp = requests.get(f"{SCRAPER_API}/stats", headers={'X-API-Key': get_api_key()})
        return jsonify(resp.json())
    except:
        return jsonify({'total_products': 0})

@app.route('/api/products')
def get_products():
    try:
        resp = requests.get(f"{SCRAPER_API}/products", params=request.args, headers={'X-API-Key': get_api_key()})
        return jsonify(resp.json())
    except:
        return jsonify({'products': [], 'total': 0})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=False)
