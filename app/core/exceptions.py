from __future__ import annotations


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot be reached."""


class ExternalServiceError(RuntimeError):
    """Raised when an external service fails."""
