FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

RUN mkdir -p /logs /tmp/playwright-cache && chmod 777 /logs /tmp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py .

ENV PLAYWRIGHT_BROWSERS_PATH=/tmp/playwright-cache

EXPOSE 5001

CMD ["python", "scraper.py"]
