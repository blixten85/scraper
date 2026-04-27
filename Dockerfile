FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    supervisor \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /logs && chmod 777 /logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "\
import pathlib, re; \
p = pathlib.Path('/usr/local/lib/python3.14/site-packages/playwright_stealth/stealth.py'); \
c = p.read_text(); \
c = c.replace('import pkg_resources', 'import importlib.resources'); \
c = re.sub(r\"pkg_resources\\.resource_filename\\('playwright_stealth',\\s*'js'\\)\", \
    \"str(importlib.resources.files('playwright_stealth').joinpath('js'))\", c); \
c = re.sub(r\"pkg_resources\\.resource_string\\('playwright_stealth',\\s*f'js/\\{name\\}'\\)\\.decode\\(\\)\", \
    \"importlib.resources.files('playwright_stealth').joinpath(f'js/{name}').read_text()\", c); \
p.write_text(c)"

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium
RUN playwright install-deps chromium

COPY scraper/scraper.py scraper.py
COPY api/api.py api.py
COPY alerts/alerts.py alerts.py
COPY webui/app.py webui/app.py
COPY webui/templates webui/templates
COPY webui/static webui/static
COPY supervisord.conf supervisord.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 3000 5001 8000

ENTRYPOINT ["/entrypoint.sh"]
