CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    image_path TEXT DEFAULT '',
    full_text TEXT DEFAULT '',
    original_title TEXT DEFAULT '',
    original_full_text TEXT DEFAULT '',
    source TEXT DEFAULT '',
    category_ta TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    show_in_important BOOLEAN NOT NULL DEFAULT TRUE,
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Colombo'),
    approved_at TIMESTAMP
);

ALTER TABLE news ADD COLUMN IF NOT EXISTS source TEXT DEFAULT '';
ALTER TABLE news ADD COLUMN IF NOT EXISTS category_ta TEXT DEFAULT '';
ALTER TABLE news ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE news
    ADD COLUMN IF NOT EXISTS show_in_important BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE news ADD COLUMN IF NOT EXISTS original_title TEXT DEFAULT '';
ALTER TABLE news ADD COLUMN IF NOT EXISTS original_full_text TEXT DEFAULT '';
ALTER TABLE news ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0;
ALTER TABLE news ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;
ALTER TABLE news
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP
    DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Colombo');
ALTER TABLE news
    ALTER COLUMN created_at
    SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Colombo');
UPDATE news
SET approved_at = created_at
WHERE status = 'approved' AND approved_at IS NULL;
