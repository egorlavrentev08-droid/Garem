import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# ============================================================
# 1. ПОДКЛЮЧЕНИЕ И СОЗДАНИЕ ТАБЛИЦ
# ============================================================

async def init_db():
    """Создаёт таблицы, если их нет"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            name VARCHAR(50) UNIQUE,
            rank VARCHAR(20) DEFAULT 'Новичок',
            streak INT DEFAULT 0,
            streak_record INT DEFAULT 0,
            coins NUMERIC(10,1) DEFAULT 0,
            shield_until TIMESTAMP,
            last_message TIMESTAMP,
            is_registered BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS phrases (
            id SERIAL PRIMARY KEY,
            trigger_type VARCHAR(50) NOT NULL,
            mood VARCHAR(50) NOT NULL,
            phrase_text TEXT NOT NULL,
            emoji TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            usage_count INT DEFAULT 0,
            last_used TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_phrases_trigger ON phrases(trigger_type, mood);
        CREATE INDEX IF NOT EXISTS idx_users_name ON users(name);
    """)
    await conn.close()
    print("✅ База данных инициализирована.")

# ============================================================
# 2. ЗАГРУЗКА ФРАЗ ИЗ ФАЙЛОВ (при первом запуске)
# ============================================================

async def load_phrases_from_file(file_path: str):
    """Загружает фразы из txt-файла в БД, пропуская дубликаты"""
    if not os.path.exists(file_path):
        print(f"⚠️ Файл {file_path} не найден, пропускаем.")
        return

    conn = await asyncpg.connect(DATABASE_URL)
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Формат строки: trigger|mood|text|emoji
            parts = line.split('|')
            if len(parts) < 3:
                continue

            trigger, mood, text = parts[0], parts[1], parts[2]
            emoji = parts[3] if len(parts) > 3 else None

            # Проверяем, есть ли уже такая фраза (по тексту и триггеру)
            exists = await conn.fetchval("""
                SELECT 1 FROM phrases 
                WHERE trigger_type = $1 AND phrase_text = $2
                LIMIT 1
            """, trigger, text)
            
            if not exists:
                await conn.execute("""
                    INSERT INTO phrases (trigger_type, mood, phrase_text, emoji)
                    VALUES ($1, $2, $3, $4)
                """, trigger, mood, text, emoji)

    await conn.close()
    print(f"✅ Фразы из {file_path} загружены.")

# ============================================================
# 3. РАБОТА С ПОЛЬЗОВАТЕЛЯМИ
# ============================================================

async def register_user(user_id: int):
    """Регистрирует пользователя, если его нет"""
    conn = await asyncpg.connect(DATABASE_URL)
    exists = await conn.fetchval("SELECT user_id FROM users WHERE user_id = $1", user_id)
    if not exists:
        await conn.execute("""
            INSERT INTO users (user_id, is_registered)
            VALUES ($1, TRUE)
        """, user_id)
    await conn.close()
    return True

async def get_user(user_id: int):
    """Возвращает данные пользователя или None"""
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return dict(row) if row else None

async def update_user_name(user_id: int, new_name: str):
    """Обновляет имя, если оно уникально"""
    conn = await asyncpg.connect(DATABASE_URL)
    # Проверяем уникальность
    exists = await conn.fetchval("SELECT user_id FROM users WHERE name = $1", new_name)
    if exists:
        await conn.close()
        return False
    await conn.execute("UPDATE users SET name = $1 WHERE user_id = $2", new_name, user_id)
    await conn.close()
    return True

async def update_last_message(user_id: int):
    """Обновляет время последнего сообщения"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE users SET last_message = NOW() WHERE user_id = $1", user_id)
    await conn.close()

async def add_coins(user_id: int, amount: float):
    """Добавляет или забирает коины (отрицательное значение — забирает)"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE users SET coins = coins + $1 WHERE user_id = $2", amount, user_id)
    await conn.close()

async def set_shield(user_id: int, hours: int):
    """Устанавливает щит на N часов (или навсегда, если -1)"""
    conn = await asyncpg.connect(DATABASE_URL)
    if hours == -1:
        await conn.execute("UPDATE users SET shield_until = '9999-12-31 23:59:59' WHERE user_id = $1", user_id)
    else:
        await conn.execute("UPDATE users SET shield_until = NOW() + INTERVAL '$1 hours' WHERE user_id = $2", hours, user_id)
    await conn.close()

async def update_streak(user_id: int, new_streak: int, new_record: int):
    """Обновляет стрик и рекорд"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        UPDATE users 
        SET streak = $1, streak_record = $2 
        WHERE user_id = $3
    """, new_streak, new_record, user_id)
    await conn.close()

# ============================================================
# 4. РАБОТА С ФРАЗАМИ
# ============================================================

async def get_phrases_by_trigger(trigger: str, limit: int = 20):
    """Возвращает список фраз для указанного триггера"""
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT id, phrase_text, mood, emoji, usage_count
        FROM phrases
        WHERE trigger_type = $1 AND is_active = TRUE
        ORDER BY id
        LIMIT $2
    """, trigger, limit)
    await conn.close()
    return [dict(row) for row in rows]

async def add_phrase(trigger: str, mood: str, text: str, emoji: str = None):
    """Добавляет новую фразу в БД"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        INSERT INTO phrases (trigger_type, mood, phrase_text, emoji)
        VALUES ($1, $2, $3, $4)
    """, trigger, mood, text, emoji)
    await conn.close()

async def delete_phrase(phrase_id: int):
    """Мягко удаляет фразу (деактивирует)"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE phrases SET is_active = FALSE WHERE id = $1", phrase_id)
    await conn.close()

# ============================================================
# 5. ПЛАНИРОВЩИК (проверка бездействия)
# ============================================================

async def get_inactive_users():
    """Возвращает пользователей, которые не писали > 24 часов и не имеют щита"""
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("""
        SELECT user_id, name, last_message, shield_until
        FROM users
        WHERE is_registered = TRUE
          AND (shield_until IS NULL OR shield_until < NOW())
          AND last_message < NOW() - INTERVAL '24 hours'
    """)
    await conn.close()
    return [dict(row) for row in rows]

# ============================================================
# ЗАПУСК ПРИ СТАРТЕ
# ============================================================

async def initialize_database():
    """Инициализирует БД и загружает фразы из файлов"""
    await init_db()
    
    # Загружаем фразы из Content (если файлы есть)
    await load_phrases_from_file("Content/phrases.txt")
    await load_phrases_from_file("Content/ranksms.txt")
    
    print("🦊 База данных готова к работе.")
