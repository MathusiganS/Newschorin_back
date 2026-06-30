"""Compatibility entry point for existing Uvicorn and deployment commands."""

import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_DIR.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tamilwin_scraper.app.main import app, create_app

__all__ = ["app", "create_app"]
