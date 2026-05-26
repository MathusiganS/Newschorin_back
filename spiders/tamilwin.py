import json
import os
import re
import urllib.request

import scrapy

# Directory to save downloaded images
IMAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image")


class TamilwinSpider(scrapy.Spider):
    name = "tamilwin"
    allowed_domains = ["tamilwin.com"]

    def start_requests(self):
        # Ensure image directory exists
        os.makedirs(IMAGE_DIR, exist_ok=True)

        yield scrapy.Request(
            url="https://tamilwin.com/srilanka",
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
        articles = response.css("h4 a")
        count = 0

        for article in articles:
            title = article.css("::text").get()
            link = article.attrib.get("href", "")

            if not title or not link:
                continue

            url = response.urljoin(link)

            if "/article/" not in url:
                continue

            count += 1
            if count > 10:
                break

            # Follow each article link to get full content
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
                    "title": title.strip(),
                },
            )

    def parse_article(self, response):
        title = response.meta["title"]

        # Extract image URL from JSON-LD schema (cleanest source)
        image_url = ""
        ld_json = response.css('script[type="application/ld+json"]::text').getall()
        for block in ld_json:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and data.get("image"):
                    image_url = data["image"]
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: get first image inside .ds-content
        if not image_url:
            image_url = response.css(".ds-content img::attr(src)").get("")

        # Extract full article text from .ds-content paragraphs
        paragraphs = response.css(".ds-content p::text, .ds-content p *::text").getall()
        full_text = "\n".join(p.strip() for p in paragraphs if p.strip())

        # Download the image locally
        image_path = ""
        if image_url:
            image_path = self._download_image(image_url, response.url)

        yield {
            "title": title,
            "url": response.url,
            "image_path": image_path,
            "full_text": full_text,
            "source": "tamilwin",
        }

    def _download_image(self, image_url, article_url):
        """Download image to tamilwin_scraper/image/ and return the local path."""
        try:
            # Build filename from article slug
            slug = article_url.rstrip("/").split("/")[-1]
            # Clean slug for filename
            slug = re.sub(r'[^\w\-]', '_', slug)
            # Get file extension from URL
            ext = os.path.splitext(image_url.split("?")[0])[1] or ".webp"
            filename = f"{slug}{ext}"
            filepath = os.path.join(IMAGE_DIR, filename)

            req = urllib.request.Request(image_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(filepath, "wb") as f:
                    f.write(resp.read())

            return filepath
        except Exception as e:
            self.logger.warning(f"Failed to download image {image_url}: {e}")
            return ""
