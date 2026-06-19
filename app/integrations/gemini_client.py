from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher

import requests

from tamilwin_scraper.app.core.config import Settings, get_settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParaphraseResult:
    title: str
    full_text: str
    changed: bool


class GeminiClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def status(self) -> dict[str, object]:
        return {
            "gemini_api_key_configured": self.configured,
            "model": self.settings.gemini_model,
            "temperature": self.settings.gemini_temperature,
            "topP": self.settings.gemini_top_p,
            "maxOutputTokens": self.settings.gemini_max_output_tokens,
        }

    def paraphrase_news(self, title: str, full_text: str) -> ParaphraseResult:
        if not self.configured or (not title and not full_text):
            logger.info("Paraphrase skipped because Gemini is not configured")
            return ParaphraseResult(title, full_text, False)
        if len(full_text) > 6_000:
            return self._paraphrase_long_news(title, full_text)

        prompt = f"""
Paraphrase the following Tamil news title and full text without changing the original meaning.

Rules:
1. Do not change names, dates, numbers, locations, organizations, or quotes.
2. Do not add new information.
3. Do not show the news source in the title or full_text.
4. Rewrite the title as a fresh Tamil news headline. Do not copy the original title word-for-word.
5. Keep the title concise, natural, professional, and suitable for a news website.
6. Keep the title meaning exactly the same as the original.
7. Rewrite every sentence in the body naturally; do not merely replace a few words.
8. Preserve all paragraphs and factual details. Do not summarize or shorten the article.
9. Keep the rewritten body close to the original length.
10. Return only valid JSON with exactly these keys: title, full_text.

Original title:
{title}

Original full_text:
{full_text}
""".strip()

        output_tokens = self._article_output_tokens(full_text)
        for attempt in range(1, self.settings.gemini_max_attempts + 1):
            try:
                attempt_prompt = prompt
                if attempt > 1:
                    attempt_prompt += (
                        "\n\nPrevious output was too similar, incomplete, or shortened. "
                        "Rewrite more distinctly while preserving every fact and paragraph."
                    )
                parsed = self._generate_json(
                    attempt_prompt,
                    timeout=90,
                    max_output_tokens=output_tokens,
                    temperature=max(self.settings.gemini_temperature, 0.4),
                )
                new_title = str(parsed.get("title") or "").strip()
                new_full_text = str(parsed.get("full_text") or "").strip()
                body_is_valid = (
                    body_rewrite_acceptable(full_text, new_full_text)
                    if full_text.strip()
                    else True
                )
                if not body_is_valid:
                    logger.warning(
                        "Gemini body rewrite rejected attempt=%s original_chars=%s rewritten_chars=%s",
                        attempt,
                        len(full_text),
                        len(new_full_text),
                    )
                    continue
                if titles_too_similar(title, new_title):
                    new_title = self.paraphrase_title(title, new_full_text)
                if titles_too_similar(title, new_title):
                    logger.warning(
                        "Gemini title rewrite remained too similar attempt=%s",
                        attempt,
                    )
                    continue
                return ParaphraseResult(new_title, new_full_text, True)
            except Exception:
                logger.exception(
                    "Gemini article paraphrasing failed attempt=%s", attempt
                )
        return ParaphraseResult(title, full_text, False)

    def _paraphrase_long_news(
        self,
        title: str,
        full_text: str,
    ) -> ParaphraseResult:
        chunks = split_text_chunks(full_text)
        rewritten_chunks: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            rewritten = self._paraphrase_body_chunk(
                chunk,
                index=index,
                total=len(chunks),
            )
            if not rewritten:
                logger.warning(
                    "Long article paraphrasing aborted chunk=%s/%s",
                    index,
                    len(chunks),
                )
                return ParaphraseResult(title, full_text, False)
            rewritten_chunks.append(rewritten)

        rewritten_body = "\n\n".join(rewritten_chunks)
        if not body_rewrite_acceptable(full_text, rewritten_body):
            logger.warning(
                "Combined long article rewrite rejected original_chars=%s rewritten_chars=%s",
                len(full_text),
                len(rewritten_body),
            )
            return ParaphraseResult(title, full_text, False)

        rewritten_title = self.paraphrase_title(title, rewritten_body)
        if titles_too_similar(title, rewritten_title):
            logger.warning("Long article title rewrite remained too similar")
            return ParaphraseResult(title, full_text, False)
        return ParaphraseResult(rewritten_title, rewritten_body, True)

    def _paraphrase_body_chunk(
        self,
        chunk: str,
        *,
        index: int,
        total: int,
    ) -> str:
        prompt = f"""
Rewrite this section of a Tamil news article in fresh, professional Tamil.

Rules:
1. Preserve every fact, name, date, number, place, organization, and quote.
2. Do not add information.
3. Rewrite every sentence naturally with different wording and structure.
4. Do not summarize, shorten, introduce, or conclude the section.
5. Preserve paragraph breaks and keep the output close to the original length.
6. This is section {index} of {total}; rewrite only the supplied section.
7. Return only valid JSON with exactly this key: full_text.

Article section:
{chunk}
""".strip()
        output_tokens = self._article_output_tokens(chunk)
        for attempt in range(1, self.settings.gemini_max_attempts + 1):
            try:
                attempt_prompt = prompt
                if attempt > 1:
                    attempt_prompt += (
                        "\n\nThe previous output was incomplete or too similar. "
                        "Rewrite the complete section more distinctly."
                    )
                parsed = self._generate_json(
                    attempt_prompt,
                    timeout=90,
                    max_output_tokens=output_tokens,
                    temperature=max(self.settings.gemini_temperature, 0.4),
                )
                rewritten = str(parsed.get("full_text") or "").strip()
                if body_rewrite_acceptable(chunk, rewritten):
                    return rewritten
                logger.warning(
                    "Gemini chunk rewrite rejected chunk=%s/%s attempt=%s original_chars=%s rewritten_chars=%s",
                    index,
                    total,
                    attempt,
                    len(chunk),
                    len(rewritten),
                )
            except Exception:
                logger.exception(
                    "Gemini chunk paraphrasing failed chunk=%s/%s attempt=%s",
                    index,
                    total,
                    attempt,
                )
        return ""

    def paraphrase_title(self, title: str, full_text: str = "") -> str:
        if not self.configured or not title:
            return title
        context = (full_text or "").strip()[:1200]
        prompt = f"""
Rewrite only this Tamil news title as a fresh headline.

Rules:
1. Preserve the same facts, names, dates, numbers, places, and meaning.
2. Do not add any new information.
3. Do not copy the original wording.
4. Keep it natural, professional, and concise for a Tamil news website.
5. Return only valid JSON with exactly this key: title.

Original title:
{title}

Article context:
{context}
""".strip()
        for attempt in range(1, self.settings.gemini_max_attempts + 1):
            try:
                attempt_prompt = prompt
                if attempt > 1:
                    attempt_prompt += (
                        "\n\nUse clearly different wording and sentence structure "
                        "while keeping the exact same facts."
                    )
                parsed = self._generate_json(
                    attempt_prompt,
                    timeout=45,
                    max_output_tokens=300,
                    temperature=max(self.settings.gemini_temperature, 0.55),
                )
                new_title = str(parsed.get("title") or "").strip()
                if new_title and not titles_too_similar(title, new_title):
                    return new_title
                logger.warning(
                    "Gemini title rewrite rejected attempt=%s", attempt
                )
            except Exception:
                logger.exception(
                    "Gemini title paraphrasing failed attempt=%s", attempt
                )
        return title

    def _article_output_tokens(self, full_text: str) -> int:
        estimated = int(max(1, len((full_text or "").split())) * 2.5) + 400
        return min(
            8192,
            max(self.settings.gemini_max_output_tokens, estimated),
        )

    def _generate_json(
        self,
        prompt: str,
        *,
        timeout: int,
        max_output_tokens: int,
        temperature: float,
    ) -> dict[str, object]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.settings.gemini_model}:generateContent"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "topP": self.settings.gemini_top_p,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
        }
        response = None
        for request_attempt in range(1, 4):
            response = requests.post(
                url,
                headers={"x-goog-api-key": self.settings.gemini_api_key},
                json=payload,
                timeout=timeout,
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if request_attempt < 3:
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else request_attempt * 2
                logger.warning(
                    "Gemini transient error status=%s retry_in=%ss",
                    response.status_code,
                    delay,
                )
                time.sleep(delay)
        if response is None:
            raise RuntimeError("Gemini request was not sent")
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini response did not contain candidates")
        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")
        if finish_reason not in (None, "STOP"):
            raise ValueError(f"Gemini stopped with finishReason={finish_reason}")
        parts = candidate.get("content", {}).get("parts") or []
        if not parts:
            raise ValueError("Gemini response did not contain text")
        text = parts[0].get("text", "")
        stripped = str(text).strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("Gemini response must be a JSON object")
        return parsed


def titles_too_similar(original: str, rewritten: str) -> bool:
    original_norm = " ".join((original or "").split()).strip()
    rewritten_norm = " ".join((rewritten or "").split()).strip()
    if not original_norm or not rewritten_norm:
        return True
    if original_norm == rewritten_norm:
        return True
    original_words = set(original_norm.split())
    rewritten_words = set(rewritten_norm.split())
    overlap = len(original_words & rewritten_words) / max(1, len(original_words))
    return overlap >= 0.85


def body_rewrite_acceptable(original: str, rewritten: str) -> bool:
    original_norm = " ".join((original or "").split()).strip()
    rewritten_norm = " ".join((rewritten or "").split()).strip()
    if not original_norm:
        return bool(rewritten_norm)
    if not rewritten_norm or original_norm == rewritten_norm:
        return False
    length_ratio = len(rewritten_norm) / len(original_norm)
    if not 0.65 <= length_ratio <= 1.45:
        return False
    similarity = SequenceMatcher(
        None,
        original_norm[:20_000],
        rewritten_norm[:20_000],
        autojunk=False,
    ).ratio()
    return similarity < 0.96


def split_text_chunks(text: str, max_chars: int = 4_500) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n|\n", cleaned)
        if paragraph.strip()
    ]
    units: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            units.append(paragraph)
            continue
        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?\u0964])\s+", paragraph)
            if sentence.strip()
        ]
        for sentence in sentences:
            if len(sentence) <= max_chars:
                units.append(sentence)
                continue
            words = sentence.split()
            current_words: list[str] = []
            current_length = 0
            for word in words:
                added_length = len(word) + (1 if current_words else 0)
                if current_words and current_length + added_length > max_chars:
                    units.append(" ".join(current_words))
                    current_words = []
                    current_length = 0
                current_words.append(word)
                current_length += added_length
            if current_words:
                units.append(" ".join(current_words))

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for unit in units:
        separator_length = 2 if current else 0
        if current and current_length + separator_length + len(unit) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_length = 0
            separator_length = 0
        current.append(unit)
        current_length += separator_length + len(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks
