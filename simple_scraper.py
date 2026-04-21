#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Generic Web Scraper
Just change the CONFIG section below and run!
"""

import asyncio
import re
from playwright.async_api import async_playwright

# ============================================================
# CONFIGURATION - JUST CHANGE THESE VALUES!
# ============================================================

CONFIG = {
    # The website URL you want to scrape
    "url": "https://www.inet.se/kategori/datorkomponenter",
    
    # CSS selector for each product container
    "product_selector": "a[href*='/produkt/']",
    
    # CSS selector for the title (relative to product_selector)
    # Use "" to use the element's own text
    "title_selector": "",
    
    # CSS selector for the price (relative to product_selector)
    # Can be a CSS selector or a regex pattern: "text=/\\d[\\d\\s]*\\s*kr/"
    "price_selector": "text=/\\d[\\d\\s]*\\s*kr/",
    
    # CSS selector for the link (relative to product_selector)
    "link_selector": "",
    
    # Maximum number of products to scrape (set to 0 for unlimited)
    "max_products": 50,
    
    # Output file name
    "output_file": "products.txt",
    
    # Wait time between scrolls (seconds) for lazy-loading sites
    "scroll_wait": 0.5,
    
    # Number of scrolls to load more content (0 = no scrolling)
    "scroll_count": 3
}

# ============================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE!
# ============================================================

async def scrape():
    products = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page()
        
        print(f"🌐 Loading: {CONFIG['url']}")
        await page.goto(CONFIG['url'], timeout=60000)
        await page.wait_for_load_state("domcontentloaded")
        
        # Scroll to load lazy content
        for i in range(CONFIG['scroll_count']):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(CONFIG['scroll_wait'])
            print(f"   📜 Scroll {i+1}/{CONFIG['scroll_count']}")
        
        # Find all product elements
        elements = await page.query_selector_all(CONFIG['product_selector'])
        print(f"🔍 Found {len(elements)} potential products")
        
        count = 0
        for elem in elements:
            if CONFIG['max_products'] > 0 and count >= CONFIG['max_products']:
                break
                
            try:
                # Extract title
                if CONFIG['title_selector']:
                    title_el = await elem.query_selector(CONFIG['title_selector'])
                    title = (await title_el.inner_text()).strip() if title_el else ""
                else:
                    title = (await elem.inner_text()).strip()
                
                # Extract link
                if CONFIG['link_selector']:
                    link_el = await elem.query_selector(CONFIG['link_selector'])
                    link = await link_el.get_attribute("href") if link_el else None
                else:
                    link = await elem.get_attribute("href")
                
                # Make full URL
                if link and link.startswith('/'):
                    from urllib.parse import urljoin
                    link = urljoin(CONFIG['url'], link)
                
                # Extract price
                price_text = ""
                if CONFIG['price_selector'].startswith('text=/'):
                    # Regex mode - search in parent text
                    parent_text = await elem.evaluate("el => el.closest('article, div[class*=\"product\"]')?.innerText || ''")
                    pattern = CONFIG['price_selector'][6:-1]
                    match = re.search(pattern, parent_text)
                    price_text = match.group(0) if match else ""
                else:
                    price_el = await elem.query_selector(CONFIG['price_selector'])
                    price_text = (await price_el.inner_text()).strip() if price_el else ""
                
                # Clean price
                price = re.sub(r'[^\d]', '', price_text) if price_text else ""
                
                if title and price and link:
                    products.append({
                        'title': title,
                        'price': int(price) if price else 0,
                        'link': link
                    })
                    count += 1
                    print(f"   ✅ [{count}] {title[:50]}... - {price} kr")
                    
            except Exception as e:
                continue
        
        await browser.close()
    
    # Save to file
    with open(CONFIG['output_file'], 'w', encoding='utf-8') as f:
        f.write(f"Scraped from: {CONFIG['url']}\n")
        f.write(f"Date: {asyncio.get_event_loop().time()}\n")
        f.write("=" * 80 + "\n\n")
        f.write("Product\t\tPrice\t\tLink\n")
        f.write("-" * 80 + "\n")
        
        for p in products:
            f.write(f"{p['title'][:40]}\t{p['price']} kr\t{p['link']}\n")
    
    print(f"\n✅ Saved {len(products)} products to {CONFIG['output_file']}")
    return products

if __name__ == "__main__":
    print("=" * 60)
    print("🕷️  SIMPLE WEB SCRAPER")
    print("=" * 60)
    asyncio.run(scrape())
