import os
import random
import asyncio
import logging
from aiogram import F, Bot
from aiogram.types import Message, ChatMemberUpdated, FSInputFile
from aiogram.filters import Command

from config import ADMIN_IDS, LIBRARY_CHAT_ID, LIBRARY_CHAT_LINK, TRIGGER_SYMBOLS, MOOD_SYMBOLS, is_admin

logger = logging.getLogger(__name__)

# Кеш фраз (в памяти)
phrase_cache = {
    '1_DAY_INACTIVE': [],
    '2_PLUS_DAYS_INACTIVE': [],
    'ACTIVITY_RESUMED_AFTER_BREAK': [],
    'RANK': [],
    'STREAK_ACHIEVEMENT': []
}


# ============================================================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_library_handlers(dp):
    # Основные хендлеры чата-библиотеки
    dp.message.register(library_parser, F.chat.id == LIBRARY_CHAT_ID)
    dp.message.register(update_cache_on_edited, F.chat.id == LIBRARY_CHAT_ID)
    dp.my_chat_member.register(update_cache_on_deleted)
    
    # Команды для проверки и обновления (работают везде)
    dp.message.register(cmd_check_cache, Command("check"))
    dp.message.register(cmd_check_cache, F.text.lower() == ".чек")
    dp.message.register(cmd_update_cache, Command("upd"))
    dp.message.register(cmd_update_cache, F.text.lower() == ".апд")


# ============================================================
# КОМАНДЫ ДЛЯ ПРОВЕРКИ И ОБНОВЛЕНИЯ КЕША
# ============================================================

async def cmd_check_cache(message: Message):
    """Показывает сколько фраз загружено в кеш"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Только админы!")
    
    total = sum(len(p) for p in phrase_cache.values())
    
    text = f"📊 **СТАТУС КЕША ФРАЗ**\n\n"
    text += f"📚 Всего фраз: {total}\n\n"
    
    for trigger, phrases in phrase_cache.items():
        trigger_name = {
            '1_DAY_INACTIVE': '1 день неактива',
            '2_PLUS_DAYS_INACTIVE': '2+ дней',
            'ACTIVITY_RESUMED_AFTER_BREAK': 'Возвращение',
            'RANK': 'Ранги',
            'STREAK_ACHIEVEMENT': 'Достижения'
        }.get(trigger, trigger)
        text += f"• {trigger_name}: {len(phrases)} шт.\n"
    
    text += f"\n🔄 Для обновления: `/upd` или `.апд`"
    
    await message.answer(text)


async def cmd_update_cache(message: Message):
    """Принудительно обновляет кеш из чата-библиотеки"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Только админы!")
    
    await message.answer("🔄 Начинаю обновление кеша из чата-библиотеки...")
    
    total = await load_phrases_from_chat(message.bot)
    
    await message.answer(
        f"✅ **Кеш обновлён!**\n\n"
        f"📚 Загружено фраз: {total}\n"
        f"📊 Всего фраз в кеше: {sum(len(p) for p in phrase_cache.values())}"
    )


# ============================================================
# УДАЛЕНИЕ СООБЩЕНИЙ БОТА
# ============================================================

async def delete_message_after_delay(bot: Bot, chat_id: int, message_id: int, delay: int = 60):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ============================================================
# ЗАГРУЗКА ФРАЗ ИЗ ЧАТА ПРИ СТАРТЕ (С ЦИКЛАМИ)
# ============================================================

async def load_phrases_from_chat(bot: Bot):
    global phrase_cache
    
    phrase_cache = {
        '1_DAY_INACTIVE': [],
        '2_PLUS_DAYS_INACTIVE': [],
        'ACTIVITY_RESUMED_AFTER_BREAK': [],
        'RANK': [],
        'STREAK_ACHIEVEMENT': []
    }
    
    try:
        logger.info("📥 Начинаем загрузку фраз из чата-библиотеки...")
        
        all_messages = []
        last_message_id = None
        limit_per_request = 100
        total_loaded = 0
        max_messages = 2000  # Максимум сообщений для загрузки
        
        # Цикл для пагинации
        while total_loaded < max_messages:
            try:
                # Получаем сообщения с пагинацией
                if last_message_id:
                    messages = await bot.get_chat_messages(
                        chat_id=LIBRARY_CHAT_ID,
                        limit=limit_per_request,
                        offset_id=last_message_id
                    )
                else:
                    messages = await bot.get_chat_messages(
                        chat_id=LIBRARY_CHAT_ID,
                        limit=limit_per_request
                    )
                
                # Если сообщений нет - выходим
                if not messages:
                    logger.info("📭 Сообщения закончились")
                    break
                
                all_messages.extend(messages)
                total_loaded += len(messages)
                logger.info(f"📥 Загружено {len(messages)} сообщений (всего: {total_loaded})")
                
                # Обновляем последний ID для следующей итерации
                last_message_id = messages[-1].message_id
                
                # Если загрузили меньше лимита - значит это последние сообщения
                if len(messages) < limit_per_request:
                    logger.info("📭 Достигнут конец истории чата")
                    break
                    
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при загрузке сообщений: {e}")
                break
        
        # Парсим все загруженные сообщения (от старых к новым)
        logger.info(f"📝 Парсим {len(all_messages)} сообщений...")
        parsed_count = 0
        
        for message in reversed(all_messages):
            if message.text:
                if parse_and_cache_phrase(message.text):
                    parsed_count += 1
        
        total = sum(len(p) for p in phrase_cache.values())
        logger.info(f"📚 Загружено {total} фраз из чата-библиотеки (всего сообщений: {len(all_messages)}, распарсено: {parsed_count})")
        return total
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки: {e}")
        return 0


