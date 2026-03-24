"""
Storage service for files.

Supports:
- Local storage (development)
- Cloudflare R2 (production) with pre-signed URLs

Usage:
    # Get pre-signed upload URL (for direct frontend upload)
    upload_url, file_key = await storage_service.get_upload_url(
        content_type="image/png",
        filename="invoice.png"
    )

    # Get public URL for downloaded file
    public_url = storage_service.get_public_url(file_key)

    # Delete file
    await storage_service.delete_file(file_key)
"""

import logging
import os
import uuid
from enum import Enum

import boto3
from botocore.config import Config as BotoConfig

from src.core.config import settings

logger = logging.getLogger(__name__)


class StorageBackend(str, Enum):
    """Storage backend types."""

    LOCAL = "local"
    R2 = "r2"


class StorageService:
    """
    Storage service abstraction.

    In development: stores files locally in STORAGE_PATH
    In production: uses Cloudflare R2 with pre-signed URLs
    """

    def __init__(self) -> None:
        self.backend = StorageBackend(settings.STORAGE_BACKEND)
        self._s3_client = None

        if self.backend == StorageBackend.LOCAL:
            os.makedirs(settings.STORAGE_PATH, exist_ok=True)
            logger.info(f"Storage: using local backend at {settings.STORAGE_PATH}")
        elif self.backend == StorageBackend.R2:
            logger.info(
                f"Storage: using R2 backend at {settings.R2_ENDPOINT}"
            )

    @property
    def s3_client(self):
        """Lazy initialization of S3 client for R2."""
        if self._s3_client is None:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=settings.R2_ENDPOINT,
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
                config=BotoConfig(signature_version="s3v4"),
            )
        return self._s3_client

    def _generate_file_key(self, filename: str) -> str:
        """Generate a unique file key for storage."""
        ext = os.path.splitext(filename)[1] or ".bin"
        return f"invoices/{uuid.uuid4()}{ext}"

    async def get_upload_url(
        self,
        content_type: str,
        filename: str,
        expires_in: int = 300,  # 5 minutes default
    ) -> tuple[str, str]:
        """
        Get a pre-signed URL for direct upload to storage.

        Args:
            content_type: MIME type of the file
            filename: Original filename (used for extension)
            expires_in: URL expiration in seconds

        Returns:
            Tuple of (pre-signed upload URL, file key)
        """
        file_key = self._generate_file_key(filename)

        if self.backend == StorageBackend.LOCAL:
            # For local storage, return the local path
            file_path = os.path.join(settings.STORAGE_PATH, file_key)
            # Return file:// URL for local development
            upload_url = f"file://{file_path}"
            return upload_url, file_key

        elif self.backend == StorageBackend.R2:
            # Generate pre-signed URL for R2 upload
            upload_url = self.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.R2_BUCKET_NAME,
                    "Key": file_key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
            return upload_url, file_key

        raise ValueError(f"Unknown storage backend: {self.backend}")

    def get_public_url(self, file_key: str) -> str:
        """
        Get public URL for accessing a stored file.

        Args:
            file_key: The key of the file in storage

        Returns:
            Public URL for the file
        """
        if self.backend == StorageBackend.LOCAL:
            return f"file://{settings.STORAGE_PATH}/{file_key}"

        elif self.backend == StorageBackend.R2:
            if settings.R2_PUBLIC_URL:
                return f"{settings.R2_PUBLIC_URL}/{file_key}"
            # Fallback: generate a public URL from the endpoint
            return f"{settings.R2_ENDPOINT}/{settings.R2_BUCKET_NAME}/{file_key}"

        raise ValueError(f"Unknown storage backend: {self.backend}")

    async def delete_file(self, file_key: str) -> bool:
        """
        Delete a file from storage.

        Args:
            file_key: The key of the file to delete

        Returns:
            True if deleted successfully
        """
        if self.backend == StorageBackend.LOCAL:
            file_path = os.path.join(settings.STORAGE_PATH, file_key)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted local file: {file_path}")
                return True
            return False

        elif self.backend == StorageBackend.R2:
            try:
                self.s3_client.delete_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=file_key,
                )
                logger.info(f"Deleted R2 file: {file_key}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete R2 file {file_key}: {e}")
                return False

        raise ValueError(f"Unknown storage backend: {self.backend}")

    async def file_exists(self, file_key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            file_key: The key of the file to check

        Returns:
            True if file exists
        """
        if self.backend == StorageBackend.LOCAL:
            file_path = os.path.join(settings.STORAGE_PATH, file_key)
            return os.path.exists(file_path)

        elif self.backend == StorageBackend.R2:
            try:
                self.s3_client.head_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=file_key,
                )
                return True
            except Exception:
                return False

        return False

    async def get_file_content(self, file_key: str) -> bytes | None:
        """
        Get file content from storage.

        Args:
            file_key: The key of the file

        Returns:
            File content as bytes, or None if not found
        """
        if self.backend == StorageBackend.LOCAL:
            file_path = os.path.join(settings.STORAGE_PATH, file_key)
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    return f.read()
            return None

        elif self.backend == StorageBackend.R2:
            try:
                response = self.s3_client.get_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=file_key,
                )
                return response["Body"].read()
            except Exception as e:
                logger.error(f"Failed to get R2 file {file_key}: {e}")
                return None

        return None


# Singleton instance
storage_service = StorageService()
