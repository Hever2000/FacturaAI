import logging
import traceback
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.schemas.error import ErrorResponse, ValidationErrorResponse

logger = logging.getLogger("facturaai")


class AppException(Exception):
    """Base application exception with standardized error format."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 500,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        error = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"error": error}


class AuthenticationError(AppException):
    """Authentication related errors."""

    def __init__(
        self,
        message: str = "Authentication failed",
        code: str = "AUTHENTICATION_ERROR",
        **kwargs,
    ):
        super().__init__(code=code, message=message, status_code=401, **kwargs)


class InvalidCredentialsError(AuthenticationError):
    def __init__(self):
        super().__init__(
            message="Invalid email or password",
            code="INVALID_CREDENTIALS",
        )


class TokenExpiredError(AuthenticationError):
    def __init__(self):
        super().__init__(
            message="Authentication token has expired",
            code="TOKEN_EXPIRED",
        )


class TokenInvalidError(AuthenticationError):
    def __init__(self):
        super().__init__(
            message="Invalid authentication token",
            code="TOKEN_INVALID",
        )


class InsufficientPermissionsError(AuthenticationError):
    def __init__(self, required_scope: str | None = None):
        message = "Insufficient permissions to perform this action"
        if required_scope:
            message = f"Required scope: {required_scope}"
        super().__init__(
            message=message,
            code="INSUFFICIENT_PERMISSIONS",
            status_code=403,
        )


class NotFoundError(AppException):
    """Resource not found error."""

    def __init__(self, resource: str, identifier: str | None = None):
        message = f"{resource} not found"
        details = {"resource": resource}
        if identifier:
            details["identifier"] = str(identifier)
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=message,
            details=details,
            status_code=404,
        )


class ConflictError(AppException):
    """Resource conflict error."""

    def __init__(self, message: str, code: str = "CONFLICT", **kwargs):
        super().__init__(code=code, message=message, status_code=409, **kwargs)


class DuplicateResourceError(ConflictError):
    def __init__(self, resource: str, field: str):
        super().__init__(
            message=f"{resource} already exists",
            code="DUPLICATE_RESOURCE",
            details={"resource": resource, "field": field},
        )


class ValidationError_(AppException):
    """Validation error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            details=details,
            status_code=422,
        )


class RateLimitError(AppException):
    """Rate limit exceeded error."""

    def __init__(self, current: int, limit: int, reset_in: int):
        super().__init__(
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. {current}/{limit} requests per minute.",
            details={
                "limit": limit,
                "remaining": 0,
                "reset_in_seconds": reset_in,
            },
            status_code=429,
        )


class QuotaExceededError(AppException):
    """Monthly quota exceeded error."""

    def __init__(self, current: int, limit: int):
        super().__init__(
            code="QUOTA_EXCEEDED",
            message="Monthly quota exceeded. Upgrade your plan to continue.",
            details={
                "current_usage": current,
                "monthly_limit": limit,
                "upgrade_url": "/v1/subscriptions",
            },
            status_code=429,
        )


class ExternalServiceError(AppException):
    """External service (OCR, LLM, Payment) error."""

    def __init__(self, service: str, message: str):
        super().__init__(
            code="EXTERNAL_SERVICE_ERROR",
            message=f"{service} error: {message}",
            details={"service": service},
            status_code=502,
        )


async def validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    errors = exc.errors()
    logger.warning(f"Validation error on {request.url.path}: {errors}")
    return JSONResponse(
        status_code=422,
        content=ValidationErrorResponse.from_validation_errors(errors),
    )


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Handle SQLAlchemy database errors."""
    logger.error(f"Database error on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse.from_exception(
            code="DATABASE_ERROR",
            message="An internal database error occurred",
            status_code=500,
        ),
    )


async def app_exception_handler(
    request: Request, exc: AppException
) -> JSONResponse:
    """Handle application exceptions."""
    request_id = request.state.__dict__.get("request_id", str(uuid.uuid4()))
    logger.warning(
        f"App exception [{request_id}]: {exc.code} - {exc.message}",
        extra={"request_id": request_id, "details": exc.details},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    request_id = request.state.__dict__.get("request_id", str(uuid.uuid4()))
    logger.error(
        f"Unexpected error [{request_id}]: {type(exc).__name__}: {str(exc)}\n"
        f"Traceback: {traceback.format_exc()}",
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content=ErrorResponse.from_exception(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred",
            status_code=500,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app."""
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
