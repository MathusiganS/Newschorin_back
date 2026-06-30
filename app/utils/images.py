from __future__ import annotations

from pathlib import Path

from tamilwin_scraper.app.core.config import get_settings


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
