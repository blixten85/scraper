FROM python:3.11-slim

# Installera systemberoenden FÖRST (innan Playwright)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    libnss3 \
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
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-dri3-0 \
    libxcb-shm0 \
    libxcb-present0 \
    libxcb-sync1 \
    libxcb-xfixes0 \
    libxshmfence1 \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopiera och installera Python-beroenden
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installera Playwright OCH dess beroenden
RUN python -m playwright install chromium
RUN python -m playwright install-deps chromium || true

COPY scraper.py .
COPY worker_v3.py .
COPY api_v3.py .

# Exponera port för interna API:et
EXPOSE 5001

CMD ["python", "scraper.py"]
