#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL-based API - Production version with connection pooling
"""

import os
import logging
import sys
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_NAME = os.getenv('DB_NAME', 'scraper')
DB_USER = os.getenv('DB_USER', 'scraper')
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')

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
    conn = db_pool.getconn()
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        try:
            db_pool.putconn(conn, close=True)
        except Exception as cleanup_err:
            logger.debug("Failed to discard stale connection: %s", cleanup_err)
        conn = db_pool.getconn()
    return conn

def return_db(conn):
    try:
        conn.rollback()
    except Exception:
        db_pool.putconn(conn, close=True)
        return
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
    if request.url.path in ["/health", "/docs", "/openapi.json", "/", "/redoc"]:
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
    conn = None
    try:
        conn = get_db()
        conn.cursor().execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "timestamp": datetime.utcnow().isoformat()}
    except Exception:
        return {"status": "unhealthy", "error": "Database connection failed"}
    finally:
        if conn:
            return_db(conn)

@app.get("/products")
def get_products(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), search: Optional[str] = Query(None)):
    conn = get_db()
    try:
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
        return {"products": products, "total": total, "limit": limit, "offset": offset}
    finally:
        return_db(conn)

@app.get("/stats")
def get_stats():
    conn = get_db()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) FROM products")
        total_products = cur.fetchone()['count']
        cur.execute("SELECT COUNT(DISTINCT product_id) FROM price_history WHERE timestamp >= NOW() - INTERVAL '1 day'")
        updated_24h = cur.fetchone()['count']
        cur.execute("SELECT COUNT(*) FROM scraper_config WHERE enabled = 1")
        active_configs = cur.fetchone()['count']
        return {"total_products": total_products, "updated_24h": updated_24h, "active_configs": active_configs}
    finally:
        return_db(conn)

@app.get("/products/{product_id}/history")
def get_product_history(product_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, title, current_price FROM products WHERE id = %s", (product_id,))
        product = cur.fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        cur.execute(
            "SELECT price, timestamp FROM price_history WHERE product_id = %s ORDER BY timestamp ASC LIMIT 100",
            (product_id,)
        )
        history = cur.fetchall()
        return {"product_id": product_id, "title": product["title"], "history": history}
    finally:
        return_db(conn)


@app.get("/deals")
def get_deals():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                p.id, p.title, p.url, p.current_price,
                ph_old.price AS old_price,
                ROUND((1 - p.current_price::numeric / NULLIF(ph_old.price, 0)) * 100)::int AS discount_pct,
                ph_new.timestamp AS updated_at
            FROM products p
            JOIN LATERAL (
                SELECT price, timestamp FROM price_history
                WHERE product_id = p.id
                ORDER BY timestamp DESC LIMIT 1
            ) ph_new ON true
            JOIN LATERAL (
                SELECT price FROM price_history
                WHERE product_id = p.id
                  AND timestamp <= NOW() - INTERVAL '1 day'
                ORDER BY timestamp DESC LIMIT 1
            ) ph_old ON true
            WHERE p.current_price > 0
              AND ph_old.price > 0
              AND p.current_price < ph_old.price
              AND ph_new.timestamp >= NOW() - INTERVAL '7 days'
            ORDER BY discount_pct DESC
            LIMIT 50
        """)
        deals = cur.fetchall()
        return {"deals": deals}
    finally:
        return_db(conn)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
