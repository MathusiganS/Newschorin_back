from spiders.base_news import BaseNewsSpider


class LankasriSpider(BaseNewsSpider):
    name = "lankasri"
    allowed_domains = ["lankasri.com", "news.lankasri.com"]
    start_url = "https://news.lankasri.com/news/srilanka"
    source = "lankasri"
    listing_selectors = ("h4 a", "h3 a", ".news-item a", ".article-card a")
    title_cleanup_pattern = r"\s*(Srilanka|World|India|Sports|Cinema)\s*\d+.*$"
    title_suffixes = (
        " - Lankasri News",
        " - Lankasri",
    )
    content_selectors = (
        ".ds-content p",
        ".article-content p",
        ".article-body p",
        ".story-content p",
        ".news-content p",
        "article p",
        ".main-content p",
    )
