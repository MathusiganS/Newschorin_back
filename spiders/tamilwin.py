from spiders.base_news import BaseNewsSpider


class TamilwinSpider(BaseNewsSpider):
    name = "tamilwin"
    allowed_domains = ["tamilwin.com"]
    start_url = "https://tamilwin.com/srilanka"
    source = "tamilwin"
    listing_selectors = ("h4 a",)
    content_selectors = (".ds-content p",)
