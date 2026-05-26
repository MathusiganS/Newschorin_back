"""
Run from the repository root or from tamilwin_scraper/:

  python -m tamilwin_scraper.diagnose_classification

Shows classifier paths, load errors, and a sample prediction from news.json.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo not in sys.path:
        sys.path.insert(0, repo)

    from tamilwin_scraper.classifier import (
        classify_article_for_pipeline,
        diagnose_classifier,
    )

    info = diagnose_classifier()
    print("=== Tamil classifier diagnose ===")
    for k, v in info.items():
        print(f"  {k}: {v}")

    news_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "news.json"
    )
    if os.path.isfile(news_path):
        with open(news_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and data:
            ft = (data[0].get("full_text") or "")[:500]
            cat = classify_article_for_pipeline(ft)
            print("\n=== Sample (first article, truncated text) ===")
            print(f"  category_ta: {cat!r}")
    else:
        print(f"\n(no {news_path})")

    print(
        "\nTip: without .pkl files, set TAMILNEWS_KEYWORD_FALLBACK=1 for "
        "rule-based Tamil categories (approximate)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
