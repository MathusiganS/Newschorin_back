from spiders.base_news import BaseNewsSpider


class NewswireSpider(BaseNewsSpider):
    name = "newswire"
    allowed_domains = ["newswire.lk", "www.newswire.lk"]
    start_url = "https://www.newswire.lk/"
    source = "newswire"
    use_playwright = False
    listing_selectors = ("h4 a",)
    article_url_marker = None
    article_url_pattern = r"/20\d{2}/\d{2}/\d{2}/[^/]+/?$"
    title_suffixes = (" - Newswire",)
    content_selectors = (
        ".entry-content p",
        "article p",
        ".post-content p",
        ".td-post-content p",
    )
