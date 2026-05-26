import json
import os

import psycopg2

from tamilwin_scraper.classifier import (
    classify_article_for_pipeline,
    diagnose_classifier,
)


DB_URL = "postgresql://postgres:12345@localhost:5432/news_techorin"


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

        # Connect to PostgreSQL (graceful fallback if unavailable)
        self.db_available = False
        self.conn = None
        self.cur = None
        try:
            self.conn = psycopg2.connect(DB_URL)
            self.cur = self.conn.cursor()
            self.cur.execute("""
                CREATE TABLE IF NOT EXISTS news (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    image_path TEXT DEFAULT '',
                    full_text TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    category_ta TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            for stmt in (
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS source TEXT DEFAULT ''",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS category_ta TEXT DEFAULT ''",
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'",
            ):
                try:
                    self.cur.execute(stmt)
                except Exception:
                    pass
            self.conn.commit()
            self.db_available = True
        except Exception as e:
            spider.logger.warning(f"DB connection failed (continuing without DB): {e}")

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

        if self.db_available:
            try:
                self.cur.execute(
                    """
                    INSERT INTO news (title, url, image_path, full_text, source, category_ta, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO UPDATE SET
                        title = EXCLUDED.title,
                        image_path = EXCLUDED.image_path,
                        full_text = EXCLUDED.full_text,
                        source = EXCLUDED.source,
                        category_ta = EXCLUDED.category_ta,
                        status = news.status
                    """,
                    (
                        row["title"],
                        row["url"],
                        row.get("image_path", ""),
                        row.get("full_text", ""),
                        row.get("source", spider.name),
                        row.get("category_ta", ""),
                        "pending",
                    ),
                )
                self.conn.commit()
            except Exception as e:
                spider.logger.warning(f"DB insert error: {e}")
                self.conn.rollback()

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

        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
