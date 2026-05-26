"""
Tamil news category from article text (first 70 words, cleaned).

Expected layout (same as your training script):

    model = joblib.load("tamil_news_classifier.pkl")
    le    = joblib.load("label_encoder.pkl")
    label = le.inverse_transform(model.predict(["cleaned Tamil text"]))[0]

Pickle resolution order (first file found wins):
  1. TAMILNEWS_MODEL_DIR env
  2. tamilwin_scraper/models/tamil_news_classifier.pkl
  3. tamilwin_scraper/tamil_news_classifier.pkl

Classifier pickle is required for ML labels; `label_encoder.pkl` is optional if
`predict` already returns Tamil strings. Use `TAMILNEWS_KEYWORD_FALLBACK=1` for
rough categories when no ML files exist.

joblib / numpy load lazily so Scrapy can start without ML deps until you:
  pip install joblib scikit-learn numpy
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

# Canonical Tamil labels (fallback if encoder is missing / index only)
TAMIL_CATEGORIES_1_TO_14 = {
    1: "அரசியல்",
    2: "பொருளாதாரம்",
    3: "வணிகம்",
    4: "விளையாட்டு",
    5: "சுகாதாரம்",
    6: "தொழில்நுட்பம்",
    7: "சர்வதேசம்",
    8: "குற்றம் & சட்டம்",
    9: "கல்வி",
    10: "விபத்து & அனர்த்தம்",
    11: "போக்குவரத்து",
    12: "அரசு அறிவிப்பு",
    13: "சுற்றுலா & குடிவரவு",
    14: "மதம் & கலாச்சாரம்",
}
ORDERED_TAMIL = [TAMIL_CATEGORIES_1_TO_14[i] for i in range(1, 15)]

# Training often uses English class names; UI / DB expect these Tamil labels.
_ENGLISH_TO_TAMIL = {
    "politics": "அரசியல்",
    "political": "அரசியல்",
    "government": "அரசியல்",
    "economics": "பொருளாதாரம்",
    "economy": "பொருளாதாரம்",
    "finance": "பொருளாதாரம்",
    "business": "வணிகம்",
    "commercial": "வணிகம்",
    "sports": "விளையாட்டு",
    "sport": "விளையாட்டு",
    "health": "சுகாதாரம்",
    "medical": "சுகாதாரம்",
    "healthcare": "சுகாதாரம்",
    "technology": "தொழில்நுட்பம்",
    "tech": "தொழில்நுட்பம்",
    "science": "தொழில்நுட்பம்",
    "international": "சர்வதேசம்",
    "world": "சர்வதேசம்",
    "foreign": "சர்வதேசம்",
    "crime": "குற்றம் & சட்டம்",
    "law": "குற்றம் & சட்டம்",
    "crime & law": "குற்றம் & சட்டம்",
    "education": "கல்வி",
    "accident": "விபத்து & அனர்த்தம்",
    "disaster": "விபத்து & அனர்த்தம்",
    "accident & disaster": "விபத்து & அனர்த்தம்",
    "transport": "போக்குவரத்து",
    "transportation": "போக்குவரத்து",
    "traffic": "போக்குவரத்து",
    "govt announcement": "அரசு அறிவிப்பு",
    "government announcement": "அரசு அறிவிப்பு",
    "tourism": "சுற்றுலா & குடிவரவு",
    "immigration": "சுற்றுலா & குடிவரவு",
    "tourism & immigration": "சுற்றுலா & குடிவரவு",
    "religion": "மதம் & கலாச்சாரம்",
    "culture": "மதம் & கலாச்சாரம்",
    "religion & culture": "மதம் & கலாச்சாரம்",
}


def canonical_tamil_category(raw: str) -> str:
    """Map encoder English / mixed labels → fixed Tamil category names."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s in ORDERED_TAMIL:
        return s
    key = re.sub(r"\s+", " ", s.lower())
    if key in _ENGLISH_TO_TAMIL:
        return _ENGLISH_TO_TAMIL[key]
    for en, ta in _ENGLISH_TO_TAMIL.items():
        if en in key or key in en:
            return ta
    return s


def models_dir() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    override = os.environ.get("TAMILNEWS_MODEL_DIR")
    if override:
        return override
    return os.path.join(root, "models")


def first_n_words(text: str, n: int = 70) -> str:
    parts = (text or "").split()
    return " ".join(parts[:n]).strip()


