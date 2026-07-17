FROM python:3.11-slim

# System deps for aiohttp
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENV PORT=5000

EXPOSE 5000

CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --timeout 150 \
    --worker-class sync \
    --access-logfile - \
    --error-logfile -
