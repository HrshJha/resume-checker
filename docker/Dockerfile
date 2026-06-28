# ============================================================
# Candidate Intelligence System — Production Dockerfile
# ============================================================
FROM python:3.11-slim AS base

# System dependencies for PDF parsing, OCR, file validation, and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download ML models at build time (baked into image)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
RUN python -m spacy download en_core_web_sm

# Copy application code
COPY src/ ./src/
COPY configs/ ./configs/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create data directories
RUN mkdir -p data/raw/resumes data/raw/job_descriptions data/processed \
    data/embeddings data/labels data/uploads \
    models/ranker models/embeddings models/authenticity \
    models/cross_encoder models/registry logs

# Copy pre-built models if available
COPY models/ ./models/

EXPOSE 8000

# M-5: Use curl for health checks — lighter and doesn't require Python runtime startup.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || exit 1

# Run with uvicorn (4 workers for production)
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

