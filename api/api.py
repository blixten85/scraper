#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generiskt API för prisdata
"""

import sqlite3
import os
import logging
import sys
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import csv
from io import StringIO

# === Konfiguration ===
CONFIG_FILE = os.getenv('CONFIG_FILE', '/config/scraper_config.json')
DB_FILE = os.getenv('DB_FILE', '/data/products.db')
SQLITE_BUSY_TIMEOUT = int(os.getenv('SQLITE_BUSY_TIMEOUT', '5000'))

# === Loggning ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# === FastAPI app ===
app = FastAPI(
    title="Web Scraper API",
    description="Generiskt API för prisbevakning",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_config():
    """Ladda konfiguration"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"name": "Unknown"}


def get_db():
    """Hämta databasanslutning"""
    try:
        if not os.path.exists(DB_FILE):
            raise FileNotFoundError(f"Databasfil saknas: {DB_FILE}")
        
        conn = sqlite3.connect(DB_FILE, timeout=10)
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT};")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"DB-fel: {e}")
        raise HTTPException(status_code=503, detail="Databas ej tillgänglig")


@app.get("/", tags=["Root"])
def root():
    """Hälsokontroll"""
    config = load_config()
    return {
        "message": f"Web Scraper API - {config.get('name', 'Unknown')}",
        "status": "running",
        "version": "2.0.0"
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Detaljerad hälsokontroll"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        
        db_exists = os.path.exists(DB_FILE)
        db_size = os.path.getsize(DB_FILE) / (1024 * 1024) if db_exists else 0
        
        return {
            "status": "healthy",
            "database": "connected",
            "database_size_mb": round(db_size, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/config", tags=["Configuration"])
def get_config():
    """Hämta aktuell konfiguration"""
    return load_config()


@app.get("/products", tags=["Products"])
def get_products(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    sort: str = Query("last_updated"),
    order: str = Query("desc")
):
    """Hämta produkter med paginering och sökning"""
    conn = get_db()
    cur = conn.cursor()
    
    # Validera sortering
    allowed_sort = ["last_updated", "current_price", "title", "first_seen"]
    if sort not in allowed_sort:
        sort = "last_updated"
    
    order_clause = "DESC" if order.lower() == "desc" else "ASC"
    
    # Bygg query
    query = "SELECT id, title, url, current_price, first_seen, last_updated FROM products"
    count_query = "SELECT COUNT(*) FROM products"
    params = []
    
    if search:
        query += " WHERE title LIKE ?"
        count_query += " WHERE title LIKE ?"
        params.append(f"%{search}%")
    
    # Hämta totalt antal
    cur.execute(count_query, params)
    total = cur.fetchone()[0]
    
    # Hämta produkter
    query += f" ORDER BY {sort} {order_clause} LIMIT ? OFFSET ?"
    cur.execute(query, params + [limit, offset])
    
    products = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return {
        "products": products,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@app.get("/products/{product_id}", tags=["Products"])
def get_product(product_id: int):
    """Hämta enskild produkt"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, title, url, current_price, first_seen, last_updated
        FROM products WHERE id = ?
    """, (product_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Produkt ej hittad")
    
    return dict(row)


@app.get("/products/{product_id}/history", tags=["Products"])
def get_price_history(product_id: int, limit: int = Query(100, le=1000)):
    """Hämta prishistorik"""
    conn = get_db()
    cur = conn.cursor()
    
    # Kolla om produkten finns
    cur.execute("SELECT title FROM products WHERE id = ?", (product_id,))
    product = cur.fetchone()
    
    if not product:
        raise HTTPException(status_code=404, detail="Produkt ej hittad")
    
    # Hämta historik
    cur.execute("""
        SELECT price, timestamp
        FROM price_history
        WHERE product_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (product_id, limit))
    
    history = [dict(row) for row in cur.fetchall()]
    
    # Statistik
    cur.execute("""
        SELECT MIN(price) as min_price, MAX(price) as max_price, AVG(price) as avg_price
        FROM price_history WHERE product_id = ?
    """, (product_id,))
    stats = cur.fetchone()
    
    conn.close()
    
    return {
        "product_id": product_id,
        "product_title": product["title"],
        "history": history,
        "statistics": dict(stats) if stats else {}
    }


@app.get("/deals", tags=["Deals"])
def get_deals(
    min_drop_percent: float = Query(5, ge=0),
    min_drop_amount: int = Query(50, ge=0),
    limit: int = Query(50, le=100),
    hours: int = Query(168, ge=1)
):
    """Hämta bästa prisnedsättningar"""
    conn = get_db()
    cur = conn.cursor()
    
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    
    cur.execute("""
        SELECT 
            p.id, p.title, p.url,
            ph1.price AS old_price,
            ph2.price AS new_price,
            ph1.timestamp AS old_date,
            ph2.timestamp AS new_date
        FROM products p
        JOIN price_history ph1 ON p.id = ph1.product_id
        JOIN price_history ph2 ON p.id = ph2.product_id
        WHERE ph1.id < ph2.id
        AND ph2.timestamp = (SELECT MAX(timestamp) FROM price_history WHERE product_id = p.id)
        AND ph1.timestamp = (SELECT MAX(timestamp) FROM price_history 
                            WHERE product_id = p.id AND id < ph2.id)
        AND ph2.price < ph1.price
        AND ph2.timestamp >= ?
    """, (cutoff,))
    
    deals = []
    for row in cur.fetchall():
        drop_amount = row["old_price"] - row["new_price"]
        drop_percent = (drop_amount / row["old_price"]) * 100
        
        if drop_percent >= min_drop_percent and drop_amount >= min_drop_amount:
            deals.append({
                "id": row["id"],
                "title": row["title"],
                "url": row["url"],
                "old_price": row["old_price"],
                "new_price": row["new_price"],
                "drop_amount": drop_amount,
                "drop_percent": round(drop_percent, 1),
                "old_date": row["old_date"],
                "new_date": row["new_date"]
            })
    
    conn.close()
    
    deals.sort(key=lambda x: x["drop_percent"], reverse=True)
    
    return {
        "deals": deals[:limit],
        "count": len(deals[:limit])
    }


@app.get("/stats", tags=["Statistics"])
def get_stats():
    """Hämta statistik"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM price_history")
    total_history = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(DISTINCT product_id) 
        FROM price_history 
        WHERE timestamp >= datetime('now', '-1 day')
    """)
    updated_24h = cur.fetchone()[0]
    
    cur.execute("SELECT AVG(current_price) FROM products")
    avg_price = cur.fetchone()[0]
    
    cur.execute("SELECT MAX(timestamp) FROM price_history")
    last_run = cur.fetchone()[0]
    
    conn.close()
    
    return {
        "total_products": total_products,
        "total_price_records": total_history,
        "updated_24h": updated_24h,
        "average_price": round(avg_price, 2) if avg_price else 0,
        "last_run": last_run,
        "database_size_mb": round(os.path.getsize(DB_FILE) / (1024 * 1024), 2) if os.path.exists(DB_FILE) else 0
    }


@app.get("/export/csv", tags=["Export"])
def export_csv():
    """Exportera produkter som CSV"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, title, url, current_price, first_seen, last_updated
        FROM products ORDER BY last_updated DESC
    """)
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "URL", "Price (SEK)", "First Seen", "Last Updated"])
    
    for row in cur.fetchall():
        writer.writerow([
            row["id"],
            row["title"],
            row["url"],
            row["current_price"],
            row["first_seen"],
            row["last_updated"]
        ])
    
    conn.close()
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=products_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
