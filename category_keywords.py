"""
Approximate Tamil category when ML pickles are not installed (optional).

Enable with: TAMILNEWS_KEYWORD_FALLBACK=1

Uses simple substring rules — not as accurate as your trained model.
Disable once tamil_news_classifier.pkl + label_encoder.pkl are in place.
"""

from __future__ import annotations

import os
import re
from typing import List, Tuple

def _enabled() -> bool:
    """On by default; set TAMILNEWS_KEYWORD_FALLBACK=0 to disable."""
    v = os.environ.get("TAMILNEWS_KEYWORD_FALLBACK", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


# (category_label, list of regex patterns on normalized text)
_RULES: List[Tuple[str, List[str]]] = [
    (
        "அரசியல்",
        [
            r"அமைச்சர்",
            r"ஜனாதிபதி",
            r"அரசாங்கம்",
            r"நாடாளுமன்ற",
            r"இராஜினாமா",
            r"பதவி\s*விலக",
            r"பொலிஸ்",
            r"நீதிமன்ற",
            r"கைது",
            r"போராட்டம்",
            r"படுகொலை",
            r"கொலை",
            r"சடலம்",
            r"விசாரணை",
            r"பல்கலைக்கழக",
        ],
    ),
    (
        "பொருளாதாரம்",
        [
            r"பொருளாதார",
            r"முதலீடு",
            r"முதலீட்டாளர்",
            r"பங்குச் சந்தை",
            r"GDP",
            r"விலைச் சுட்டெண்",
        ],
    ),
    (
        "வணிகம்",
        [
            r"ரூபாய்",
            r"டொலர்",
            r"நாணய\s*மாற்று",
            r"பெற்றோலிய",
            r"எரிபொருள்",
            r"எரிவாயு",
            r"லிட்ரோ",
            r"வர்த்தக",
            r"வணிக",
        ],
    ),
    (
        "விளையாட்டு",
        [
            r"கிரிக்கெட்",
            r"போட்டி",
            r"விளையாட்டு",
            r"சம்பியன்",
            r"கோல்",
        ],
    ),
    (
        "சுகாதாரம்",
        [
            r"வைத்திய",
            r"சிகிச்சை",
            r"படுகாயம்",
            r"குடிநீர்",
            r"சுகாதார",
            r"நீர்மட்டம்",
        ],
    ),
    (
        "தொழில்நுட்பம்",
        [
            r"QR",
            r"கியூ\.ஆர்",
            r"குறியீட்டு\s*முறை",
            r"மின்னல்",
            r"வளிமண்டல",
        ],
    ),
    (
        "சர்வதேசம்",
        [
            r"அமெரிக்க",
            r"ஈரான்",
            r"இந்திய",
            r"இஸ்ரேல",
            r"கடற்படை",
            r"சர்வதேச",
        ],
    ),
    (
        "குற்றம் & சட்டம்",
        [
            r"குற்றம்",
            r"சட்டம்",
            r"நீதிமன்ற",
            r"வழக்கு",
            r"தண்டனை",
            r"போலீஸ்",
        ],
    ),
    (
        "கல்வி",
        [
            r"கல்வி",
            r"பள்ளி",
            r"கல்லூரி",
            r"பல்கலை",
            r"பரீட்சை",
            r"மாணவர்",
        ],
    ),
    (
        "விபத்து & அனர்த்தம்",
        [
            r"விபத்து",
            r"அனர்த்தம்",
            r"வெள்ளம்",
            r"நிலநடுக்க",
            r"புயல்",
            r"சரிவு",
        ],
    ),
    (
        "போக்குவரத்து",
        [
            r"போக்குவரத்து",
            r"பேருந்து",
            r"ரயில்",
            r"விமான",
            r"சாலை",
            r"போக்குவரத்து துறை",
        ],
    ),
    (
        "அரசு அறிவிப்பு",
        [
            r"அறிவிப்பு",
            r"அறிவித்தல்",
            r"அரசு அறிவிப்பு",
            r"அமைச்சு அறிக்கை",
            r"வெளியீடு",
        ],
    ),
    (
        "சுற்றுலா & குடிவரவு",
        [
            r"சுற்றுலா",
            r"குடிவரவு",
            r"விசா",
            r"பாஸ்போர்ட்",
            r"விமான நிலைய",
        ],
    ),
    (
        "மதம் & கலாச்சாரம்",
        [
            r"மதம்",
            r"கலாச்சாரம்",
            r"கோவில்",
            r"திருவிழா",
            r"பண்பாடு",
            r"நாடகம்",
        ],
    ),
]


def keyword_category(full_text: str) -> str:
    if not _enabled() or not (full_text or "").strip():
        return ""
    text = re.sub(r"\s+", " ", (full_text or "")[:8000])
    for label, patterns in _RULES:
        for pat in patterns:
            if re.search(pat, text):
                return label
    return ""
