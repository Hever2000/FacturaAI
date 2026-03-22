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
    libpq-dev \
    gcc \
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

# Install only runtime system deps
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

# Copy source + config (not test files)
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create storage dir
RUN mkdir -p /app/storage

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# CMD set via docker-compose
