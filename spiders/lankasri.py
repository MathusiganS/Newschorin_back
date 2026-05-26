import json
import os
import re
import urllib.request

import scrapy

IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image")


class LankasriSpider(scrapy.Spider):
    name = "lankasri"
    allowed_domains = ["lankasri.com", "news.lankasri.com"]

    def start_requests(self):
        os.makedirs(IMAGE_DIR, exist_ok=True)

        yield scrapy.Request(
            url="https://news.lankasri.com/news/srilanka",
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

        for link_el in response.css("h4 a, h3 a, .news-item a, .article-card a"):
            href = link_el.attrib.get("href", "")
            if not href:
                continue

            url = response.urljoin(href)

            if "lankasri.com" not in url:
                continue
            if url in seen_urls:
                continue
            # Only follow actual article pages (must have /article/ in URL)
            if "/article/" not in url:
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

            # Clean trailing category/time text like "Srilanka 2 நாட்கள் முன்"
            title = re.sub(r'\s*(Srilanka|World|India|Sports|Cinema)\s*\d+.*$', '', title).strip()

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

        # Clean common suffixes
        for suffix in [" - லங்காசிறி நியூஸ்", " - Lankasri News", " - Lankasri"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()

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

        if not image_url:
            image_url = response.css(".ds-content img::attr(src), .article-image img::attr(src)").get("")

        # Extract full article text with multiple fallback selectors
        content_selectors = [
            ".ds-content p",
            ".article-content p",
            ".article-body p",
            ".story-content p",
            ".news-content p",
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
            "source": "lankasri",
        }

    def _download_image(self, image_url, article_url):
        try:
            slug = article_url.rstrip("/").split("/")[-1]
            slug = re.sub(r'[^\w\-]', '_', slug)
            ext = os.path.splitext(image_url.split("?")[0])[1] or ".jpg"
            filename = f"lankasri_{slug}{ext}"
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
