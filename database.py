import os
import aiosqlite
from dotenv import load_dotenv

load_dotenv()
DB_PATH = "dori.db"  # Файл базы будет лежать рядом с ботом

# ============================================================
# 1. ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ
# ============================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                rank TEXT DEFAULT 'Новичок',
                streak INTEGER DEFAULT 0,
                streak_record INTEGER DEFAULT 0,
                coins REAL DEFAULT 0,
                shield_until TEXT,
                last_message TEXT,
                is_registered INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS phrases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_type TEXT NOT NULL,
                mood TEXT NOT NULL,
                phrase_text TEXT NOT NULL,
                emoji TEXT,
                is_active INTEGER DEFAULT 1,
                usage_count INTEGER DEFAULT 0,
                last_used TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def load_phrases_from_file(file_path: str):
    if not os.path.exists(file_path):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                if len(parts) < 3:
                    continue
                trigger, mood, text = parts[0], parts[1], parts[2]
                emoji = parts[3] if len(parts) > 3 else None
                
                # Проверяем дубликат
                exists = await db.execute_fetchall(
                    "SELECT 1 FROM phrases WHERE trigger_type = ? AND phrase_text = ?",
                    (trigger, text)
                )
                if not exists:
                    await db.execute(
                        "INSERT INTO phrases (trigger_type, mood, phrase_text, emoji) VALUES (?, ?, ?, ?)",
                        (trigger, mood, text, emoji)
                    )
        await db.commit()

# ============================================================
# 2. РАБОТА С ПОЛЬЗОВАТЕЛЯМИ
# ============================================================

async def register_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, is_registered) VALUES (?, ?)",
            (user_id, 1)
        )
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchall(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        return dict(row[0]) if row else None

async def update_user_name(user_id: int, new_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        exists = await db.execute_fetchall(
            "SELECT user_id FROM users WHERE name = ?", (new_name,)
        )
        if exists:
            return False
        await db.execute(
            "UPDATE users SET name = ? WHERE user_id = ?",
            (new_name, user_id)
        )
        await db.commit()
        return True

async def update_last_message(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_message = datetime('now') WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()

async def add_coins(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def set_shield(user_id: int, hours: int):
    async with aiosqlite.connect(DB_PATH) as db:
        if hours == -1:
            await db.execute(
                "UPDATE users SET shield_until = '9999-12-31 23:59:59' WHERE user_id = ?",
                (user_id,)
            )
        else:
            await db.execute(
                "UPDATE users SET shield_until = datetime('now', '+' || ? || ' hours') WHERE user_id = ?",
                (hours, user_id)
            )
        await db.commit()

async def update_streak(user_id: int, new_streak: int, new_record: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?",
            (new_streak, new_record, user_id)
        )
        await db.commit()

# ============================================================
# 3. РАБОТА С ФРАЗАМИ
# ============================================================

async def get_phrases_by_trigger(trigger: str, limit: int = 20):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            """
            SELECT id, phrase_text, mood, emoji, usage_count
            FROM phrases
            WHERE trigger_type = ? AND is_active = 1
            ORDER BY id
            LIMIT ?
            """,
            (trigger, limit)
        )
        return [dict(row) for row in rows]

async def add_phrase(trigger: str, mood: str, text: str, emoji: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO phrases (trigger_type, mood, phrase_text, emoji) VALUES (?, ?, ?, ?)",
            (trigger, mood, text, emoji)
        )
        await db.commit()

async def delete_phrase(phrase_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE phrases SET is_active = 0 WHERE id = ?", (phrase_id,)
        )
        await db.commit()

# ============================================================
# 4. ПЛАНИРОВЩИК (бездействие)
# ============================================================

async def get_inactive_users():
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            """
            SELECT user_id, name, last_message, shield_until
            FROM users
            WHERE is_registered = 1
              AND (shield_until IS NULL OR shield_until < datetime('now'))
              AND last_message < datetime('now', '-24 hours')
            """
        )
        return [dict(row) for row in rows]

# ============================================================
# 5. ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ
# ============================================================

async def initialize_database():
    await init_db()
    await load_phrases_from_file("Content/phrases.txt")
    await load_phrases_from_file("Content/ranksms.txt")
    print("✅ SQLite база готова (файл dori.db)")
