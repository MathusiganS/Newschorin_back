from __future__ import annotations

from typing import Any

from classifier import (
    classify_article_for_pipeline,
    diagnose_classifier,
)


def classify_article(full_text: str, title: str | None = None) -> str:
    return classify_article_for_pipeline(full_text, title)


def classifier_diagnostics() -> dict[str, Any]:
    return diagnose_classifier()
