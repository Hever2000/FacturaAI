import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.v1 import (
    apikeys_router,
    auth_router,
    jobs_router,
    rate_limit_router,
    subscriptions_router,
    webhooks_router,
)
from src.core.config import settings
from src.core.exceptions import register_exception_handlers
from src.db import close_db, init_db
from src.db.redis import _redact_url, close_redis, init_redis, redis_available

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("facturaai")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured JSON logging with request tracking."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else None,
        }

        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={**extra, "event": "request_start"},
        )

        try:
            response = await call_next(request)
            logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                extra={
                    **extra,
                    "event": "request_end",
                    "status_code": response.status_code,
                },
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as e:
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={**extra, "event": "request_error", "error": str(e)},
            )
            raise


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

app.add_middleware(StructuredLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)

app.include_router(apikeys_router, prefix=settings.API_V1_PREFIX)

app.include_router(rate_limit_router, prefix=settings.API_V1_PREFIX)

app.include_router(jobs_router, prefix=settings.API_V1_PREFIX)

app.include_router(subscriptions_router, prefix=settings.API_V1_PREFIX)

app.include_router(webhooks_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", summary="Health check")
async def health_check() -> dict:
    """Health check endpoint with detailed status for DB, Redis, and Workers."""
    from src.db.redis import redis_client

    status = {
        "status": "healthy",
        "service": "factura-ai",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }

    db_status = "unknown"
    try:
        import asyncio

        from src.db.session import engine

        async def check_db():
            try:
                async with engine.connect() as conn:
                    await conn.execute("SELECT 1")
                return "connected"
            except Exception:
                return "disconnected"

        db_status = asyncio.run(check_db())
    except Exception:
        db_status = "disconnected"

    status["database"] = db_status

    if redis_available and redis_client:
        try:
            import asyncio
            asyncio.run(redis_client.ping())
            redis_status = "connected"
        except Exception:
            redis_status = "disconnected"
    else:
        redis_status = "disconnected" if settings.REDIS_URL else "not_configured"

    status["redis"] = redis_status

    worker_status = "unknown"
    if settings.REDIS_URL:
        try:
            from src.core.celery_app import celery_app
            inspect = celery_app.control.inspect(timeout=1.0)
            workers = inspect.active()
            worker_status = f"running ({len(workers)} workers)" if workers else "no_active_workers"
        except Exception:
            worker_status = "unavailable"
    else:
        worker_status = "not_configured"

    status["workers"] = worker_status

    if db_status != "connected" or redis_status == "disconnected":
        status["status"] = "degraded"

    if db_status == "disconnected":
        status["status"] = "unhealthy"

    status_codes = {"healthy": 200, "degraded": 200, "unhealthy": 503}
    status_code = status_codes.get(status["status"], 200)

    if status_code != 200:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=status, status_code=status_code)

    return status


@app.get("/health/live", summary="Liveness check")
async def liveness_check() -> dict:
    """Simple liveness check - returns OK if service is running."""
    return {"status": "ok"}


@app.get("/health/ready", summary="Readiness check")
async def readiness_check() -> dict:
    """Readiness check - returns OK if service can handle requests."""

    if not redis_available:
        return {"status": "not_ready", "reason": "redis_unavailable"}

    return {"status": "ready"}
