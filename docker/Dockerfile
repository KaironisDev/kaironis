FROM python:3.11-slim

WORKDIR /app

# System dependencies
# - gcc: required for compiling some Python packages
# - poppler-utils: required by pdf2image for PDF → image conversion (ingest_images.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    poppler-utils \
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
