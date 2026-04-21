FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libxkbcommon0 libgtk-3-0 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium
RUN python -m playwright install-deps

COPY scraper.py .

EXPOSE 5001

CMD ["python", "scraper.py"]
