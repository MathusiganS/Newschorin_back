from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AdminNewsUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=2_000)
    url: Optional[str] = Field(default=None, max_length=8_000)
    image_path: Optional[str] = Field(default=None, max_length=8_000)
    image: Optional[str] = Field(default=None, max_length=8_000)
    full_text: Optional[str] = Field(default=None, max_length=1_000_000)
    source: Optional[str] = Field(default=None, max_length=255)
    category_ta: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = Field(default=None, max_length=32)
    created_at: Optional[str] = Field(default=None, max_length=128)
