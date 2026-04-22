FROM python:3.11-slim

WORKDIR /app

RUN mkdir -p /logs && chmod 777 /logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alerts.py .

CMD ["python", "alerts.py"]
