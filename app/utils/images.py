from __future__ import annotations

import base64
import binascii
import logging
import uuid
from pathlib import Path

from app.core.config import get_settings


logger = logging.getLogger(__name__)

ADMIN_IMAGE_MAX_BYTES = 8 * 1024 * 1024
ADMIN_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
}


def normalize_image_path(image_path: str) -> str:
    if not image_path:
        return ""
    if image_path.startswith(("http://", "https://")):
        return image_path
    filename = image_path.replace("\\", "/").rstrip("/").split("/")[-1]
    return f"/images/{filename}" if filename else ""


def to_image_url(image_path: str, image_dir: Path | None = None) -> str:
    normalized = normalize_image_path(image_path)
    if normalized.startswith("/images/"):
        directory = image_dir or get_settings().image_dir
        filename = normalized.rsplit("/", 1)[-1]
        if not (directory / filename).is_file():
            return ""
    return normalized


def save_admin_image_data(image_data: str, image_dir: Path | None = None) -> str:
    header, separator, encoded = image_data.partition(",")
    logger.info(
        "Admin image upload decode started has_separator=%s header_prefix=%s payload_chars=%s",
        bool(separator),
        header[:32],
        len(encoded),
    )
    if not separator or not header.startswith("data:") or ";base64" not in header:
        logger.warning("Admin image upload rejected reason=invalid_data_url")
        raise ValueError("Image upload must be a base64 data URL.")

    media_type = header[5:].split(";", 1)[0].lower()
    extension = ADMIN_IMAGE_TYPES.get(media_type)
    if not extension:
        logger.warning(
            "Admin image upload rejected reason=unsupported_media_type media_type=%s",
            media_type,
        )
        raise ValueError("Choose a JPG, PNG, WebP, GIF, or AVIF image.")

    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        logger.warning(
            "Admin image upload rejected reason=base64_decode_failed media_type=%s",
            media_type,
        )
        raise ValueError("Could not decode the uploaded image.") from exc

    if not content:
        logger.warning(
            "Admin image upload rejected reason=empty_content media_type=%s",
            media_type,
        )
        raise ValueError("Uploaded image is empty.")
    if len(content) > ADMIN_IMAGE_MAX_BYTES:
        logger.warning(
            "Admin image upload rejected reason=file_too_large media_type=%s bytes=%s max_bytes=%s",
            media_type,
            len(content),
            ADMIN_IMAGE_MAX_BYTES,
        )
        raise ValueError("Image must be 8 MB or smaller.")

    directory = image_dir or get_settings().image_dir
    logger.info(
        "Admin image upload writing file media_type=%s bytes=%s directory=%s",
        media_type,
        len(content),
        directory,
    )
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"admin_{uuid.uuid4().hex}.{extension}"
    (directory / filename).write_bytes(content)
    logger.info(
        "Admin image upload saved path=/images/%s exists=%s",
        filename,
        (directory / filename).is_file(),
    )
    return f"/images/{filename}"