def parse_and_cache_phrase(text: str) -> bool:
    """Парсит сообщение и добавляет в кеш. Возвращает True если добавила"""
    if len(text) < 2:
        return False
    
    trigger_symbol = text[0]
    mood_symbol = text[1]
    
    if trigger_symbol not in TRIGGER_SYMBOLS or mood_symbol not in MOOD_SYMBOLS:
        return False
    
    phrase_text = text[2:].strip()
    
    if len(phrase_text) < 7 or len(phrase_text) > 100:
        return False
    
    trigger = TRIGGER_SYMBOLS[trigger_symbol]
    mood = MOOD_SYMBOLS[mood_symbol]
    
    # Проверяем дубликат
    for p in phrase_cache.get(trigger, []):
        if p['text'].lower() == phrase_text.lower():
            return False
    
    phrase_cache[trigger].append({
        'text': phrase_text,
        'mood': mood,
        'original': text
    })
    return True


# ============================================================
# ПАРСЕР СООБЩЕНИЙ В ЧАТЕ-БИБЛИОТЕКЕ
# ============================================================

async def library_parser(message: Message):
    if message.chat.id != LIBRARY_CHAT_ID:
        return
    
    if not is_admin(message.from_user.id):
        reply = await message.reply("❌ Только админы!")
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    text = message.text
    if not text:
        reply = await message.reply("❌ Отправь текст!")
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    # Проверка длины без маркеров
    clean_text = text
    for char in text[:2]:
        if char in TRIGGER_SYMBOLS or char in MOOD_SYMBOLS:
            clean_text = clean_text.replace(char, '', 1)
    clean_text = clean_text.strip()
    
    if len(clean_text) < 7:
        reply = await message.reply(
            f"❌ **Слишком коротко!**\nМинимум: 7 символов\nПример: `!₽ Где ты был?`"
        )
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    if len(clean_text) > 100:
        reply = await message.reply(
            f"❌ **Слишком длинно!**\nМаксимум: 100 символов"
        )
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    # Проверка маркеров
    if len(text) < 2:
        reply = await message.reply(
            f"❌ **Неверный формат!**\nПример: `!₽ Где ты был?`"
        )
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    trigger_symbol = text[0]
    mood_symbol = text[1]
    
    if trigger_symbol not in TRIGGER_SYMBOLS:
        available = ', '.join(TRIGGER_SYMBOLS.keys())
        reply = await message.reply(f"❌ **Неверный триггер!**\nДоступны: {available}")
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    if mood_symbol not in MOOD_SYMBOLS:
        available = ', '.join(MOOD_SYMBOLS.keys())
        reply = await message.reply(f"❌ **Неверное настроение!**\nДоступны: {available}")
        asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
        return
    
    # Проверка дубликата
    phrase_text = text[2:].strip()
    trigger = TRIGGER_SYMBOLS[trigger_symbol]
    
    for p in phrase_cache.get(trigger, []):
        if p['text'].lower() == phrase_text.lower():
            reply = await message.reply(f"⚠️ **Такая фраза уже есть!**\n{p['text']}")
            asyncio.create_task(delete_message_after_delay(message.bot, message.chat.id, reply.message_id, 60))
            return
    
    # Сохраняем
    mood = MOOD_SYMBOLS[mood_symbol]
    
    phrase_cache[trigger].append({
        'text': phrase_text,
        'mood': mood,
        'original': text
    })
    
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
# ОБНОВЛЕНИЕ КЕША
# ============================================================

async def update_cache_on_edited(message: Message):
    if message.chat.id != LIBRARY_CHAT_ID:
        return
    await load_phrases_from_chat(message.bot)
    logger.info("🔄 Кеш обновлён после редактирования сообщения")


async def update_cache_on_deleted(event: ChatMemberUpdated):
    if event.chat.id != LIBRARY_CHAT_ID:
        return
    await load_phrases_from_chat(event.bot)
    logger.info("🔄 Кеш обновлён после удаления сообщения")


# ============================================================
# ПОЛУЧЕНИЕ ФРАЗ ИЗ КЕША
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
