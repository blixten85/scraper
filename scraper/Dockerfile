FROM python:3.14-slim-bookworm

WORKDIR /app

# Installera ENDAST nödvändiga systemberoenden
RUN apt-get update && apt-get install -y \
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
RUN pip install --no-cache-dir -r requirements.txt

# Installera EXAKT rätt Chromium-version
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install chromium
RUN playwright install-deps chromium

COPY scraper.py .

EXPOSE 5001

CMD ["python", "scraper.py"]
