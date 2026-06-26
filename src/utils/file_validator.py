"""
File type validation using magic bytes.

Validates uploaded files by their actual content (magic bytes), not by
file extension. Prevents MIME-type spoofing attacks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("file_validator")

# ---------------------------------------------------------------------------
# Allowed MIME types and their magic bytes
# ---------------------------------------------------------------------------
ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

# Magic byte signatures for validation without python-magic
_MAGIC_SIGNATURES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Maximum file size (10 MB)
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024


class FileValidationError(Exception):
    """Raised when file validation fails."""

    def __init__(self, message: str, error_code: str = "INVALID_FILE") -> None:
        super().__init__(message)
        self.error_code = error_code


def detect_mime_type(file_path: str | Path) -> Optional[str]:
    """
    Detect MIME type using python-magic, falling back to magic byte check.

    Args:
        file_path: Path to the file to check.

    Returns:
        Detected MIME type string, or None if detection fails.
    """
    file_path = Path(file_path)

    # Try python-magic first
    try:
        import magic

        mime = magic.from_file(str(file_path), mime=True)
        return mime
    except ImportError:
        logger.debug("python-magic not available, falling back to magic bytes")
    except Exception as e:
        logger.warning(f"python-magic detection failed: {e}")

    # Fallback: read first bytes
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)
        for signature, mime_type in _MAGIC_SIGNATURES.items():
            if header.startswith(signature):
                return mime_type
    except Exception as e:
        logger.error(f"Magic byte detection failed: {e}")

    return None


def detect_mime_type_from_bytes(data: bytes) -> Optional[str]:
    """
    Detect MIME type from raw bytes.

    Args:
        data: File content bytes (at least first 8 bytes needed).

    Returns:
        Detected MIME type string, or None.
    """
    # Try python-magic first
    try:
        import magic

        mime = magic.from_buffer(data, mime=True)
        return mime
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback to magic bytes
    for signature, mime_type in _MAGIC_SIGNATURES.items():
        if data[:len(signature)] == signature:
            return mime_type

    return None


def validate_file(
    file_path: str | Path,
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> str:
    """
    Validate an uploaded file.

    Checks:
    1. File exists
    2. File size within limits
    3. MIME type is allowed (PDF or DOCX)

    Args:
        file_path: Path to the uploaded file.
        max_size_bytes: Maximum allowed file size in bytes.

    Returns:
        Detected file type string ("pdf" or "docx").

    Raises:
        FileValidationError: If any validation check fails.
    """
    path = Path(file_path)

    # Check existence
    if not path.exists():
        raise FileValidationError(
            f"File not found: {path}",
            error_code="FILE_NOT_FOUND",
        )

    # Check size
    file_size = path.stat().st_size
    if file_size == 0:
        raise FileValidationError(
            "File is empty",
            error_code="FILE_EMPTY",
        )
    if file_size > max_size_bytes:
        size_mb = file_size / (1024 * 1024)
        max_mb = max_size_bytes / (1024 * 1024)
        raise FileValidationError(
            f"File too large: {size_mb:.1f}MB (max: {max_mb:.0f}MB)",
            error_code="FILE_TOO_LARGE",
        )

    # Check MIME type by magic bytes
    mime_type = detect_mime_type(path)
    if mime_type is None:
        raise FileValidationError(
            "Could not determine file type",
            error_code="UNKNOWN_TYPE",
        )

    if mime_type not in ALLOWED_MIME_TYPES:
        raise FileValidationError(
            f"Unsupported file type: {mime_type}. "
            f"Allowed: {', '.join(ALLOWED_MIME_TYPES.keys())}",
            error_code="UNSUPPORTED_TYPE",
        )

    file_type = ALLOWED_MIME_TYPES[mime_type]
    logger.debug(f"Validated file {path.name}: type={file_type}, size={file_size}")
    return file_type


def validate_file_bytes(
    data: bytes,
    filename: str = "unknown",
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> str:
    """
    Validate file content from bytes (for in-memory uploads).

    Args:
        data: File content bytes.
        filename: Original filename (for logging).
        max_size_bytes: Maximum allowed size.

    Returns:
        Detected file type ("pdf" or "docx").

    Raises:
        FileValidationError: If validation fails.
    """
    if not data:
        raise FileValidationError("File is empty", error_code="FILE_EMPTY")

    if len(data) > max_size_bytes:
        size_mb = len(data) / (1024 * 1024)
        max_mb = max_size_bytes / (1024 * 1024)
        raise FileValidationError(
            f"File too large: {size_mb:.1f}MB (max: {max_mb:.0f}MB)",
            error_code="FILE_TOO_LARGE",
        )

    mime_type = detect_mime_type_from_bytes(data)
    if mime_type is None:
        raise FileValidationError(
            "Could not determine file type",
            error_code="UNKNOWN_TYPE",
        )

    if mime_type not in ALLOWED_MIME_TYPES:
        raise FileValidationError(
            f"Unsupported file type: {mime_type}",
            error_code="UNSUPPORTED_TYPE",
        )

    file_type = ALLOWED_MIME_TYPES[mime_type]
    logger.debug(f"Validated bytes for {filename}: type={file_type}")
    return file_type
