#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Redis Streams worker med consumer groups och ack
"""

import os
import json
import asyncio
import logging
import signal
from datetime import datetime
from typing import Optional

import asyncpg
import redis.asyncio as redis

# === Konfiguration ===
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://scraper:scraper@postgres:5432/scraper')
REDIS_URL = os.getenv('REDIS_URL', 'redis://:changeme@redis:6379/0')
CONSUMER_GROUP = os.getenv('CONSUMER_GROUP', 'scraper_workers')
CONSUMER_NAME = os.getenv('CONSUMER_NAME', f'worker-{os.getpid()}')
STREAM_NAME = "scraper_stream"
LOG_DIR = "/logs"

os.makedirs(LOG_DIR, exist_ok=True)

# === Loggning ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/worker.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === Global state ===
shutdown_event = asyncio.Event()
db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[redis.Redis] = None
stats = {"processed": 0, "inserted": 0, "updated": 0, "errors": 0, "retries": 0}


async def init_connections():
    """Initiera anslutningar"""
    global db_pool, redis_client
    
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30
    )
    
    redis_client = await redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30
    )
    
    await redis_client.ping()
    
    # Skapa consumer group
    try:
        await redis_client.xgroup_create(
            STREAM_NAME,
            CONSUMER_GROUP,
            id='0',
            mkstream=True
        )
        logger.info(f"Created consumer group: {CONSUMER_GROUP}")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group {CONSUMER_GROUP} already exists")
        else:
            raise
    
    logger.info(f"Worker {CONSUMER_NAME} initialized")


async def process_product(product_data: dict) -> bool:
    """Processa en produkt - returnerar True vid success"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow("""
                        INSERT INTO products (url, title, current_price, site_config_id, last_updated)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT (url) DO UPDATE SET
                            current_price = EXCLUDED.current_price,
                            title = EXCLUDED.title,
                            last_updated = NOW()
                        RETURNING id, (xmax = 0) AS is_new
                    """,
                        product_data['url'],
                        product_data['title'],
                        product_data['price'],
                        product_data.get('site_config_id')
                    )
                    
                    product_id = row['id']
                    is_new = row['is_new']
                    
                    await conn.execute("""
                        INSERT INTO price_history (product_id, price, timestamp)
                        VALUES ($1, $2, NOW())
                    """, product_id, product_data['price'])
                    
                    if is_new:
                        stats['inserted'] += 1
                    else:
                        stats['updated'] += 1
                    
                    stats['processed'] += 1
                    return True
                    
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {product_data.get('url')}: {e}")
                stats['retries'] += 1
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Failed after {max_retries} attempts: {product_data.get('url')} - {e}")
                stats['errors'] += 1
                return False
    
    return False


async def worker_loop():
    """Huvudloop med Redis Streams"""
    logger.info(f"Worker {CONSUMER_NAME} started, listening on {STREAM_NAME}")
    
    last_cleanup = datetime.now()
    batch_size = 10
    
    while not shutdown_event.is_set():
        try:
            # Läs meddelanden från stream
            messages = await redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={STREAM_NAME: '>'},
                count=batch_size,
                block=5000  # 5 sekunder timeout
            )
            
            if messages:
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        try:
                            product = json.loads(data['product'])
                            
                            success = await process_product(product)
                            
                            if success:
                                # Ack:a meddelandet
                                await redis_client.xack(
                                    STREAM_NAME,
                                    CONSUMER_GROUP,
                                    message_id
                                )
                            else:
                                # Lämna för retry (kommer plockas upp av pending processing)
                                logger.warning(f"Message {message_id} failed, will be retried")
                            
                            if stats['processed'] % 100 == 0:
                                logger.info(
                                    f"Processed: {stats['processed']} "
                                    f"(new: {stats['inserted']}, updated: {stats['updated']}, "
                                    f"errors: {stats['errors']}, retries: {stats['retries']})"
                                )
                                
                        except Exception as e:
                            logger.error(f"Error processing message {message_id}: {e}")
                            stats['errors'] += 1
            
            # Hantera pending messages (omstartade workers)
            await process_pending_messages()
            
            # Daglig cleanup
            now = datetime.now()
            if (now - last_cleanup).days >= 1:
                await cleanup_old_history()
                last_cleanup = now
                
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.error(f"Worker loop error: {e}", exc_info=True)
            await asyncio.sleep(1)
    
    logger.info(f"Worker {CONSUMER_NAME} shutting down. Final stats: {stats}")


async def process_pending_messages():
    """Processa pending messages (från crashed workers)"""
    try:
        pending = await redis_client.xpending(
            STREAM_NAME,
            CONSUMER_GROUP
        )
        
        if pending and pending['pending'] > 0:
            # Hämta pending messages
            messages = await redis_client.xpending_range(
                STREAM_NAME,
                CONSUMER_GROUP,
                min='-',
                max='+',
                count=10
            )
            
            for msg in messages:
                # Claim om de är äldre än 60 sekunder
                if msg['time_since_delivered'] > 60000:
                    claimed = await redis_client.xclaim(
                        STREAM_NAME,
                        CONSUMER_GROUP,
                        CONSUMER_NAME,
                        min_idle_time=60000,
                        message_ids=[msg['message_id']]
                    )
                    
                    if claimed:
                        logger.info(f"Claimed pending message: {msg['message_id']}")
    except Exception as e:
        logger.error(f"Error processing pending messages: {e}")


async def cleanup_old_history(days: int = 30):
    """Rensa gammal prishistorik"""
    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM price_history
            WHERE timestamp < NOW() - INTERVAL '1 day' * $1
        """, days)
        
        deleted = int(result.split()[-1]) if result else 0
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old price records")


async def shutdown():
    """Graceful shutdown"""
    logger.info("Shutting down worker...")
    
    if redis_client:
        await redis_client.close()
    if db_pool:
        await db_pool.close()
    
    logger.info("Shutdown complete")


def signal_handler():
    shutdown_event.set()


async def main():
    await init_connections()
    
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        await worker_loop()
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())
