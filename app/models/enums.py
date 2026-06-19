from __future__ import annotations

from enum import Enum


class NewsStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
