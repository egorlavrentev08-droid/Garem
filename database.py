import os
import aiosqlite
from datetime import datetime, timedelta
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
                shield_count INTEGER DEFAULT 0,
                last_message TEXT,
                is_registered INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                messages_today INTEGER DEFAULT 0,
                last_message_date TEXT,
                redemption_active INTEGER DEFAULT 0,
                redemption_target INTEGER DEFAULT 200,
                redemption_progress INTEGER DEFAULT 0,
                redemption_streak_to_restore INTEGER DEFAULT 0,
                redemption_expires_at TEXT
            )
        """)
        
        # Таблица фраз (больше не используется для хранения, но оставляем для совместимости)
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                source_message_id INTEGER
            )
        """)
        
        # Таблица истории наград
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rewards_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                reward_type TEXT,
                position INTEGER,
                coins INTEGER,
                streak INTEGER,
                awarded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Индексы для скорости
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_name ON users(name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(telegram_username)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_streak ON users(streak)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_messages_today ON users(messages_today)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_last_message ON users(last_message)")
        
        # Добавляем поле shield_count, если его нет (для существующей БД)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN shield_count INTEGER DEFAULT 0")
        except:
            pass  # Поле уже существует
        
        # Добавляем поле source_message_id, если его нет
        try:
            await db.execute("ALTER TABLE phrases ADD COLUMN source_message_id INTEGER")
        except:
            pass  # Поле уже существует
        
        await db.commit()

# ============================================================
# 2. РАБОТА С ПОЛЬЗОВАТЕЛЯМИ
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

# ============================================================
# 3. КОИНЫ
# ============================================================

async def add_coins(user_id: int, amount: float):
    """Добавляет или забирает коины (отрицательное значение — забирает)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

# ============================================================
# 4. ЩИТЫ
# ============================================================

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

async def add_shield(user_id: int, count: int = 1):
    """Добавляет щиты пользователю"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET shield_count = shield_count + ? WHERE user_id = ?",
            (count, user_id)
        )
        await db.commit()

async def use_shield(user_id: int) -> bool:
    """Использует один щит, возвращает True если успешно"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT shield_count FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0] > 0:
            await db.execute(
                "UPDATE users SET shield_count = shield_count - 1 WHERE user_id = ?",
                (user_id,)
            )
            await db.commit()
            return True
        return False

async def get_shield_count(user_id: int) -> int:
    """Возвращает количество щитов"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT shield_count FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

# ============================================================
# 5. СТРИКИ
# ============================================================

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

async def increment_messages_today(user_id: int):
    """Увеличивает счётчик сообщений за сегодня"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET messages_today = messages_today + 1,
                last_message_date = datetime('now')
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()

# ============================================================
# 6. ФРАЗЫ (только для совместимости, основное хранение в кеше)
# ============================================================

async def get_phrases_by_trigger(trigger: str, limit: int = 20, offset: int = 0, mood: str = None):
    """Возвращает список фраз для указанного триггера (из БД, для обратной совместимости)"""
    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT id, phrase_text, mood, emoji, usage_count
            FROM phrases
            WHERE trigger_type = ? AND is_active = 1
        """
        params = [trigger]
        
        if mood:
            query += " AND mood = ?"
            params.append(mood)
        
        query += " ORDER BY id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        col_names = [description[0] for description in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

async def add_phrase(trigger: str, mood: str, text: str, emoji: str = None, source_message_id: int = None):
    """Добавляет новую фразу в БД (для обратной совместимости)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO phrases (trigger_type, mood, phrase_text, emoji, source_message_id) VALUES (?, ?, ?, ?, ?)",
            (trigger, mood, text, emoji, source_message_id)
        )
        await db.commit()

async def delete_phrase(phrase_id: int):
    """Мягко удаляет фразу (деактивирует)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE phrases SET is_active = 0 WHERE id = ?", (phrase_id,)
        )
        await db.commit()

