# AGENTS.md - Guía de Desarrollo de FacturaAI

Guía para agentes IA del proyecto FacturaAI.

## Project Overview

OCR + LLM invoice processing API for Argentine invoices. Built with FastAPI, PaddleOCR-VL/EasyOCR, Groq (Llama 3.3), PostgreSQL, and Redis.

## Tech Stack

- **Framework**: FastAPI (Python 3.11+)
- **OCR**: PaddleOCR-VL (remote) / EasyOCR (fallback)
- **LLM**: Groq (Llama 3.3)
- **Database**: PostgreSQL + SQLAlchemy (async)
- **Cache**: Redis
- **Auth**: JWT (python-jose)
- **Payments**: Mercado Pago

## Project Structure

```
facturaai/
├── src/
│   ├── api/
│   │   ├── main.py            # FastAPI app initialization
│   │   ├── deps.py            # Dependencies (auth, db, redis)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth.py        # /v1/auth/* - Register, login, refresh, me
│   │       ├── apikeys.py     # /v1/apikeys/* - API keys management
│   │       ├── jobs.py        # /v1/jobs/* - Invoice processing
│   │       ├── subscriptions.py # /v1/subscriptions/* - Plans, subscribe
│   │       ├── webhooks.py    # /v1/webhooks/mercadopago
│   │       └── rate_limit.py  # /v1/rate-limit/status
│   ├── core/
│   │   ├── config.py          # Settings (pydantic-settings)
│   │   ├── ocr.py             # OCR processing logic
│   │   ├── security.py        # JWT create/verify utilities
│   │   ├── feedback.py        # User feedback system
│   │   └── celery_app.py      # Celery configuration
│   ├── models/
│   │   ├── base.py            # Base model class
│   │   ├── user.py            # User SQLAlchemy model
│   │   ├── job.py             # Job SQLAlchemy model
│   │   ├── apikey.py          # API key SQLAlchemy model
│   │   ├── invoice.py         # Invoice Pydantic model
│   │   └── feedback.py        # Feedback SQLAlchemy model
│   ├── schemas/
│   │   ├── auth.py            # Token, LoginRequest, UserResponse
│   │   ├── apikey.py          # APIKeyResponse, APIKeyCreate
│   │   ├── subscription.py    # SubscriptionPlan, SubscriptionResponse
│   │   └── job.py              # JobResponse, JobCreate
│   ├── services/
│   │   ├── auth.py            # AuthService (create tokens, authenticate)
│   │   ├── apikey.py          # APIKeyService (create, rotate, validate)
│   │   ├── subscription.py    # SubscriptionService (MP integration)
│   │   ├── mercadopago.py     # Mercado Pago client
│   │   └── mercadopopago.py   # Legacy MP client
│   └── db/
│       ├── session.py         # AsyncSession, get_db
│       └── redis.py           # Redis client, cache utilities
├── tests/
│   ├── conftest.py            # Pytest fixtures (db, auth, client)
│   └── test_api.py            # API endpoint tests
├── .github/workflows/          # CI/CD pipelines
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Build/Lint/Test Commands

### Running the API

```bash
# Install dependencies
pip install -e .

# Run development server
uvicorn src.api.main:app --reload --port 8000

# Docker
docker-compose up --build
```

### Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_api.py

# Run single test
pytest tests/test_api.py::test_job_status

# Run tests matching pattern
pytest -k "test_job"

# With coverage
pytest --cov=src --cov-report=html
```

### Linting & Formatting

```bash
# Install linting tools
pip install ruff black isort mypy

# Auto-fix with ruff
ruff check --fix .

# Format code
black --line-length=100 .
isort --profile=black .

# Type checking
mypy src/ --ignore-missing-imports
```

## Code Style Guidelines

### General Principles

- Write clean, readable, maintainable code
- Follow DRY (Don't Repeat Yourself)
- Use meaningful variable/function names
- Keep functions small and focused
- Add type hints to all signatures

### Imports (use isort)

```python
# Standard library
import os
import logging
from typing import Dict, Any, Optional
from uuid import uuid4

# Third-party
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from src.api.deps import CurrentUser, DBSession
from src.services.auth import AuthService
from src.models.user import User
```

### Formatting

- Line length: **100 characters max**
- Use 4 spaces (no tabs)
- Use Black for formatting
- One blank line between top-level definitions

### Type Hints

```python
async def get_job(job_id: str, db: DBSession) -> Job | None:
    pass

async def create_api_key(user_id: str, name: str) -> APIKeyWithSecret:
    pass
```

### Naming Conventions

- **Variables/Functions**: `snake_case` (e.g., `job_id`, `process_ocr`)
- **Classes**: `PascalCase` (e.g., `InvoiceData`, `JobStatus`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_FILE_SIZE`)
- **Private members**: Prefix with underscore (`_internal_method`)

### Error Handling

```python
try:
    result = await ocr_engine.process(file_path)
except Exception as e:
    logger.error(f"OCR failed for job {job_id}: {str(e)}")
    raise HTTPException(status_code=500, detail="OCR processing failed")

if not job:
    raise HTTPException(status_code=404, detail="Job not found")
```

### Pydantic Models (v2)

```python
from pydantic import BaseModel, Field
from typing import Optional

class InvoiceData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice_number: str
    vendor_name: str
    tax_id: Optional[str] = None
    confidence_score: float = Field(default=0.0, ge=0, le=1)
```

### SQLAlchemy Models

```python
from sqlalchemy import Column, String, Integer
from src.models.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

async def process_job(job_id: str):
    logger.info(f"Starting OCR for job {job_id}")
    try:
        result = await process_ocr(job_id)
        logger.info(f"OCR completed for job {job_id}")
    except Exception as e:
        logger.error(f"OCR failed for job {job_id}: {e}")
        raise
```

## Authentication

- JWT with access token (15 min default) and refresh token (7 days default)
- Tokens created in `src/core/security.py`
- Auth service in `src/services/auth.py`
- API key authentication supported via `X-API-Key` header

## Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

# Redis
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your-secret-key-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# Groq
GROQ_API_KEY=your_groq_api_key

# PaddleOCR-VL (remote API)
PADDLE_VL_API_URL=https://c6vceb62c4n8zfaf.aistudio-app.com/layout-parsing
PADDLE_VL_TOKEN=your_token

# Mercado Pago
MP_ACCESS_TOKEN=your_mp_access_token
MP_WEBHOOK_SECRET=your_webhook_secret

# Optional
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
ENVIRONMENT=development
```

## Git Workflow & Branch Protection

### Branch Strategy

- **main**: Production code (protected)
- **feature/***: New features
- **fix/***: Bug fixes

### Protection Rules

- **Direct pushes to main are FORBIDDEN**
- All changes must go through Pull Requests
- CI/CD checks must pass before merge

### How to Contribute

```bash
git checkout -b feature/my-new-feature
git add .
git commit -m "feat: description of changes"
git push -u origin feature/my-new-feature
```

### CI/CD Requirements

Before merging, all checks must pass:
- ✅ Tests (pytest)
- ✅ Linting (ruff, black, isort)
- ✅ Type checking (mypy)
- ✅ Docker build

## Prohibited Actions

- ❌ Direct push to `main`
- ❌ Commit secrets/API keys
- ❌ Disable CI/CD checks
- ❌ Use wildcard CORS origins in production

## CORS

CORS origins are configured in `src/core/config.py` under `CORS_ORIGINS`. Default includes:
- `http://localhost:3000`
- `http://localhost:5173`
- `https://facturaai.com`
- Vercel preview/production domains
