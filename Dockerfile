# Multi-stage lightweight production Dockerfile
FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

COPY instagram_analyzer ./instagram_analyzer
COPY static ./static
COPY compare.py .

EXPOSE 8000

CMD ["python", "-m", "instagram_analyzer", "serve", "--host", "0.0.0.0", "--port", "8000"]
