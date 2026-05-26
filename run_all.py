"""
Run all three news spiders (tamilwin, virakesari, lankasri) sequentially.
Results are merged into tamilwin_scraper/news.json with duplicate removal.
After scraping, syncs all items from news.json into the PostgreSQL database.
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRAPY_CWD = PROJECT_DIR
NEWS_JSON = os.path.join(PROJECT_DIR, "news.json")
IMAGE_DIR = os.path.join(PROJECT_DIR, "image")
API_SYNC_URL = os.environ.get(
    "API_SYNC_URL",
    f"https://api-new.techorin.xyz/api/sync",
)
NEWS_JSON_BACKUP = os.path.join(PROJECT_DIR, "news.json.bak")
IMAGE_LOG_SAMPLE_LIMIT = int(os.environ.get("IMAGE_LOG_SAMPLE_LIMIT", "25"))


def _scraped_count(log):
    match = re.search(r"'item_scraped_count':\s*(\d+)", log)
    return int(match.group(1)) if match else 0


def _log_image_dir(prefix="[run_all images]"):
    exists = os.path.isdir(IMAGE_DIR)
    print(f"{prefix} IMAGE_DIR={IMAGE_DIR}")
    print(f"{prefix} exists={exists}")
    if not exists:
        return
    try:
        files = sorted(
            name
            for name in os.listdir(IMAGE_DIR)
            if os.path.isfile(os.path.join(IMAGE_DIR, name))
        )
    except OSError as e:
        print(f"{prefix} list failed: {e}")
        return
    print(f"{prefix} file_count={len(files)}")
    for name in files[:IMAGE_LOG_SAMPLE_LIMIT]:
        print(f"{prefix} file={name}")
    if len(files) > IMAGE_LOG_SAMPLE_LIMIT:
        print(f"{prefix} ... {len(files) - IMAGE_LOG_SAMPLE_LIMIT} more files")


def run_spider(name):
    print(f"\n{'=' * 60}")
    print(f"  Running spider: {name}")
    print(f"{'=' * 60}\n")
    result = subprocess.run(
        [sys.executable, "-m", "scrapy", "crawl", name],
        cwd=SCRAPY_CWD,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log = (result.stderr or "") + "\n" + (result.stdout or "")
    code = result.returncode
    scraped_count = _scraped_count(log)
    # Scrapy can exit 0 while the async crawler task crashes; detect common failures.
    if code == 0 and (
        "ModuleNotFoundError" in log
        or "exception=ModuleNotFoundError" in log
        or "Error in download handler" in log
        or "BrowserType.launch" in log
        or "Executable doesn't exist" in log
        or "playwright._impl._errors" in log
    ):
        code = 1
    if code != 0 or scraped_count == 0:
        tail = log.strip()[-3500:] if log.strip() else "(no log output)"
        print(tail)
        if code != 0:
            print(f"\n  Spider '{name}' failed (exit treated as {code}).\n")
        else:
            print(f"\n  Spider '{name}' finished but scraped 0 items.\n")
    return code, scraped_count


def main():
    # Keep a backup so a blocked/empty scrape cannot wipe the last good data file.
    if os.path.exists(NEWS_JSON):
        os.replace(NEWS_JSON, NEWS_JSON_BACKUP)
        print("Backed up existing news.json")

    spiders = ["tamilwin", "virakesari", "lankasri"]
    results = {}
    total_scraped = 0

    for spider in spiders:
        code, scraped_count = run_spider(spider)
        total_scraped += scraped_count
        results[spider] = (
            f"OK ({scraped_count} items)" if code == 0 else f"exit code {code}"
        )

    if total_scraped == 0 and os.path.exists(NEWS_JSON_BACKUP):
        if os.path.exists(NEWS_JSON):
            os.remove(NEWS_JSON)
        os.replace(NEWS_JSON_BACKUP, NEWS_JSON)
        print("Restored previous news.json because this run scraped 0 items")
    elif os.path.exists(NEWS_JSON_BACKUP):
        os.remove(NEWS_JSON_BACKUP)

    _log_image_dir()

    # Print summary
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    for spider, status in results.items():
        print(f"  {spider:15s} : {status}")

    if os.path.exists(NEWS_JSON):
        with open(NEWS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"\n  Total unique news in news.json: {len(data)}")

        sources = {}
        for item in data:
            src = item.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
        for src, count in sources.items():
            print(f"    - {src}: {count} articles")
    else:
        print("\n  news.json was not created (all spiders may have failed)")

    # Sync news.json into PostgreSQL via the API
    print(f"\n{'=' * 60}")
    print("  SYNCING TO DATABASE")
    print(f"{'=' * 60}")
    try:
        req = urllib.request.Request(
            API_SYNC_URL,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            sync_result = json.loads(resp.read().decode())
            print(f"  Total:    {sync_result.get('total', '?')}")
            print(f"  Inserted: {sync_result.get('inserted', '?')}")
            print(f"  Updated:  {sync_result.get('updated', '?')}")
            print(f"  Failed:   {sync_result.get('failed', '?')}")
    except urllib.error.URLError as e:
        print(f"  Sync skipped (API not running?): {e}")
        print(f"  Then POST {API_SYNC_URL}")

    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
