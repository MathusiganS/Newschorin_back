from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import require_admin
from app.schemas.classification import (
    ClassifyRequest,
    ClassifyResponse,
)
from app.services.classification_service import (
    classifier_diagnostics,
    classify_article,
)


router = APIRouter(prefix="/api", tags=["classification"])


@router.get(
    "/classifier/diagnose",
    dependencies=[Depends(require_admin)],
)
def api_classifier_diagnose():
    return classifier_diagnostics()


@router.post("/classify", response_model=ClassifyResponse)
def api_classify(body: ClassifyRequest) -> ClassifyResponse:
    raw = body.snippet_source()
    if not raw.strip():
        return ClassifyResponse(category_ta="")
    return ClassifyResponse(category_ta=classify_article(raw))
