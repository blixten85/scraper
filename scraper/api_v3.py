#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI-native API för intern kommunikation (ersätter Flask)
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncpg
import redis.asyncio as redis
from prometheus_fastapi_instrumentator import Instrumentator

# === Konfiguration ===
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://scraper:scraper@postgres:5432/scraper')
REDIS_URL = os.getenv('REDIS_URL', 'redis://:changeme@redis:6379/0')
LOG_DIR = "/logs"

os.makedirs(LOG_DIR, exist_ok=True)

# === Loggning ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/api.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === Global state ===
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None
scraping_active = False
stats = {"products": 0, "pages_scraped": 0, "errors": 0}


# === Pydantic Models ===
class ScraperConfig(BaseModel):
    name: str
    base_url: str
    product_selector: str
    title_selector: str
    price_selector: str
    link_selector: str
    pagination_type: str = "query"
    pagination_selector: Optional[str] = None
    max_pages: int = 50
    enabled: bool = True
    min_price: int = 0
    max_price: int = 999999
    exclude_out_of_stock: bool = False
    out_of_stock_selector: Optional[str] = None
    categories: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    active: bool
    database: str
    redis: str
    stats: Dict[str, int]
    timestamp: str


# === Lifespan ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events"""
    global db_pool, redis_client
    
    # Startup
    logger.info("Starting FastAPI...")
    
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    
    redis_client = await redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30
    )
    
    await redis_client.ping()
    
    logger.info("FastAPI ready")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    
    if redis_client:
        await redis_client.close()
    if db_pool:
        await db_pool.close()
    
    logger.info("Shutdown complete")


# === FastAPI App ===
app = FastAPI(
    title="Web Scraper API v3",
    description="Enterprise scraping platform API",
    version="3.0.0",
    lifespan=lifespan
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, include_in_schema=False)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Middleware ===
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Logga alla requests"""
    start = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start).total_seconds()
    
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s")
    
    return response


# === Health Check ===
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Utökad health check med DB och Redis test"""
    db_status = "disconnected"
    redis_status = "disconnected"
    
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                db_status = "connected"
        except:
            pass
    
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "connected"
        except:
            pass
    
    return {
        "status": "healthy" if db_status == "connected" and redis_status == "connected" else "degraded",
        "active": scraping_active,
        "database": db_status,
        "redis": redis_status,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }


# === Config endpoints ===
@app.get("/config")
async def get_configs():
    """Hämta alla konfigurationer"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM scraper_config 
            WHERE enabled = true 
            ORDER BY name
        """)
    
    return [dict(row) for row in rows]


@app.post("/config")
async def create_config(config: ScraperConfig):
    """Skapa ny konfiguration"""
    async with db_pool.acquire() as conn:
        try:
            row = await conn.fetchrow("""
                INSERT INTO scraper_config 
                (name, base_url, product_selector, title_selector, price_selector, 
                 link_selector, pagination_type, pagination_selector, max_pages,
                 enabled, min_price, max_price, exclude_out_of_stock, out_of_stock_selector, categories)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                RETURNING id
            """,
                config.name, config.base_url,
                config.product_selector, config.title_selector,
                config.price_selector, config.link_selector,
                config.pagination_type, config.pagination_selector,
                config.max_pages, config.enabled,
                config.min_price, config.max_price,
                config.exclude_out_of_stock, config.out_of_stock_selector,
                json.dumps(config.categories)
            )
            return {"status": "success", "id": row['id']}
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(status_code=400, detail="Name already exists")


@app.put("/config/{config_id}")
async def update_config(config_id: int, config: ScraperConfig):
    """Uppdatera konfiguration"""
    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE scraper_config SET
                name = $1, base_url = $2,
                product_selector = $3, title_selector = $4,
                price_selector = $5, link_selector = $6,
                pagination_type = $7, pagination_selector = $8,
                max_pages = $9, enabled = $10,
                min_price = $11, max_price = $12,
                exclude_out_of_stock = $13, out_of_stock_selector = $14,
                categories = $15, updated_at = NOW()
            WHERE id = $16
        """,
            config.name, config.base_url,
            config.product_selector, config.title_selector,
            config.price_selector, config.link_selector,
            config.pagination_type, config.pagination_selector,
            config.max_pages, config.enabled,
            config.min_price, config.max_price,
            config.exclude_out_of_stock, config.out_of_stock_selector,
            json.dumps(config.categories),
            config_id
        )
        
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Config not found")
        
        return {"status": "success"}


@app.delete("/config/{config_id}")
async def delete_config(config_id: int):
    """Ta bort/inaktivera konfiguration"""
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE scraper_config SET enabled = false WHERE id = $1",
            config_id
        )
        
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Config not found")
        
        return {"status": "success"}


# === Scraping control ===
@app.post("/scrape")
async def trigger_scrape(background_tasks: BackgroundTasks):
    """Starta manuell scraping (async)"""
    global scraping_active
    
    if scraping_active:
        raise HTTPException(status_code=409, detail="Scraping already running")
    
    scraping_active = True
    background_tasks.add_task(run_scraping_task)
    
    return {"status": "success", "message": "Scraping started"}


async def run_scraping_task():
    """Bakgrundsuppgift för scraping"""
    global scraping_active, stats
    
    try:
        logger.info("Starting manual scraping task...")
        # Här anropas den riktiga scraping-logiken
        await asyncio.sleep(10)  # Simulera arbete
        stats["products"] += 100
        logger.info("Manual scraping completed")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        stats["errors"] += 1
    finally:
        scraping_active = False


@app.get("/stats")
async def get_stats():
    """Hämta scraping-statistik"""
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
