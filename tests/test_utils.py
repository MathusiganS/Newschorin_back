from __future__ import annotations

from datetime import datetime

from app.integrations.gemini_client import (
    body_rewrite_acceptable,
    split_text_chunks,
    titles_too_similar,
)
from app.core.passwords import hash_password, verify_password
from app.utils.datetime import (
    json_datetime,
    parse_scraped_datetime,
)
from app.utils.images import normalize_image_path
from app.utils.images import save_admin_image_data


def test_image_path_contract() -> None:
    assert normalize_image_path("") == ""
    assert normalize_image_path("https://example.com/a.jpg") == (
        "https://example.com/a.jpg"
    )
    assert normalize_image_path(r"C:\images\story.webp") == "/images/story.webp"


def test_admin_row_preserves_stored_local_image_path() -> None:
    from app.repositories.news_repository import NewsRepository

    row = (
        1,
        "Title",
        "https://example.com/story",
        "/images/missing.webp",
        "Body",
        "source",
        "category",
        "approved",
        None,
        "",
        "",
    )

    article = NewsRepository._admin_row(row)

    assert article["image"] == "/images/missing.webp"
    assert article["image_path"] == "/images/missing.webp"


def test_save_admin_image_data_writes_file(tmp_path) -> None:
    image_path = save_admin_image_data(
        "data:image/png;base64,iVBORw0KGgo=", image_dir=tmp_path
    )

    assert image_path.startswith("/images/admin_")
    assert image_path.endswith(".png")
    assert (tmp_path / image_path.rsplit("/", 1)[-1]).read_bytes() == (
        b"\x89PNG\r\n\x1a\n"
    )


def test_save_admin_image_data_rejects_unsupported_type(tmp_path) -> None:
    try:
        save_admin_image_data("data:text/plain;base64,aGVsbG8=", image_dir=tmp_path)
    except ValueError as exc:
        assert "JPG, PNG, WebP, GIF, or AVIF" in str(exc)
    else:
        raise AssertionError("Unsupported uploads should fail")


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
