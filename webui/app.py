#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebUI Control Plane - Proxyrar allt till API:et
"""

import os
import logging
import requests
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS

# === Konfiguration ===
SCRAPER_API = os.getenv('SCRAPER_API', 'http://scraper_api:8000')

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# === Hjälpfunktion för secrets ===
def read_secret(env_var, default=""):
    """Läs secret från fil eller env"""
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


def api_request(method, path, **kwargs):
    """Proxy-request till API:et med API-nyckel"""
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
        resp = api_request('GET', '/config')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/configs', methods=['POST'])
def create_config():
    try:
        resp = api_request('POST', '/config', json=request.json)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/configs/<int:config_id>', methods=['PUT'])
def update_config(config_id):
    try:
        resp = api_request('PUT', f'/config/{config_id}', json=request.json)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/configs/<int:config_id>', methods=['DELETE'])
def delete_config(config_id):
    try:
        resp = api_request('DELETE', f'/config/{config_id}')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/test', methods=['POST'])
def test_config():
    try:
        resp = api_request('POST', '/test', json=request.json)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    try:
        resp = api_request('POST', '/scrape')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/stats')
def get_stats():
    try:
        resp = api_request('GET', '/stats')
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/products')
def get_products():
    try:
        resp = api_request('GET', '/products', params=request.args)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 503


@app.route('/api/docs')
@app.route('/api/docs/<path:path>')
def proxy_api_docs(path=''):
    try:
        url = f"{SCRAPER_API}/docs"
        if path:
            url = f"{SCRAPER_API}/docs/{path}"
        resp = requests.get(url)
        return Response(resp.content, resp.status_code, resp.raw.headers.items())
    except Exception as e:
        return f"API proxy error: {e}", 503


@app.route('/openapi.json')
def proxy_openapi():
    try:
        resp = requests.get(f"{SCRAPER_API}/openapi.json")
        return Response(resp.content, resp.status_code, resp.raw.headers.items())
    except Exception as e:
        return f"Error: {e}", 503


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=False)
