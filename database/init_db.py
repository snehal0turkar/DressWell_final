import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'instance', 'dresswell.db')
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

conn = sqlite3.connect(DB_PATH)
c    = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    gender        TEXT DEFAULT 'prefer_not_to_say',
    city          TEXT,
    skin_tone     TEXT DEFAULT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

c.execute("""CREATE TABLE IF NOT EXISTS clothing_items (
    item_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    name          TEXT NOT NULL,
    wear_type     TEXT NOT NULL DEFAULT 'top',
    category      TEXT,
    image_path    TEXT,
    color_rgb     TEXT,
    color_palette TEXT,
    occasions     TEXT,
    temp_min      INTEGER,
    temp_max      INTEGER,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS outfit_feedback (
    feedback_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER,
    top_id        INTEGER,
    bottom_id     INTEGER,
    item_ids      TEXT,
    feedback_type TEXT,
    harmony_type  TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

c.execute("""CREATE TABLE IF NOT EXISTS favourite_outfits (
    favourite_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER,
    top_id       INTEGER,
    bottom_id    INTEGER,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, top_id, bottom_id)
)""")

c.execute("""CREATE TABLE IF NOT EXISTS saved_outfits (
    outfit_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER,
    items      TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

# Migrations for existing databases
for sql in [
    "ALTER TABLE users ADD COLUMN skin_tone TEXT DEFAULT NULL",
    "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT 'prefer_not_to_say'",
    "ALTER TABLE clothing_items ADD COLUMN wear_type TEXT DEFAULT 'top'",
    "ALTER TABLE clothing_items ADD COLUMN image_path TEXT",
    "ALTER TABLE clothing_items ADD COLUMN color_palette TEXT",
    "ALTER TABLE outfit_feedback ADD COLUMN top_id INTEGER",
    "ALTER TABLE outfit_feedback ADD COLUMN bottom_id INTEGER",
    "ALTER TABLE outfit_feedback ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
]:
    try:
        c.execute(sql)
    except Exception:
        pass

conn.commit()
conn.close()
print("DressWell DB initialized!")
