# Scrapy settings for tamilwin_scraper project

BOT_NAME = "tamilwin_scraper"

SPIDER_MODULES = ["tamilwin_scraper.spiders"]
NEWSPIDER_MODULE = "tamilwin_scraper.spiders"


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
    "tamilwin_scraper.pipelines.SaveNewsPipeline": 300,
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
