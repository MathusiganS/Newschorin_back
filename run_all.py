"""
Run all three news spiders (tamilwin, virakesari, lankasri) sequentially.
Results are merged into tamilwin_scraper/news.json with duplicate removal.
After scraping, syncs all items from news.json into the PostgreSQL database.
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRAPY_CWD = PROJECT_DIR
NEWS_JSON = os.path.join(PROJECT_DIR, "news.json")
API_SYNC_URL = os.environ.get(
    "API_SYNC_URL",
    f"http://127.0.0.1:{os.environ.get('PORT', '4000')}/api/sync",
)


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
    # Scrapy can exit 0 while the async crawler task crashes; detect common failures.
    if code == 0 and (
        "ModuleNotFoundError" in log
        or "exception=ModuleNotFoundError" in log
        or "Error in download handler" in log
    ):
        code = 1
    if code != 0:
        tail = log.strip()[-3500:] if log.strip() else "(no log output)"
        print(tail)
        print(f"\n  Spider '{name}' failed (exit treated as {code}).\n")
    return code


def main():
    # Clear existing news.json for a fresh run
    if os.path.exists(NEWS_JSON):
        os.remove(NEWS_JSON)
        print("Cleared existing news.json")

    spiders = ["tamilwin", "virakesari", "lankasri"]
    results = {}

    for spider in spiders:
        code = run_spider(spider)
        results[spider] = "OK" if code == 0 else f"exit code {code}"

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
