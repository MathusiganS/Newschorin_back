import json
import os

import psycopg2


DB_URL = "postgresql://postgres:12345@localhost:5432/news_corin"


class SaveNewsPipeline:

    def open_spider(self, spider):
        # Still write news.json as backup
        output_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "news.json"
        )
        self.file = open(output_path, "w", encoding="utf-8")
        self.data = []

        # Connect to PostgreSQL
        self.conn = psycopg2.connect(DB_URL)
        self.cur = self.conn.cursor()

        # Create table if it doesn't exist
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                image_path TEXT DEFAULT '',
                full_text TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        self.conn.commit()

    def process_item(self, item, spider):
        self.data.append(dict(item))

        # Upsert into PostgreSQL (skip if url already exists)
        try:
            self.cur.execute(
                """
                INSERT INTO news (title, url, image_path, full_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    title = EXCLUDED.title,
                    image_path = EXCLUDED.image_path,
                    full_text = EXCLUDED.full_text
                """,
                (item["title"], item["url"], item.get("image_path", ""), item.get("full_text", "")),
            )
            self.conn.commit()
        except Exception as e:
            spider.logger.warning(f"DB insert error: {e}")
            self.conn.rollback()

        return item

    def close_spider(self, spider):
        json.dump(self.data, self.file, ensure_ascii=False, indent=4)
        self.file.close()

        # Close DB connection
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
