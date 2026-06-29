import os
import aiosqlite
from dotenv import load_dotenv

load_dotenv()
DB_PATH = "dori.db"  # Файл базы будет лежать рядом с ботом

# ============================================================
# 1. ИНИЦИАЛИЗАЦИЯ ТАБЛИЦ
# ============================================================

async def init_db():
    """Создаёт таблицы, если их нет"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                telegram_username TEXT,
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
        
        # Таблица фраз
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
        
        # Индексы для скорости
        await db.execute("CREATE INDEX IF NOT EXISTS idx_phrases_trigger ON phrases(trigger_type, mood)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_name ON users(name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(telegram_username)")
        
        await db.commit()

# ============================================================
# 2. ЗАГРУЗКА ФРАЗ ИЗ ФАЙЛОВ (при первом запуске)
# ============================================================

async def load_phrases_from_file(file_path: str):
    """Загружает фразы из txt-файла в БД, пропуская дубликаты"""
    if not os.path.exists(file_path):
        print(f"⚠️ Файл {file_path} не найден, пропускаем.")
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

                trigger = parts[0].strip()
                mood = parts[1].strip()
                text = parts[2].strip()
                emoji = parts[3].strip() if len(parts) > 3 else None

                # Проверяем дубликат
                cursor = await db.execute(
                    "SELECT 1 FROM phrases WHERE trigger_type = ? AND phrase_text = ?",
                    (trigger, text)
                )
                exists = await cursor.fetchone()
                
                if not exists:
                    await db.execute(
                        "INSERT INTO phrases (trigger_type, mood, phrase_text, emoji) VALUES (?, ?, ?, ?)",
                        (trigger, mood, text, emoji)
                    )
        await db.commit()

# ============================================================
# 3. РАБОТА С ПОЛЬЗОВАТЕЛЯМИ
# ============================================================

async def register_user(user_id: int, username: str = None):
    """Регистрирует пользователя, если его нет"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        exists = await cursor.fetchone()
        
        if not exists:
            await db.execute(
                "INSERT INTO users (user_id, is_registered, telegram_username) VALUES (?, ?, ?)",
                (user_id, 1, username)
            )
        else:
            if username:
                await db.execute(
                    "UPDATE users SET telegram_username = ? WHERE user_id = ?",
                    (username, user_id)
                )
        await db.commit()

async def get_user(user_id: int):
    """Возвращает данные пользователя или None"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            col_names = [description[0] for description in cursor.description]
            return dict(zip(col_names, row))
        return None

async def get_user_by_identifier(identifier: str) -> dict | None:
    """
    Ищет пользователя по трём вариантам:
    1. user_id (если identifier состоит только из цифр)
    2. Telegram username (с @ или без)
    3. Кастомное имя из /name (поле name в БД)
    Возвращает словарь пользователя или None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Попробуем как user_id (только цифры)
        if identifier.isdigit():
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(identifier),))
            row = await cursor.fetchone()
            if row:
                col_names = [description[0] for description in cursor.description]
                return dict(zip(col_names, row))

        # 2. Попробуем как Telegram username (без @)
        clean_username = identifier.lstrip('@').lower()
        cursor = await db.execute(
            "SELECT * FROM users WHERE LOWER(telegram_username) = ?", 
            (clean_username,)
        )
        row = await cursor.fetchone()
        if row:
            col_names = [description[0] for description in cursor.description]
            return dict(zip(col_names, row))

        # 3. Попробуем как кастомное имя (поле name)
        cursor = await db.execute("SELECT * FROM users WHERE name = ?", (identifier,))
        row = await cursor.fetchone()
        if row:
            col_names = [description[0] for description in cursor.description]
            return dict(zip(col_names, row))

        return None

async def update_user_name(user_id: int, new_name: str):
    """Обновляет имя, если оно уникально"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE name = ?", (new_name,))
        exists = await cursor.fetchone()
        if exists:
            return False
        
        await db.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))
        await db.commit()
        return True

async def update_last_message(user_id: int):
    """Обновляет время последнего сообщения"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_message = datetime('now') WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()

async def add_coins(user_id: int, amount: float):
    """Добавляет или забирает коины (отрицательное значение — забирает)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def set_shield(user_id: int, hours: int):
    """Устанавливает щит на N часов (или навсегда, если -1)"""
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
    """Обновляет стрик и рекорд"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?",
            (new_streak, new_record, user_id)
        )
        await db.commit()

async def increment_streak(user_id: int):
    """Увеличивает стрик на 1 и обновляет рекорд"""
    async with aiosqlite.connect(DB_PATH) as db:
        user = await get_user(user_id)
        if user:
            new_streak = user['streak'] + 1
            new_record = max(new_streak, user['streak_record'])
            await db.execute(
                "UPDATE users SET streak = ?, streak_record = ? WHERE user_id = ?",
                (new_streak, new_record, user_id)
            )
            await db.commit()
            return new_streak
        return 0

# ============================================================
# 4. РАБОТА С ФРАЗАМИ (с поддержкой OFFSET для пагинации)
# ============================================================

async def get_phrases_by_trigger(trigger: str, limit: int = 20, offset: int = 0):
    """Возвращает список фраз для указанного триггера с пагинацией"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, phrase_text, mood, emoji, usage_count
            FROM phrases
            WHERE trigger_type = ? AND is_active = 1
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            (trigger, limit, offset)
        )
        rows = await cursor.fetchall()
        col_names = [description[0] for description in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

async def add_phrase(trigger: str, mood: str, text: str, emoji: str = None):
    """Добавляет новую фразу в БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO phrases (trigger_type, mood, phrase_text, emoji) VALUES (?, ?, ?, ?)",
            (trigger, mood, text, emoji)
        )
        await db.commit()

async def delete_phrase(phrase_id: int):
    """Мягко удаляет фразу (деактивирует)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE phrases SET is_active = 0 WHERE id = ?", (phrase_id,)
        )
        await db.commit()

async def get_rank_phrase_by_name(rank_name: str) -> str | None:
    """
    Ищет поздравление для указанного ранга в таблице phrases.
    В ranksms.txt фразы записываются как: 'RANK|Название_ранга|Текст|эмодзи'
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT phrase_text, emoji FROM phrases WHERE trigger_type = 'RANK' AND mood = ? AND is_active = 1 LIMIT 1",
            (rank_name,)
        )
        row = await cursor.fetchone()
        if row:
            text, emoji = row
            return f"{text} {emoji or ''}".strip()
        return None

# ============================================================
# 5. ПЛАНИРОВЩИК (проверка бездействия)
# ============================================================

async def get_inactive_users():
    """Возвращает пользователей, которые не писали > 24 часов и не имеют щита"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT user_id, name, telegram_username, last_message, shield_until
            FROM users
            WHERE is_registered = 1
              AND (shield_until IS NULL OR shield_until < datetime('now'))
              AND last_message < datetime('now', '-24 hours')
            """
        )
        rows = await cursor.fetchall()
        col_names = [description[0] for description in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

# ============================================================
# 6. ИНИЦИАЛИЗАЦИЯ ПРИ СТАРТЕ
# ============================================================

async def initialize_database():
    """Инициализирует БД и загружает фразы из файлов"""
    await init_db()
    await load_phrases_from_file("Content/phrases.txt")
    await load_phrases_from_file("Content/ranksms.txt")
    print("✅ SQLite база готова (файл dori.db)")

async def get_total_phrases_count(trigger: str) -> int:
    """Возвращает общее количество активных фраз для указанного триггера"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM phrases WHERE trigger_type = ? AND is_active = 1",
            (trigger,)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0
