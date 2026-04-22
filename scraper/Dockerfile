FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

RUN mkdir -p /logs && chmod 777 /logs

# Installera Chromium
RUN python -m playwright install chromium

# VIKTIGT: Symlink så Playwright hittar cachen
RUN ln -sf /ms-playwright /root/.cache/ms-playwright 2>/dev/null || true

COPY requirements.txt .
RUN pip install --no-cache-dir flask==3.0.0 flask-cors==4.0.0 psycopg2-binary==2.9.9

COPY scraper.py .

EXPOSE 5001

CMD ["python", "scraper.py"]
