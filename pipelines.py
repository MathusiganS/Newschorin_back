import json
import os

from tamilwin_scraper.classifier import (
    classify_article_for_pipeline,
    diagnose_classifier,
)


class SaveNewsPipeline:

    def open_spider(self, spider):
        self.output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "news.json"
        )
        self.new_items = []

        # Load existing data so we can merge across spider runs
        self.existing_data = []
        if os.path.exists(self.output_path):
            try:
                with open(self.output_path, "r", encoding="utf-8") as f:
                    self.existing_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.existing_data = []

        info = diagnose_classifier()
        if not info["classifier_path"]:
            spider.logger.warning(
                "Tamil categories: NO classifier pickle found. %s | "
                "Copy tamil_news_classifier.pkl (+ label_encoder.pkl) into "
                "tamilwin_scraper/models/ or set TAMILNEWS_MODEL_DIR. "
                "Optional: TAMILNEWS_KEYWORD_FALLBACK=1 for rule-based labels. "
                "Searched: %s",
                info.get("load_error") or "",
                info.get("searched_roots"),
            )
        elif not info.get("label_encoder_path"):
            spider.logger.info(
                "Tamil classifier loaded from %s (no separate label_encoder; "
                "numeric outputs will map to fixed Tamil names).",
                info["classifier_path"],
            )

    def process_item(self, item, spider):
        row = dict(item)
        ft = row.get("full_text", "") or ""
        row["category_ta"] = classify_article_for_pipeline(ft, row.get("title") or "")
        item["category_ta"] = row["category_ta"]
        self.new_items.append(dict(item))

        return item

    def close_spider(self, spider):
        # Merge existing + new items, deduplicate by URL
        all_items = self.existing_data + self.new_items
        seen_urls = set()
        unique_items = []
        for item in all_items:
            url = item.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_items.append(item)

        for item in unique_items:
            ft = (item.get("full_text") or "").strip()
            if ft:
                item["category_ta"] = classify_article_for_pipeline(
                    ft, item.get("title") or ""
                )
            else:
                item["category_ta"] = item.get("category_ta") or ""

        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(unique_items, f, ensure_ascii=False, indent=4)

        spider.logger.info(
            f"Saved {len(unique_items)} unique items to news.json "
            f"({len(self.new_items)} new from {spider.name})"
        )
