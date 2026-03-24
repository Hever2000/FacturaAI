import secrets
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class APIKey(BaseModel):
    """API Key model for programmatic access."""

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    scopes: Mapped[list[str]] = mapped_column(
        JSON, default=["jobs:read", "jobs:write"], nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    def has_scope(self, scope: str) -> bool:
        """Check if API key has the given scope."""
        return scope in self.scopes

    def has_any_scope(self, scopes: list[str]) -> bool:
        """Check if API key has any of the given scopes."""
        return any(scope in self.scopes for scope in scopes)

    def __repr__(self) -> str:
        return f"<APIKey {self.name} ({self.key_prefix}...)>"

    @property
    def is_expired(self) -> bool:
        """Check if API key is expired."""
        if self.expires_at is None:
            return False
        return self.expires_at < datetime.now()

    @property
    def is_valid(self) -> bool:
        """Check if API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired

    @classmethod
    def generate_key(cls) -> tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            Tuple of (plain_key, key_hash, key_prefix)
            The plain_key should only be shown once to the user.
        """
        import hashlib

        plain_key = f"fa_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        key_prefix = plain_key[:15]

        return plain_key, key_hash, key_prefix

    def rotate(self) -> str:
        """
        Rotate the API key.

        Returns:
            New plain key (only shown once).
        """
        import hashlib

        plain_key = f"fa_{secrets.token_urlsafe(32)}"
        self.key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        self.key_prefix = plain_key[:15]
        self.last_used_at = None
        self.request_count = 0

        return plain_key


from src.models.user import User  # noqa: E402
