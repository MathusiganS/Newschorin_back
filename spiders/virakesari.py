import json
import os
import re
import urllib.request

import scrapy

from tamilwin_scraper.spiders.date_utils import extract_published_at

IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image")


class VirakesariSpider(scrapy.Spider):
    name = "virakesari"
    allowed_domains = ["virakesari.lk"]

    def start_requests(self):
        os.makedirs(IMAGE_DIR, exist_ok=True)

        yield scrapy.Request(
            url="https://www.virakesari.lk/",
            meta={
                "playwright": True,
                "playwright_include_page": False,
                "playwright_page_goto_kwargs": {
                    "wait_until": "domcontentloaded",
                    "timeout": 60000,
                },
            },
        )

    def parse(self, response):
        seen_urls = set()
        count = 0

        for link_el in response.css('a[href*="/article/"]'):
            href = link_el.attrib.get("href", "")
            if not href:
                continue

            url = response.urljoin(href)

            if url in seen_urls:
                continue
            seen_urls.add(url)

            title = link_el.css("::text").get("").strip()
            if not title or len(title) < 5:
                title = " ".join(
                    t.strip()
                    for t in link_el.xpath(".//text()").getall()
                    if t.strip()
                )

            if not title or len(title) < 5:
                continue

            # Strip trailing date/time like "06 Apr, 2026 | 12:11 PM"
            title = re.sub(
                r'\s*\d{1,2}\s+\w{3},?\s*\d{4}\s*\|?\s*\d{1,2}:\d{2}\s*(AM|PM)?\s*$',
                '', title, flags=re.IGNORECASE
            ).strip()

            count += 1
            if count > 10:
                break

            yield scrapy.Request(
                url=url,
                callback=self.parse_article,
                meta={
                    "playwright": True,
                    "playwright_include_page": False,
                    "playwright_page_goto_kwargs": {
                        "wait_until": "domcontentloaded",
                        "timeout": 60000,
                    },
                    "title": title,
                },
            )

    def parse_article(self, response):
        title = response.meta["title"]

        og_title = response.css('meta[property="og:title"]::attr(content)').get("")
        if og_title and len(og_title) > len(title):
            title = og_title.split("|")[0].strip()

        # Extract image from og:image or JSON-LD
        image_url = response.css('meta[property="og:image"]::attr(content)').get("")

        if not image_url:
            ld_json = response.css('script[type="application/ld+json"]::text').getall()
            for block in ld_json:
                try:
                    data = json.loads(block)
                    if isinstance(data, dict):
                        img = data.get("image", "")
                        if isinstance(img, list) and img:
                            image_url = img[0] if isinstance(img[0], str) else img[0].get("url", "")
                        elif isinstance(img, str):
                            image_url = img
                        if image_url:
                            break
                except (json.JSONDecodeError, TypeError):
                    continue

        # Extract full article text with multiple fallback selectors
        content_selectors = [
            ".article-content p",
            ".article-body p",
            ".story-content p",
            ".single-article-content p",
            ".news-content p",
            ".content-area p",
            "article p",
            ".main-content p",
        ]

        paragraphs = []
        for selector in content_selectors:
            texts = response.css(f"{selector}::text, {selector} *::text").getall()
            if texts and len(texts) > 2:
                paragraphs = texts
                break

        if not paragraphs:
            paragraphs = response.css("p::text, p *::text").getall()

        full_text = "\n".join(p.strip() for p in paragraphs if p.strip())

        yield {
            "title": title,
            "url": response.url,
            "image_path": image_url,
            "full_text": full_text,
            "source": "virakesari",
            "created_at": extract_published_at(response),
        }

    def _download_image(self, image_url, article_url):
        try:
            slug = article_url.rstrip("/").split("/")[-1]
            slug = re.sub(r'[^\w\-]', '_', slug)
            ext = os.path.splitext(image_url.split("?")[0])[1] or ".jpg"
            filename = f"virakesari_{slug}{ext}"
            filepath = os.path.join(IMAGE_DIR, filename)

            req = urllib.request.Request(image_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(filepath, "wb") as f:
                    f.write(resp.read())

            return f"/images/{filename}"
        except Exception as e:
            self.logger.warning(f"Failed to download image {image_url}: {e}")
            return ""
