import logging
import os

logger = logging.getLogger("facturaai")

ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "application/pdf",
}

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}

MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"%PDF": "application/pdf",
}

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def validate_file_magic_bytes(file_path: str) -> tuple[bool, str | None]:
    """
    Validate file by checking magic bytes.

    Returns:
        Tuple of (is_valid, detected_mime_type or None)
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)

        for magic, mime_type in MAGIC_BYTES.items():
            if header.startswith(magic):
                return True, mime_type

        return False, None
    except Exception as e:
        logger.error(f"Error validating file magic bytes: {e}")
        return False, None


def validate_upload(
    content: bytes,
    filename: str | None,
    content_type: str | None,
    max_size_mb: int = MAX_FILE_SIZE_MB,
) -> tuple[bool, str]:
    """
    Validate file upload for security.

    Args:
        content: File content bytes
        filename: Original filename
        content_type: Declared content type
        max_size_mb: Maximum file size in MB

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not content or len(content) == 0:
        return False, "Empty file provided"

    max_size = max_size_mb * 1024 * 1024
    if len(content) > max_size:
        return False, f"File too large: {len(content) / (1024 * 1024):.1f}MB. Max: {max_size_mb}MB"

    if content_type and content_type not in ALLOWED_MIME_TYPES:
        return False, f"Unsupported file type: {content_type}. Allowed: PNG, JPG, PDF"

    if filename:
        ext = os.path.splitext(filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS:
            return False, f"Unsupported file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

    try:
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            is_valid, detected_type = validate_file_magic_bytes(tmp_path)
            if not is_valid:
                return False, "File content does not match its extension (possible disguised file)"
            if content_type and detected_type and content_type != detected_type:
                logger.warning(
                    f"Content type mismatch: declared={content_type}, detected={detected_type}"
                )
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Error during file validation: {e}")
        return False, "Error validating file content"

    return True, ""
