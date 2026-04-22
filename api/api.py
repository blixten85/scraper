#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL-based API - Production version with connection pooling
"""

import os
import logging
import sys
import csv
from io import StringIO
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_NAME = os.getenv('DB_NAME', 'scraper')
DB_USER = os.getenv('DB_USER', 'scraper')
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'https://scraper.denied.se').split(',')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
        host=DB_HOST, database=DB_NAME, user=DB_USER,
        password=db_password, connect_timeout=10
    )
    logger.info("Database connection pool initialized")

def get_db():
    return db_pool.getconn()

def return_db(conn):
    db_pool.putconn(conn)

app = FastAPI(
    title="Web Scraper API",
    description="Production API for price monitoring",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

API_KEY = None
def get_api_key():
    global API_KEY
    if API_KEY is None:
        API_KEY = read_secret("API_KEY")
    return API_KEY

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    if request.url.path in ["/health", "/docs", "/openapi.json", "/", "/redoc", "/configs"]:
        return await call_next(request)
    if request.headers.get("X-API-Key") != get_api_key():
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await call_next(request)

@app.on_event("startup")
async def startup():
    init_db_pool()

@app.on_event("shutdown")
async def shutdown():
    if db_pool:
        db_pool.closeall()

@app.get("/health")
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        return_db(conn)
        return {"status": "healthy", "database": "connected", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/products")
def get_products(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), search: Optional[str] = Query(None)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    query = "SELECT id, title, url, current_price, first_seen, last_updated FROM products"
    params = []
    if search:
        query += " WHERE title ILIKE %s"
        params.append(f"%{search}%")
    query += " ORDER BY last_updated DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    cur.execute(query, params)
    products = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM products" + (" WHERE title ILIKE %s" if search else ""), params[:-2] if search else [])
    total = cur.fetchone()['count']
    return_db(conn)
    return {"products": products, "total": total, "limit": limit, "offset": offset}

@app.get("/stats")
def get_stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()['count']
    cur.execute("SELECT COUNT(DISTINCT product_id) FROM price_history WHERE timestamp >= NOW() - INTERVAL '1 day'")
    updated_24h = cur.fetchone()['count']
    return_db(conn)
    return {"total_products": total_products, "updated_24h": updated_24h, "active_configs": 1}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
