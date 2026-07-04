"""Compatibility entry point for existing Uvicorn and deployment commands."""

import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
if str(PACKAGE_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGE_DIR))

from app.main import app, create_app

__all__ = ["app", "create_app"]