def clean_tamil_snippet(text: str) -> str:
    """Whitespace + invisible Unicode noise → single spaced string for the model."""
    s = (text or "").strip()
    s = re.sub(r"[\u200b-\u200f\ufeff]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_for_model(text: str) -> str:
    """Remove common scrape noise before classification."""
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\S+@\S+", " ", s)
    s = re.sub(r"\s+\|\s+", " ", s)
    s = re.sub(r"\s+", " ", s)

    noise_phrases = [
        "மேலும் வாசிக்க",
        "மேலும் படிக்க",
        "தொடர்ந்து வாசிக்க",
        "தொடர்ந்து படிக்க",
        "மேலும் செய்திகள்",
        "தொடர்புடைய செய்திகள்",
        "பகிரவும்",
        "பகிர",
        "பின்தொடர",
        "Follow",
        "Share",
        "Subscribe",
        "Advertisement",
        "Ad",
        "Cookies",
        "Privacy",
    ]
    for phrase in noise_phrases:
        s = s.replace(phrase, " ")

    s = re.sub(r"\s+", " ", s).strip()
    return s


def _get_numpy():
    try:
        import numpy as np
        return np
    except ImportError:
        return None


CLF_FILENAMES = (
    "tamil_news_classifier.pkl",
    "tamil_news_classifier.joblib",
    "news_classifier.pkl",
    "classifier.pkl",
)
ENC_FILENAMES = (
    "label_encoder.pkl",
    "label_encoder.joblib",
    "encoder.pkl",
)


def _search_roots() -> list[str]:
    """Directories to search for pickles (first match wins per asset)."""
    pkg = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(pkg)
    roots: list[str] = []
    override = os.environ.get("TAMILNEWS_MODEL_DIR")
    if override:
        roots.append(override)
    for r in (
        os.path.join(pkg, "models"),
        pkg,
        os.path.join(repo, "models"),
        repo,
    ):
        if r and r not in roots:
            roots.append(r)
    return roots


def _resolve_first(filenames: tuple[str, ...]) -> Optional[str]:
    seen_paths: set[str] = set()
    for root in _search_roots():
        for name in filenames:
            p = os.path.join(root, name)
            if p in seen_paths:
                continue
            seen_paths.add(p)
            if os.path.isfile(p):
                return p
    return None


def _prediction_scalar(raw: Any) -> Any:
    if raw is None:
        return None
    np = _get_numpy()
    if np is not None and isinstance(raw, np.ndarray):
        flat = raw.reshape(-1)
        return flat[0] if flat.size else None
    if isinstance(raw, (list, tuple)) and len(raw):
        return _prediction_scalar(raw[0])
    if hasattr(raw, "item"):
        try:
            return raw.item()
        except Exception:
            pass
    return raw


def _numeric_index(val: Any) -> Optional[int]:
    try:
        if val is None:
            return None
        if isinstance(val, str) and val.strip().lstrip("-").isdigit():
            return int(val.strip())
        if isinstance(val, (float, int)) and not isinstance(val, bool):
            return int(val)
    except (TypeError, ValueError):
        return None
    return None


def index_to_tamil_label(idx: int) -> str:
    if 1 <= idx <= 14:
        return TAMIL_CATEGORIES_1_TO_14[idx]
    if 0 <= idx <= 13:
        return ORDERED_TAMIL[idx]
    return ""


def _encoder_to_label(label_encoder: Any, idx: int) -> str:
    if label_encoder is None:
        return ""
    try:
        inv = label_encoder.inverse_transform([int(idx)])
        return str(inv[0]).strip()
    except Exception:
        pass
    try:
        classes = getattr(label_encoder, "classes_", None)
        if classes is not None and len(classes) > 0:
            n = int(idx)
            if 0 <= n < len(classes):
                return str(classes[n]).strip()
            if 1 <= n <= len(classes):
                return str(classes[n - 1]).strip()
    except Exception:
        pass
    return ""


def decode_prediction(pred_raw: Any, label_encoder: Any) -> str:
    val = _prediction_scalar(pred_raw)
    if val is None:
        return ""
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return ""
        if s.isdigit():
            n = int(s)
            out = _encoder_to_label(label_encoder, n)
            return out or index_to_tamil_label(n) or s
        return s
    n = _numeric_index(val)
    if n is None:
        return str(val).strip()
    out = _encoder_to_label(label_encoder, n)
    return out or index_to_tamil_label(n) or str(val)


class TamilNewsClassifier:
    """Loads both joblib artifacts; predicts via predict + inverse_transform."""

    def __init__(self) -> None:
        self._model = None
        self._label_encoder: Any = None
        self._tried_load = False
        self._load_error: Optional[str] = None
        self._clf_path: Optional[str] = None
        self._enc_path: Optional[str] = None

    def load(self) -> None:
        if self._tried_load:
            return
        self._tried_load = True
        try:
            import joblib
        except ImportError as e:
            self._load_error = (
                f"joblib is not installed ({e}). "
                "Run: pip install joblib scikit-learn numpy"
            )
            return

        self._clf_path = _resolve_first(CLF_FILENAMES)
        self._enc_path = _resolve_first(ENC_FILENAMES)

        if not self._clf_path:
            self._load_error = (
                "Missing classifier pickle. Tried: "
                + ", ".join(CLF_FILENAMES)
                + " under TAMILNEWS_MODEL_DIR, tamilwin_scraper/models/, "
                "tamilwin_scraper/, or repo ../models/ and ../"
            )
            return

        try:
            self._model = joblib.load(self._clf_path)
        except Exception as e:
            self._load_error = str(e)
            self._model = None
            self._label_encoder = None
            return

        self._load_error = None
        if self._enc_path:
            try:
                self._label_encoder = joblib.load(self._enc_path)
            except Exception as e:
                self._load_error = f"Classifier loaded but label_encoder failed: {e}"
                self._label_encoder = None
        else:
            self._label_encoder = None

    @property
    def available(self) -> bool:
        """True when the classifier pickle loads (encoder optional)."""
        self.load()
        return self._model is not None

    @property
    def load_error(self) -> Optional[str]:
        self.load()
        return self._load_error

    def predict_category(self, full_text: str) -> str:
        """
        First 70 words → clean string → model.predict([text]) →
        if label_encoder: le.inverse_transform(...)[0]
        else: decode numeric / string from predict only.
        """
        self.load()
        if self._model is None:
            return ""

        cleaned_source = clean_for_model(full_text)
        cleaned = clean_tamil_snippet(first_n_words(cleaned_source, 70))
        if not cleaned:
            return ""

        np = _get_numpy()
        le = self._label_encoder

        if le is not None:
            # --- Primary: label = le.inverse_transform(model.predict([text]))[0] ---
            try:
                raw = self._model.predict([cleaned])
                if np is not None:
                    raw_arr = np.asarray(raw)
                    labels = le.inverse_transform(raw_arr.ravel())
                else:
                    labels = le.inverse_transform(raw)
                return canonical_tamil_category(str(labels[0]).strip())
            except Exception:
                pass

            try:
                raw = self._model.predict([cleaned])
                if np is not None:
                    idx = np.asarray(raw, dtype=int).ravel()
                    labels = le.inverse_transform(idx)
                else:
                    labels = le.inverse_transform([int(_prediction_scalar(raw))])
                return canonical_tamil_category(str(labels[0]).strip())
            except Exception:
                pass

            if np is not None:
                try:
                    raw = self._model.predict(np.array([cleaned], dtype=object))
                    labels = le.inverse_transform(np.asarray(raw).ravel())
                    return canonical_tamil_category(str(labels[0]).strip())
                except Exception:
                    pass

        # --- Encoder missing, or inverse_transform failed: use raw prediction ---
        try:
            raw = self._model.predict([cleaned])
            s = _prediction_scalar(raw)
            if isinstance(s, str) and s.strip():
                return canonical_tamil_category(s.strip())
            return canonical_tamil_category(decode_prediction(raw, le))
        except Exception:
            pass

        if np is not None:
            try:
                raw = self._model.predict(np.array([cleaned], dtype=object))
                s = _prediction_scalar(raw)
                if isinstance(s, str) and s.strip():
                    return canonical_tamil_category(s.strip())
                return canonical_tamil_category(decode_prediction(raw, le))
            except Exception:
                pass

        return ""


_classifier: Optional[TamilNewsClassifier] = None


def get_classifier() -> TamilNewsClassifier:
    global _classifier
    if _classifier is None:
        _classifier = TamilNewsClassifier()
    return _classifier


def classify_article_for_pipeline(full_text: str, title: Optional[str] = None) -> str:
    """
    Prefer ML (title + body → clean → first 70 words → predict → inverse_transform).
    If that returns empty or no model: keyword rules when enabled
    (TAMILNEWS_KEYWORD_FALLBACK=1 by default; set 0 to disable).
    """
    combined = " ".join([s for s in [title, full_text] if s]).strip()
    cleaned = clean_for_model(combined)
    if len(cleaned.split()) < 8:
        return ""
    clf = get_classifier()
    cat = ""
    if clf.available:
        cat = clf.predict_category(cleaned)
    if cat:
        return cat
    from tamilwin_scraper.category_keywords import keyword_category

    return canonical_tamil_category(keyword_category(cleaned) or "")


def diagnose_classifier() -> dict[str, Any]:
    """For scripts / logs: why categories might be empty."""
    c = get_classifier()
    c.load()
    roots = _search_roots()
    return {
        "available": c.available,
        "load_error": c.load_error,
        "classifier_path": c._clf_path,
        "label_encoder_path": c._enc_path,
        "searched_roots": roots,
        "keyword_fallback": os.environ.get("TAMILNEWS_KEYWORD_FALLBACK", ""),
    }
