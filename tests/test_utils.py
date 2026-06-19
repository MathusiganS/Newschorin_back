from __future__ import annotations

from datetime import datetime

from tamilwin_scraper.app.integrations.gemini_client import (
    body_rewrite_acceptable,
    split_text_chunks,
    titles_too_similar,
)
from tamilwin_scraper.app.core.passwords import hash_password, verify_password
from tamilwin_scraper.app.utils.datetime import (
    json_datetime,
    parse_scraped_datetime,
)
from tamilwin_scraper.app.utils.images import normalize_image_path


def test_image_path_contract() -> None:
    assert normalize_image_path("") == ""
    assert normalize_image_path("https://example.com/a.jpg") == (
        "https://example.com/a.jpg"
    )
    assert normalize_image_path(r"C:\images\story.webp") == "/images/story.webp"


def test_datetime_contract_uses_sri_lanka_offset() -> None:
    parsed = parse_scraped_datetime("2026-06-11T10:00:00Z")
    assert parsed == "2026-06-11T15:30:00"
    serialized = json_datetime(datetime(2026, 6, 11, 15, 30))
    assert serialized == "2026-06-11T15:30:00+05:30"


def test_title_similarity_contract() -> None:
    assert titles_too_similar("ஒரு புதிய செய்தி", "ஒரு புதிய செய்தி")
    assert not titles_too_similar(
        "அரசின் புதிய அறிவிப்பு",
        "புதிய திட்டத்தை அரசு வெளியிட்டது",
    )


def test_admin_password_hash_round_trip() -> None:
    encoded = hash_password("strong-password", salt=b"0123456789abcdef")
    assert verify_password("strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_body_rewrite_quality_validation() -> None:
    original = "அரசு இன்று புதிய திட்டத்தை அறிவித்தது. மக்கள் வரவேற்றனர்."
    rewritten = "புதிய திட்டம் ஒன்றை அரசு இன்று வெளியிட்டது. அதற்கு பொதுமக்கள் ஆதரவு தெரிவித்தனர்."
    assert body_rewrite_acceptable(original, rewritten)
    assert not body_rewrite_acceptable(original, original)
    assert not body_rewrite_acceptable(original, "சுருக்கம்")


def test_long_article_chunking_preserves_all_text() -> None:
    paragraphs = [
        " ".join(f"word{index}_{word}" for word in range(300))
        for index in range(8)
    ]
    original = "\n\n".join(paragraphs)
    chunks = split_text_chunks(original, max_chars=1_000)
    assert len(chunks) > 1
    assert " ".join(original.split()) == " ".join("\n\n".join(chunks).split())
    assert all(len(chunk) <= 1_000 for chunk in chunks)
