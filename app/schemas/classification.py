from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    text: Optional[str] = Field(default=None, max_length=100_000)
    full_text: Optional[str] = Field(default=None, max_length=100_000)

    def snippet_source(self) -> str:
        return self.text or self.full_text or ""


class ClassifyResponse(BaseModel):
    category_ta: str = Field(default="")
