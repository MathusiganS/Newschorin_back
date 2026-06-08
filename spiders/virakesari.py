from tamilwin_scraper.spiders.base_news import BaseNewsSpider


class VirakesariSpider(BaseNewsSpider):
    name = "virakesari"
    allowed_domains = ["virakesari.lk"]
    start_url = "https://www.virakesari.lk/"
    source = "virakesari"
    listing_selectors = ('a[href*="/article/"]',)
    title_cleanup_pattern = (
        r"\s*\d{1,2}\s+\w{3},?\s*\d{4}\s*\|?\s*"
        r"\d{1,2}:\d{2}\s*(AM|PM)?\s*$"
    )
    content_selectors = (
        ".article-content p",
        ".article-body p",
        ".story-content p",
        ".single-article-content p",
        ".news-content p",
        ".content-area p",
        "article p",
        ".main-content p",
    )
