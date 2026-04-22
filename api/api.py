#!/usr/bin/env python3

# -*- coding: utf-8 -*-

“””
PostgreSQL-baserat API - Produktionsversion med connection pooling
“””

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

# === Konfiguration ===

DB_HOST = os.getenv(‘DB_HOST’, ‘postgres’)
DB_NAME = os.getenv(‘DB_NAME’, ‘scraper’)
DB_USER = os.getenv(‘DB_USER’, ‘scraper’)
ALLOWED_ORIGINS = os.getenv(‘ALLOWED_ORIGINS’, ‘https://scraper.denied.se’).split(’,’)

# === Loggning ===

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s - %(levelname)s - %(message)s”,
handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(**name**)

# === Hjälpfunktion för secrets ===

def read_secret(env_var, default=””):
“”“Läs secret från fil eller env”””
path = os.getenv(f”{env_var}_FILE”)
if path and os.path.exists(path):
with open(path) as f:
return f.read().strip()
return os.getenv(env_var, default)

# === Connection Pool ===

db_pool = None

def init_db_pool():
global db_pool
db_password = read_secret(“DB_PASSWORD”)

```
db_pool = ThreadedConnectionPool(
    minconn=1,
    maxconn=10,
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=db_password,
    connect_timeout=10
)
logger.info("Database connection pool initialized")
```

def get_db():
return db_pool.getconn()

def return_db(conn):
db_pool.putconn(conn)

# === FastAPI app ===

app = FastAPI(
title=“Web Scraper API”,
description=“Produktions-API för prisbevakning”,
version=“4.0.0”,
docs_url=”/docs”,
redoc_url=”/redoc”
)

app.add_middleware(
CORSMiddleware,
allow_origins=ALLOWED_ORIGINS,
allow_credentials=True,
allow_methods=[”*”],
allow_headers=[”*”],
)

# === API Key Middleware ===

API_KEY = None

def get_api_key():
global API_KEY
if API_KEY is None:
API_KEY = read_secret(“API_KEY”)
return API_KEY

@app.middleware(“http”)
async def check_api_key(request: Request, call_next):
if request.url.path in [”/health”, “/docs”, “/openapi.json”, “/”, “/redoc”]:
return await call_next(request)

```
if request.headers.get("X-API-Key") != get_api_key():
    raise HTTPException(status_code=401, detail="Unauthorized - Invalid API Key")

return await call_next(request)
```

@app.on_event(“startup”)
async def startup():
init_db_pool()

@app.on_event(“shutdown”)
async def shutdown():
if db_pool:
db_pool.closeall()

@app.get(”/”, tags=[“Root”])
def root():
return {
“message”: “Web Scraper API”,
“status”: “running”,
“version”: “4.0.0”
}

@app.get(”/health”, tags=[“Health”])
def health_check():
try:
conn = get_db()
cur = conn.cursor()
cur.execute(“SELECT 1”)
return_db(conn)
return {“status”: “healthy”, “database”: “connected”, “timestamp”: datetime.utcnow().isoformat()}
except Exception as e:
return {“status”: “unhealthy”, “error”: str(e), “timestamp”: datetime.utcnow().isoformat()}

@app.get(”/products”, tags=[“Products”])
def get_products(
limit: int = Query(100, ge=1, le=1000),
offset: int = Query(0, ge=0),
search: Optional[str] = Query(None),
sort: str = Query(“last_updated”),
order: str = Query(“desc”)
):
conn = get_db()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

```
allowed_sort = ["last_updated", "current_price", "title", "first_seen"]
if sort not in allowed_sort:
    sort = "last_updated"

order_clause = "DESC" if order.lower() == "desc" else "ASC"

query = "SELECT id, title, url, current_price, first_seen, last_updated FROM products"
count_query = "SELECT COUNT(*) FROM products"
params = []

if search:
    query += " WHERE title ILIKE %s"
    count_query += " WHERE title ILIKE %s"
    params.append(f"%{search}%")

cur.execute(count_query, params)
total = cur.fetchone()['count']

query += f" ORDER BY {sort} {order_clause} LIMIT %s OFFSET %s"
params.extend([limit, offset])

cur.execute(query, params)
products = cur.fetchall()
return_db(conn)

return {
    "products": products,
    "total": total,
    "limit": limit,
    "offset": offset
}
```

@app.get(”/products/{product_id}”, tags=[“Products”])
def get_product(product_id: int):
conn = get_db()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

```
cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
row = cur.fetchone()
return_db(conn)

if not row:
    raise HTTPException(status_code=404, detail="Produkt ej hittad")

return dict(row)
```

@app.get(”/products/{product_id}/history”, tags=[“Products”])
def get_price_history(product_id: int, limit: int = Query(100, le=1000)):
conn = get_db()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

```
cur.execute("SELECT title FROM products WHERE id = %s", (product_id,))
product = cur.fetchone()

if not product:
    return_db(conn)
    raise HTTPException(status_code=404, detail="Produkt ej hittad")

cur.execute("""
    SELECT price, timestamp
    FROM price_history
    WHERE product_id = %s
    ORDER BY timestamp DESC
    LIMIT %s
""", (product_id, limit))

history = cur.fetchall()

cur.execute("""
    SELECT MIN(price) as min_price, MAX(price) as max_price, AVG(price) as avg_price
    FROM price_history WHERE product_id = %s
""", (product_id,))
stats = cur.fetchone()

return_db(conn)

return {
    "product_id": product_id,
    "product_title": product['title'],
    "history": history,
    "statistics": dict(stats) if stats else {}
}
```

@app.get(”/deals”, tags=[“Deals”])
def get_deals(
min_drop_percent: float = Query(5, ge=0),
min_drop_amount: int = Query(50, ge=0),
limit: int = Query(50, le=100),
hours: int = Query(168, ge=1)
):
conn = get_db()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

```
cur.execute("""
    SELECT *
    FROM (
        SELECT 
            p.id,
            p.title,
            p.url,
            ph.price AS new_price,
            LAG(ph.price) OVER (PARTITION BY p.id ORDER BY ph.timestamp) AS old_price,
            ph.timestamp AS new_date,
            LAG(ph.timestamp) OVER (PARTITION BY p.id ORDER BY ph.timestamp) AS old_date
        FROM products p
        JOIN price_history ph ON p.id = ph.product_id
        WHERE ph.timestamp >= NOW() - INTERVAL '%s hours'
    ) t
    WHERE old_price IS NOT NULL AND new_price < old_price
""", (hours,))

deals = []
for row in cur.fetchall():
    drop_amount = row['old_price'] - row['new_price']
    drop_percent = (drop_amount / row['old_price']) * 100
    
    if drop_percent >= min_drop_percent and drop_amount >= min_drop_amount:
        deals.append({
            "id": row['id'],
            "title": row['title'],
            "url": row['url'],
            "old_price": row['old_price'],
            "new_price": row['new_price'],
            "drop_amount": drop_amount,
            "drop_percent": round(drop_percent, 1),
            "old_date": row['old_date'].isoformat() if row['old_date'] else None,
            "new_date": row['new_date'].isoformat() if row['new_date'] else None
        })

return_db(conn)

deals.sort(key=lambda x: x['drop_percent'], reverse=True)

return {
    "deals": deals[:limit],
    "count": len(deals[:limit])
}
```

@app.get(”/stats”, tags=[“Statistics”])
def get_stats():
conn = get_db()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

```
cur.execute("SELECT COUNT(*) FROM products")
total_products = cur.fetchone()['count']

cur.execute("SELECT COUNT(*) FROM price_history")
total_history = cur.fetchone()['count']

cur.execute("""
    SELECT COUNT(DISTINCT product_id) 
    FROM price_history 
    WHERE timestamp >= NOW() - INTERVAL '1 day'
""")
updated_24h = cur.fetchone()['count']

cur.execute("SELECT AVG(current_price) FROM products")
avg_price = cur.fetchone()['avg']

cur.execute("SELECT MAX(timestamp) FROM price_history")
last_run = cur.fetchone()['max']

active_configs = 0  # Hanteras av scraper_engine, inte API

return_db(conn)

return {
    "total_products": total_products,
    "total_price_records": total_history,
    "updated_24h": updated_24h,
    "average_price": round(avg_price, 2) if avg_price else 0,
    "last_run": last_run.isoformat() if last_run else None,
    "active_configs": active_configs
}
```

@app.get(”/export/csv”, tags=[“Export”])
def export_csv():
conn = get_db()
cur = conn.cursor()

```
cur.execute("""
    SELECT id, title, url, current_price, first_seen, last_updated
    FROM products ORDER BY last_updated DESC
""")

output = StringIO()
writer = csv.writer(output)
writer.writerow(["ID", "Title", "URL", "Price (SEK)", "First Seen", "Last Updated"])

for row in cur.fetchall():
    writer.writerow([row[0], row[1], row[2], row[3], row[4], row[5]])

return_db(conn)
output.seek(0)

return StreamingResponse(
    iter([output.getvalue()]),
    media_type="text/csv",
    headers={"Content-Disposition": f"attachment; filename=products_{datetime.now().strftime('%Y%m%d')}.csv"}
)
```

if **name** == “**main**”:
import uvicorn
uvicorn.run(app, host=“0.0.0.0”, port=8000)
