# AGENTS.md - ZenithOCR Developer Guide

AI agent guidance for the ZenithOCR project.

## Project Overview

OCR + LLM invoice processing API for Argentine invoices. Built with FastAPI, PaddleOCR-VL, and Groq (Llama 3.3).

## Project Structure

```
zenith-ocr/
├── src/
│   ├── api/main.py         # FastAPI endpoints
│   ├── core/ocr.py        # OCR & LLM logic
│   ├── models/invoice.py  # Pydantic models
│   └── utils/config.py    # Settings
├── tests/
│   ├── test_api.py        # API tests
│   └── conftest.py        # Pytest fixtures
├── pyproject.toml         # Project config
├── Dockerfile             # Container definition
└── docker-compose.yml    # Local dev environment
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

# Local application
from src.core.ocr import process_ocr, extract_invoice_fields
from src.models.invoice import JobStatus, InvoiceData
```

### Formatting

- Line length: **100 characters max**
- Use 4 spaces (no tabs)
- Use Black for formatting
- One blank line between top-level definitions

### Type Hints

```python
def process_job(job_id: str, data: Dict[str, Any]) -> Optional[InvoiceData]:
    pass

def get_job(job_id: str) -> Dict[str, Any]:
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
    result = ocr_engine.process(file_path)
except Exception as e:
    logger.error(f"OCR failed for job {job_id}: {str(e)}")
    raise

if not job:
    raise HTTPException(status_code=404, detail="Job not found")
```

### Pydantic Models (v2)

```python
from pydantic import BaseModel, Field
from typing import Optional

class InvoiceData(BaseModel):
    invoice_number: str
    vendor_name: str
    tax_id: Optional[str] = None
    confidence_score: float = Field(default=0.0, ge=0, le=1)
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

def process_ocr(job_id: str, file_path: str):
    logger.info(f"Starting OCR for job {job_id}")
    logger.info(f"OCR completed for job {job_id}")
```

## OCR

The API uses **PaddleOCR-VL** remote API for OCR processing.

## Environment Variables

```bash
# Required
GROQ_API_KEY=your_groq_api_key

# PaddleOCR-VL (remote API)
PADDLE_VL_API_URL=https://c6vceb62c4n8zfaf.aistudio-app.com/layout-parsing
PADDLE_VL_TOKEN=your_token

# Optional
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
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
- ✅ Docker build

## Prohibited Actions

- ❌ Direct push to `main`
- ❌ Commit secrets/API keys
- ❌ Disable CI/CD checks
