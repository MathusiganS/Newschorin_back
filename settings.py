import os
import sys

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

# Scrapy settings

PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

BOT_NAME = "news_scraper"

SPIDER_MODULES = ["spiders"]
NEWSPIDER_MODULE = "spiders"


# Identify yourself responsibly
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


# Respect robots.txt
ROBOTSTXT_OBEY = False


# Maximum concurrent requests
CONCURRENT_REQUESTS = 8


# Delay between requests (avoid blocking)
DOWNLOAD_DELAY = 2


# Disable cookies (not needed for scraping)
COOKIES_ENABLED = False


# Playwright download handler for dynamic pages
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}


# Enable pipelines
ITEM_PIPELINES = {
    "pipelines.SaveNewsPipeline": 300,
}


# Enable AutoThrottle (helps prevent bans)
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0


# Enable retry for failed requests
RETRY_ENABLED = True
RETRY_TIMES = 3


# Logging level
LOG_LEVEL = "INFO"
