FROM python:3.11-slim

WORKDIR /app

# Systeem dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Broncode
COPY src/ ./src/

# Logs map
RUN mkdir -p /app/logs

# Non-root user voor security
RUN useradd -m -u 1000 kaironis && chown -R kaironis:kaironis /app
USER kaironis

CMD ["python", "-m", "src.orchestration.bot"]
