# syntax=docker/dockerfile:1
# =============================================================================
# Stage 1: Builder — install all dependencies
# =============================================================================
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Install system deps needed for Python packages + OCR libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# =============================================================================
# Stage 2: Development — with test deps + hot reload
# =============================================================================
FROM builder AS dev

# Install dev/test dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    httpx \
    aiosqlite \
    ruff \
    black \
    isort \
    mypy

# Copy full project
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY pyproject.toml ./
COPY pytest.ini ./

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV UVICORN_RELOAD="1"

WORKDIR /app
EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# Stage 3: Production — minimal, no dev/test deps
# =============================================================================
FROM python:3.12-slim-bookworm AS prod

# Install ONLY runtime system deps (no gcc, no dev libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Set working directory BEFORE copying source files
WORKDIR /app

# Runtime environment (must be before COPY so it persists)
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Copy source + config (now correctly placed under /app)
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY pyproject.toml ./

# Create storage dir
RUN mkdir -p /app/storage

EXPOSE 8080

# Health check for Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Startup script: run migrations, then start server
# Uses $PORT if provided (Render), defaults to 8080 (Docker)
CMD ["/bin/sh", "-c", "echo 'Running database migrations...' && alembic upgrade head && echo 'Starting API server...' && exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
