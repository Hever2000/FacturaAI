"""Initial migration

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("subscription_tier", sa.String(50), nullable=False, server_default="free"),
        sa.Column("subscription_external_id", sa.String(255), nullable=True),
        sa.Column("subscription_status", sa.String(50), nullable=True),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("monthly_request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "monthly_reset_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)

    # Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=True)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"], unique=False)

    # Create jobs table
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("filename", sa.String(500), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("ocr_engine", sa.String(50), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("extracted_data", postgresql.JSON(), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_id", "jobs", ["id"], unique=False)
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"], unique=False)

    # Create feedbacks table
    op.create_table(
        "feedbacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("original_value", postgresql.JSON(), nullable=True),
        sa.Column("corrected_value", postgresql.JSON(), nullable=False),
        sa.Column("raw_text_snippet", sa.Text(), nullable=True),
        sa.Column("ai_response_snapshot", postgresql.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedbacks_id", "feedbacks", ["id"], unique=False)
    op.create_index("ix_feedbacks_job_id", "feedbacks", ["job_id"], unique=False)
    op.create_index("ix_feedbacks_user_id", "feedbacks", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("feedbacks")
    op.drop_table("jobs")
    op.drop_table("api_keys")
    op.drop_table("users")
