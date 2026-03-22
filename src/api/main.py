import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1 import (
    apikeys_router,
    auth_router,
    jobs_router,
    rate_limit_router,
    subscriptions_router,
    webhooks_router,
)
from src.core.config import settings
from src.db import close_db, init_db
from src.db.redis import close_redis, init_redis

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("factura_ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown."""
    await init_db()
    await init_redis()
    settings.ensure_directories()
    yield
    await close_redis()
    await close_db()


app = FastAPI(
    title="FacturaAI API",
    description="OCR + LLM invoice processing API for Argentine invoices",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth & user management
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)

# API keys
app.include_router(apikeys_router, prefix=settings.API_V1_PREFIX)

# Rate limiting
app.include_router(rate_limit_router, prefix=settings.API_V1_PREFIX)

# Invoice processing & jobs (DB-backed, auth required)
app.include_router(jobs_router, prefix=settings.API_V1_PREFIX)

# Subscriptions
app.include_router(subscriptions_router, prefix=settings.API_V1_PREFIX)

# Mercado Pago webhooks
app.include_router(webhooks_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", summary="Health check")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "factura-ai"}
