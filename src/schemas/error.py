from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detailed error information for debugging."""

    field: str | None = None
    message: str
    type: str | None = None


class ErrorResponse(BaseModel):
    """Standardized error response format."""

    error: dict[str, Any] = Field(
        ...,
        description="Error container with code, message and details"
    )

    @classmethod
    def from_exception(
        cls,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        status_code: int = 500,
    ) -> dict[str, Any]:
        """Create error response from exception details."""
        error_obj = {
            "code": code,
            "message": message,
        }
        if details:
            error_obj["details"] = details
        return {"error": error_obj}


class ValidationErrorResponse(ErrorResponse):
    """Validation error response with field-level details."""

    @classmethod
    def from_validation_errors(
        cls, errors: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Create validation error response from Pydantic errors."""
        details = []
        for err in errors:
            loc = ".".join(str(loc_item) for loc_item in err.get("loc", []))
            details.append(
                ErrorDetail(
                    field=loc if loc else None,
                    message=err.get("msg", "Validation error"),
                    type=err.get("type"),
                ).model_dump()
            )
        return cls.from_exception(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"fields": details},
            status_code=422,
        )


class RateLimitErrorResponse(ErrorResponse):
    """Rate limit exceeded error response."""

    @classmethod
    def from_rate_limit(
        cls,
        current: int,
        limit: int,
        reset_in: int,
    ) -> dict[str, Any]:
        """Create rate limit error response."""
        return cls.from_exception(
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. {current}/{limit} requests per minute.",
            details={
                "limit": limit,
                "remaining": 0,
                "reset_in_seconds": reset_in,
            },
            status_code=429,
        )


class AuthErrorResponse(ErrorResponse):
    """Authentication error response."""

    @classmethod
    def invalid_credentials(cls) -> dict[str, Any]:
        return cls.from_exception(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password",
            status_code=401,
        )

    @classmethod
    def token_expired(cls) -> dict[str, Any]:
        return cls.from_exception(
            code="TOKEN_EXPIRED",
            message="Authentication token has expired",
            status_code=401,
        )

    @classmethod
    def token_invalid(cls) -> dict[str, Any]:
        return cls.from_exception(
            code="TOKEN_INVALID",
            message="Invalid authentication token",
            status_code=401,
        )

    @classmethod
    def insufficient_permissions(cls) -> dict[str, Any]:
        return cls.from_exception(
            code="INSUFFICIENT_PERMISSIONS",
            message="Insufficient permissions to perform this action",
            status_code=403,
        )


class NotFoundErrorResponse(ErrorResponse):
    """Resource not found error response."""

    @classmethod
    def resource_not_found(cls, resource: str, identifier: str) -> dict[str, Any]:
        return cls.from_exception(
            code="RESOURCE_NOT_FOUND",
            message=f"{resource} not found",
            details={"resource": resource, "identifier": str(identifier)},
            status_code=404,
        )


class ConflictErrorResponse(ErrorResponse):
    """Conflict error response."""

    @classmethod
    def duplicate_resource(cls, resource: str, field: str) -> dict[str, Any]:
        return cls.from_exception(
            code="DUPLICATE_RESOURCE",
            message=f"{resource} already exists",
            details={"resource": resource, "field": field},
            status_code=409,
        )
