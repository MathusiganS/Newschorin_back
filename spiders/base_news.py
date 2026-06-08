import json
import os
import re
import urllib.request
from urllib.parse import urlparse

import scrapy

from tamilwin_scraper.spiders.date_utils import extract_published_at


IMAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "image",
)


class BaseNewsSpider(scrapy.Spider):
    start_url = ""
    source = ""
    listing_selectors = ()
    article_url_marker = "/article/"
    article_url_pattern = None
    title_cleanup_pattern = None
    title_suffixes = ()
    content_selectors = ()
    image_selectors = (
        ".ds-content img::attr(src)",
        ".article-image img::attr(src)",
        ".entry-content img::attr(src)",
        "article img::attr(src)",
    )
    max_articles = 10
    use_playwright = True

    playwright_meta = {
        "playwright": True,
        "playwright_include_page": False,
        "playwright_page_goto_kwargs": {
            "wait_until": "domcontentloaded",
            "timeout": 60000,
        },
    }

    async def start(self):
        os.makedirs(IMAGE_DIR, exist_ok=True)
        yield scrapy.Request(url=self.start_url, meta=self._request_meta())

    def parse(self, response):
        seen_urls = set()
        count = 0

        for selector in self.listing_selectors:
            for link_el in response.css(selector):
                href = link_el.attrib.get("href", "")
                if not href:
                    continue

                url = response.urljoin(href)
                if url in seen_urls or not self._is_article_url(url):
                    continue

                title = self._extract_listing_title(link_el)
                if not title:
                    continue

                seen_urls.add(url)
                count += 1
                if count > self.max_articles:
                    return

                yield scrapy.Request(
                    url=url,
                    callback=self.parse_article,
                    meta={**self._request_meta(), "title": title},
                )

    def parse_article(self, response):
        title = self._extract_article_title(response, response.meta.get("title", ""))
        image_url = self._extract_image(response)
        full_text = self._extract_body(response)

        yield {
            "title": title,
            "url": response.url,
            "image_path": image_url,
            "full_text": full_text,
            "source": self.source or self.name,
            "created_at": extract_published_at(response),
        }

    def _request_meta(self):
        return dict(self.playwright_meta) if self.use_playwright else {}

    def _is_article_url(self, url):
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        allowed = tuple(domain.lower() for domain in getattr(self, "allowed_domains", ()))
        if allowed and not any(host == domain or host.endswith(f".{domain}") for domain in allowed):
            return False

        if self.article_url_pattern:
            return re.search(self.article_url_pattern, parsed.path) is not None
        if self.article_url_marker:
            return self.article_url_marker in url
        return True

    def _extract_listing_title(self, link_el):
        title = link_el.css("::text").get("").strip()
        if not title or len(title) < 5:
            title = " ".join(
                text.strip()
                for text in link_el.xpath(".//text()").getall()
                if text.strip()
            )

        title = self._clean_title(title)
        return title if len(title) >= 5 else ""

    def _extract_article_title(self, response, fallback):
        title = fallback.strip()
        og_title = response.css('meta[property="og:title"]::attr(content)').get("")
        if og_title and len(og_title.strip()) > len(title):
            title = og_title.strip().split("|")[0].strip()

        return self._clean_title(title)

    def _clean_title(self, title):
        title = re.sub(r"\s+", " ", title or "").strip()
        if self.title_cleanup_pattern:
            title = re.sub(
                self.title_cleanup_pattern,
                "",
                title,
                flags=re.IGNORECASE,
            ).strip()

        for suffix in self.title_suffixes:
            if title.lower().endswith(suffix.lower()):
                title = title[: -len(suffix)].strip()
        return title

    def _extract_image(self, response):
        image_url = response.css('meta[property="og:image"]::attr(content)').get("")
        if image_url:
            return response.urljoin(image_url)

        for block in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(block)
            except (json.JSONDecodeError, TypeError):
                continue

            image_url = self._find_json_image(data)
            if image_url:
                return response.urljoin(image_url)

        for selector in self.image_selectors:
            image_url = response.css(selector).get("")
            if image_url:
                return response.urljoin(image_url)
        return ""

    def _find_json_image(self, value):
        if isinstance(value, dict):
            image = value.get("image")
            if isinstance(image, str) and image:
                return image
            if isinstance(image, dict) and image.get("url"):
                return image["url"]
            if isinstance(image, list):
                for item in image:
                    if isinstance(item, str) and item:
                        return item
                    if isinstance(item, dict) and item.get("url"):
                        return item["url"]
            for child in value.values():
                image_url = self._find_json_image(child)
                if image_url:
                    return image_url
        elif isinstance(value, list):
            for child in value:
                image_url = self._find_json_image(child)
                if image_url:
                    return image_url
        return ""

    def _extract_body(self, response):
        for selector in self.content_selectors:
            paragraphs = self._selector_text(response, selector)
            if paragraphs:
                return "\n".join(paragraphs)

        paragraphs = self._selector_text(response, "p")
        return "\n".join(paragraphs)

    def _selector_text(self, response, selector):
        texts = response.css(f"{selector}::text, {selector} *::text").getall()
        paragraphs = [re.sub(r"\s+", " ", text).strip() for text in texts]
        paragraphs = [text for text in paragraphs if text]
        if not paragraphs:
            return []
        if len(paragraphs) >= 2 or sum(len(text) for text in paragraphs) >= 80:
            return paragraphs
        return []

    def _download_image(self, image_url, article_url):
        try:
            slug = article_url.rstrip("/").split("/")[-1]
            slug = re.sub(r"[^\w\-]", "_", slug)
            ext = os.path.splitext(image_url.split("?")[0])[1] or ".jpg"
            filename = f"{self.name}_{slug}{ext}"
            filepath = os.path.join(IMAGE_DIR, filename)

            req = urllib.request.Request(
                image_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(filepath, "wb") as f:
                    f.write(resp.read())

            return f"/images/{filename}"
        except Exception as e:
            self.logger.warning(f"Failed to download image {image_url}: {e}")
            return ""
