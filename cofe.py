# cofe.py (финальная версия с БД)

import random
import asyncio
import logging
from aiogram import F, Dispatcher
from aiogram.types import Message, ChatMemberUpdated

from config import ADMIN_IDS, LIBRARY_CHAT_ID, TRIGGER_SYMBOLS, MOOD_SYMBOLS, is_admin
from database import save_phrases_to_db, load_phrases_from_db

logger = logging.getLogger(__name__)

# ============================================================
# КЕШ ФРАЗ (В ПАМЯТИ, ЗАГРУЖАЕТСЯ ИЗ БД)
# ============================================================

phrase_cache = {
    '1_DAY_INACTIVE': [],
    '2_PLUS_DAYS_INACTIVE': [],
    'ACTIVITY_RESUMED_AFTER_BREAK': [],
    'RANK': [],
    'STREAK_ACHIEVEMENT': []
}


# ============================================================
# ЗАГРУЗКА ФРАЗ ИЗ БД (АСИНХРОННАЯ!)
# ============================================================

async def load_phrases_from_chat():
    """Загружает фразы из БД в кеш (асинхронно)"""
    global phrase_cache
    phrase_cache = await load_phrases_from_db()
    total = sum(len(p) for p in phrase_cache.values())
    logger.info(f"📚 Загружено {total} фраз из БД")
    return total


# ============================================================
# УДАЛЕНИЕ СООБЩЕНИЙ БОТА
# ============================================================

async def delete_message_after_delay(bot, chat_id: int, message_id: int, delay: int = 60):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ============================================================
# ПАРСЕР СООБЩЕНИЙ В ЧАТЕ-БИБЛИОТЕКЕ
# ============================================================

async def library_parser(message: Message):
    if message.chat.id != LIBRARY_CHAT_ID:
        return
    
    # 🔥 Проверяем формат — только с триггером + настроением
    text = message.text
    if not text:
        return
    
    if len(text) < 2:
        return
    
    trigger_symbol = text[0]
    mood_symbol = text[1]
    
    # Если нет триггера или настроения — игнорируем
    if trigger_symbol not in TRIGGER_SYMBOLS:
        return
    if mood_symbol not in MOOD_SYMBOLS:
        return
    
    # Дальше проверяем админа
    if not is_admin(message.from_user.id):
        reply = await message.reply("❌ Только админы!")
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    # Проверка длины фразы (без маркеров)
    phrase_text = text[2:].strip()
    if len(phrase_text) < 7:
        reply = await message.reply(
            f"❌ **Слишком коротко!**\nМинимум: 7 символов\nПример: `!₽ Где ты был?`"
        )
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    if len(phrase_text) > 100:
        reply = await message.reply(
            f"❌ **Слишком длинно!**\nМаксимум: 100 символов"
        )
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    # Проверка дубликата
    trigger = TRIGGER_SYMBOLS[trigger_symbol]
    for p in phrase_cache.get(trigger, []):
        if p['text'].lower() == phrase_text.lower():
            reply = await message.reply(f"⚠️ **Такая фраза уже есть!**\n{p['text']}")
            asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
            return
    
    # Сохраняем в кеш
    mood = MOOD_SYMBOLS[mood_symbol]
    
    phrase_cache[trigger].append({
        'text': phrase_text,
        'mood': mood,
        'original': text
    })
    
    # Сохраняем в БД (асинхронно)
    await save_phrases_to_db(trigger, phrase_cache[trigger])
    
    trigger_name = {
        '1_DAY_INACTIVE': '1 день неактива',
        '2_PLUS_DAYS_INACTIVE': '2+ дней',
        'ACTIVITY_RESUMED_AFTER_BREAK': 'Возвращение',
        'RANK': 'Ранги',
        'STREAK_ACHIEVEMENT': 'Достижения'
    }.get(trigger, trigger)
    
    mood_name = {
        'ANXIOUS': '😰 Тревожное',
        'ANGRY': '😡 Злое',
        'SARCASTIC': '😏 Саркастичное',
        'MOTIVATIONAL': '💪 Мотивирующее',
        'FRIENDLY': '🤗 Дружелюбное'
    }.get(mood, mood)
    
    reply = await message.reply(
        f"✅ **Сообщение добавлено!**\n\n"
        f"📌 {trigger_name}\n"
        f"🎭 {mood_name}\n"
        f"📝 {phrase_text}\n\n"
        f"📊 Всего фраз: {sum(len(p) for p in phrase_cache.values())}"
    )
    
    asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))


# ============================================================
# ОБНОВЛЕНИЕ КЕША (ПРИ РЕДАКТИРОВАНИИ/УДАЛЕНИИ)
# ============================================================

async def update_cache_on_edited(message: Message):
    if message.chat.id != LIBRARY_CHAT_ID:
        return
    # Перезагружаем из БД
    await load_phrases_from_chat()
    logger.info("🔄 Кеш обновлён после редактирования сообщения")


async def update_cache_on_deleted(event: ChatMemberUpdated):
    if event.chat.id != LIBRARY_CHAT_ID:
        return
    # Перезагружаем из БД
    await load_phrases_from_chat()
    logger.info("🔄 Кеш обновлён после удаления сообщения")


# ============================================================
# ПОЛУЧЕНИЕ ФРАЗ ИЗ КЕША (АСИНХРОННЫЕ)
# ============================================================

async def get_random_phrase(trigger: str, mood: str = None) -> str | None:
    phrases = phrase_cache.get(trigger, [])
    if not phrases:
        return None
    if mood:
        phrases = [p for p in phrases if p['mood'] == mood]
    if not phrases:
        return None
    return random.choice(phrases)['text']


async def get_rank_phrase_from_cache(rank_name: str) -> str | None:
    phrases = phrase_cache.get('RANK', [])
    rank_phrases = [p for p in phrases if rank_name.lower() in p['text'].lower()]
    if not rank_phrases:
        return None
    return random.choice(rank_phrases)['text']


async def get_streak_achievement_from_cache(day: int) -> str | None:
    phrases = phrase_cache.get('STREAK_ACHIEVEMENT', [])
    day_phrases = [p for p in phrases if str(day) in p['text']]
    if not day_phrases:
        return None
    return random.choice(day_phrases)['text']


# ============================================================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_library_handlers(dp: Dispatcher):
    """Регистрирует хендлеры для чата-библиотеки"""
    dp.message.register(library_parser, F.chat.id == LIBRARY_CHAT_ID)
    dp.message.register(update_cache_on_edited, F.chat.id == LIBRARY_CHAT_ID)
    dp.my_chat_member.register(update_cache_on_deleted)
    logger.info("✅ Хендлеры чата-библиотеки зарегистрированы")