async def get_total_phrases_count(trigger: str) -> int:
    """Возвращает общее количество активных фраз для указанного триггера"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM phrases WHERE trigger_type = ? AND is_active = 1",
            (trigger,)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0

# ============================================================
# 7. ТОПЫ
# ============================================================

async def get_top_streak(limit: int = 15):
    """Возвращает топ-15 по стрику"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, name, streak, streak_record, telegram_username
            FROM users 
            WHERE is_registered = 1 AND streak > 0
            ORDER BY streak DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        col_names = [description[0] for description in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

async def get_top_messages_today(limit: int = 15):
    """Возвращает топ-15 по сообщениям за сегодня"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, name, messages_today, telegram_username
            FROM users 
            WHERE is_registered = 1 AND messages_today > 0
            ORDER BY messages_today DESC
            LIMIT ?
        """, (limit,))
        rows = await cursor.fetchall()
        col_names = [description[0] for description in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

async def reset_daily_messages():
    """Сбрасывает счётчик сообщений в 00:00"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET messages_today = 0")
        await db.commit()

# ============================================================
# 8. НАГРАДЫ
# ============================================================

async def add_reward_history(user_id: int, reward_type: str, position: int, coins: int, streak: int = 0):
    """Записывает историю наград"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO rewards_history (user_id, reward_type, position, coins, streak)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, reward_type, position, coins, streak))
        await db.commit()

async def award_daily_top():
    """Награждает первого места в ежедневном топе"""
    top = await get_top_messages_today(1)
    if top and top[0]['messages_today'] > 0:
        user = top[0]
        await add_coins(user['user_id'], 100)
        await add_reward_history(user['user_id'], 'daily_top', 1, 100)
        return user
    return None

async def award_weekly_top():
    """Награждает топ-3 по стрику за неделю"""
    top = await get_top_streak(3)
    rewards = [(10000, 1), (5000, 2), (1000, 3)]
    
    awarded = []
    for i, (coins, position) in enumerate(rewards):
        if i < len(top) and top[i]['streak'] > 0:
            user = top[i]
            await add_coins(user['user_id'], coins)
            await add_reward_history(user['user_id'], 'weekly_top', position, coins, user['streak'])
            awarded.append((user, position, coins))
    
    return awarded

# ============================================================
# 9. ИСКУПЛЕНИЕ СТРИКА
# ============================================================

async def start_redemption(user_id: int, lost_streak: int):
    """Активирует процесс искупления для пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        expires_at = datetime.now() + timedelta(hours=24)
        await db.execute("""
            UPDATE users 
            SET redemption_active = 1,
                redemption_target = 200,
                redemption_progress = 0,
                redemption_streak_to_restore = ?,
                redemption_expires_at = ?
            WHERE user_id = ?
        """, (lost_streak, expires_at.isoformat(), user_id))
        await db.commit()

async def update_redemption_progress(user_id: int, increment: int = 1):
    """Увеличивает прогресс искупления"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET redemption_progress = redemption_progress + ?
            WHERE user_id = ? AND redemption_active = 1
        """, (increment, user_id))
        await db.commit()

async def get_redemption_status(user_id: int) -> dict | None:
    """Возвращает статус искупления"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT redemption_active, redemption_target, redemption_progress, 
                   redemption_streak_to_restore, redemption_expires_at
            FROM users 
            WHERE user_id = ?
        """, (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'active': row[0],
                'target': row[1],
                'progress': row[2],
                'streak_to_restore': row[3],
                'expires_at': row[4]
            }
        return None

async def complete_redemption(user_id: int):
    """Завершает искупление успешно - восстанавливает стрик"""
    user = await get_user(user_id)
    if not user:
        return
    
    streak_to_restore = user.get('redemption_streak_to_restore', 0)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET streak = ?,
                redemption_active = 0,
                redemption_progress = 0,
                redemption_target = 0,
                redemption_streak_to_restore = 0,
                redemption_expires_at = NULL
            WHERE user_id = ?
        """, (streak_to_restore, user_id))
        await db.commit()

async def fail_redemption(user_id: int):
    """Искупление провалено - отключаем возможность"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users 
            SET redemption_active = 0,
                redemption_progress = 0,
                redemption_target = 0,
                redemption_streak_to_restore = 0,
                redemption_expires_at = NULL
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()

async def check_expired_redemptions():
    """Проверяет и отключает просроченные искупления"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id FROM users 
            WHERE redemption_active = 1 
              AND redemption_expires_at < datetime('now')
        """)
        expired = await cursor.fetchall()
        
        for row in expired:
            await fail_redemption(row[0])
        
        return [row[0] for row in expired]

# ============================================================
# 10. ПЛАНИРОВЩИК (проверка бездействия)
# ============================================================

async def get_inactive_users():
    """Возвращает пользователей, которые не писали > 24 часов и не имеют щита"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, name, telegram_username, last_message, shield_until, streak
            FROM users
            WHERE is_registered = 1
              AND (shield_until IS NULL OR shield_until < datetime('now'))
              AND last_message < datetime('now', '-24 hours')
        """)
        rows = await cursor.fetchall()
        col_names = [description[0] for description in cursor.description]
        return [dict(zip(col_names, row)) for row in rows]

# ============================================================
# 11. ИНИЦИАЛИЗАЦИЯ
# ============================================================

async def initialize_database():
    """Инициализирует БД"""
    await init_db()
    print("✅ SQLite база готова (файл dori.db)")

# ============================================================
# 12. СИНХРОНИЗАЦИЯ (для обратной совместимости)
# ============================================================

async def sync_phrases_to_file():
    """Сохраняет все активные фразы из БД в Content/phrases.txt"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT trigger_type, mood, phrase_text, emoji FROM phrases WHERE is_active = 1 ORDER BY id"
        )
        rows = await cursor.fetchall()
    
    file_path = "Content/phrases.txt"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# ==============================\n")
        f.write("# Фразы (автоматически сгенерировано ботом)\n")
        f.write("# ==============================\n\n")
        
        current_trigger = None
        for row in rows:
            trigger, mood, text, emoji = row
            emoji_str = f"|{emoji}" if emoji else ""
            
            if trigger != current_trigger:
                current_trigger = trigger
                f.write(f"\n# ==============================\n")
                f.write(f"# ТРИГГЕР: {trigger}\n")
                f.write(f"# ==============================\n\n")
            
            f.write(f"{trigger}|{mood}|{text}{emoji_str}\n")

async def sync_ranks_to_file():
    """Сохраняет все активные ранговые фразы из БД в Content/ranksms.txt"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT mood, phrase_text, emoji FROM phrases WHERE trigger_type = 'RANK' AND is_active = 1 ORDER BY id"
        )
        rows = await cursor.fetchall()
    
    file_path = "Content/ranksms.txt"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# ============================================\n")
        f.write("# РАНГОВЫЕ ФРАЗЫ (автоматически сгенерировано ботом)\n")
        f.write("# ============================================\n\n")
        
        current_rank = None
        for row in rows:
            rank_name, text, emoji = row
            emoji_str = f"|{emoji}" if emoji else ""
            
            if rank_name != current_rank:
                current_rank = rank_name
                f.write(f"\n# ============================================\n")
                f.write(f"# РАНГ: {rank_name}\n")
                f.write(f"# ============================================\n\n")
            
            f.write(f"RANK|{rank_name}|{text}{emoji_str}\n")

async def sync_all_files():
    """Синхронизирует все файлы с БД"""
    await sync_phrases_to_file()
    await sync_ranks_to_file()
    print("✅ Все файлы синхронизированы с БД")
