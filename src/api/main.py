import logging
from collections.abc import AsyncIterator
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
from src.db.redis import close_redis, init_redis, redis_available

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("factura_ai")


def _redact_url(url: str) -> str:
    """Redact credentials from a URL for safe logging."""
    import re

    # Remove user:password@ or user@ patterns
    redacted = re.sub(r"://[^@]+@", "://***@", url)
    # If no @ found, still try to remove leading protocol+creds
    if "@" not in redacted:
        redacted = re.sub(r"://[^/]+", "://***", url)
    return redacted


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan events for startup and shutdown."""
    logger.info("Starting FacturaAI API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database: {_redact_url(settings.DATABASE_URL)}")
    logger.info(f"Redis: {_redact_url(settings.REDIS_URL)}")
    try:
        logger.info("Initializing database connection...")
        await init_db()
        logger.info("Database connection established.")
        logger.info("Initializing Redis connection...")
        redis_ok = await init_redis()
        if redis_ok:
            logger.info("Redis connection established.")
        else:
            logger.info("Redis disabled or unavailable. Running in no-cache mode.")
        logger.info("Ensuring storage directories exist...")
        settings.ensure_directories()
        logger.info("FacturaAI API started successfully.")
    except Exception as e:
        logger.error(f"Startup failed: {e}", exc_info=True)
        raise
    try:
        yield
    finally:
        logger.info("Shutting down FacturaAI API...")
        try:
            await close_redis()
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")
        try:
            await close_db()
        except Exception as e:
            logger.error(f"Error closing database: {e}")
        logger.info("FacturaAI API shut down.")


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
    return {
        "status": "healthy",
        "service": "factura-ai",
        "redis": "connected" if redis_available else "disconnected"
    }
