# main.py

import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import BotCommand, Message
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import initialize_database
from config import ADMIN_IDS, is_admin

from core import (
    register_handlers, 
    chat_filter,
    check_inactive_users, 
    daily_reset_and_reward,
    weekly_streak_reward, 
    check_expired_redemptions_task,
    set_phrase_functions
)
from code import register_admin_handlers
from cofe import (
    register_library_handlers,
    load_phrases_from_chat,
    get_random_phrase,
    get_rank_phrase_from_cache,
    get_streak_achievement_from_cache,
    phrase_cache
)

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация планировщика
scheduler = AsyncIOScheduler()


# ============================================================
# ЗАПУСК И ОСТАНОВКА
# ============================================================

async def on_startup(bot: Bot):
    """Действия при старте бота"""
    logger.info("🦊 Инициализация базы данных...")
    await initialize_database()
    
    logger.info("📚 Загрузка фраз из БД...")
    total = await load_phrases_from_chat()  # ← теперь await!
    logger.info(f"📚 Загружено {total} фраз из БД")
    
    set_phrase_functions(
        get_random_phrase,
        get_rank_phrase_from_cache,
        get_streak_achievement_from_cache
    )
    logger.info("✅ Функции фраз переданы в core")


async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("🦊 Бот останавливается...")
    scheduler.shutdown()


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def main():
    """Главная функция запуска"""
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
        return
    
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    
    # ============================================================
    # 🔥 РЕГИСТРАЦИЯ ХЕНДЛЕРОВ (ПОРЯДОК ВАЖЕН!)
    # ============================================================
    
    # 1. Сначала обрабатываем чат-библиотеку (чтобы не перехватывалась админ-фильтрами)
    register_library_handlers(dp)
    logger.info("✅ Чат-библиотека зарегистрирована")
    
    # 2. Админские команды общего назначения (без фильтра, работают в ЛС)
    register_admin_handlers(dp)
    logger.info("✅ Админ-хендлеры зарегистрированы")
    
    # 3. Основные обработчики игрового чата (с фильтром chat_filter)
    register_handlers(dp)
    logger.info("✅ Основные хендлеры зарегистрированы")
    
    # ============================================================
    # 🔥 КОМАНДЫ ДЛЯ КЕША (БЕЗ ФИЛЬТРА, РАБОТАЮТ В ЛС ДЛЯ АДМИНОВ)
    # ============================================================
    
    @dp.message(Command("check"))
    async def cmd_check(message: Message):
        logger.info(f"🔍 КОМАНДА /check от {message.from_user.id}")
        if not is_admin(message.from_user.id):
            return await message.answer("❌ Только админы!")
        
        total = sum(len(p) for p in phrase_cache.values())
        text = f"📊 **СТАТУС КЕША ФРАЗ**\n\n📚 Всего фраз: {total}\n\n"
        for trigger, phrases in phrase_cache.items():
            names = {
                '1_DAY_INACTIVE': '1 день неактива',
                '2_PLUS_DAYS_INACTIVE': '2+ дней',
                'ACTIVITY_RESUMED_AFTER_BREAK': 'Возвращение',
                'RANK': 'Ранги',
                'STREAK_ACHIEVEMENT': 'Достижения'
            }
            text += f"• {names.get(trigger, trigger)}: {len(phrases)} шт.\n"
        text += f"\n🔄 Для обновления: /upd или .апд"
        await message.answer(text)
    
    @dp.message(F.text.lower() == ".чек")
    async def cmd_check_dot(message: Message):
        logger.info(f"🔍 КОМАНДА .чек от {message.from_user.id}")
        if not is_admin(message.from_user.id):
            return await message.answer("❌ Только админы!")
        
        total = sum(len(p) for p in phrase_cache.values())
        text = f"📊 **СТАТУС КЕША ФРАЗ**\n\n📚 Всего фраз: {total}\n\n"
        for trigger, phrases in phrase_cache.items():
            names = {
                '1_DAY_INACTIVE': '1 день неактива',
                '2_PLUS_DAYS_INACTIVE': '2+ дней',
                'ACTIVITY_RESUMED_AFTER_BREAK': 'Возвращение',
                'RANK': 'Ранги',
                'STREAK_ACHIEVEMENT': 'Достижения'
            }
            text += f"• {names.get(trigger, trigger)}: {len(phrases)} шт.\n"
        text += f"\n🔄 Для обновления: /upd или .апд"
        await message.answer(text)
    
    @dp.message(Command("upd"))
    async def cmd_update(message: Message):
        logger.info(f"🔍 КОМАНДА /upd от {message.from_user.id}")
        if not is_admin(message.from_user.id):
            return await message.answer("❌ Только админы!")
        
        await message.answer("🔄 Обновляю кеш из БД...")
        total = await load_phrases_from_chat()  # ← теперь await!
        await message.answer(
            f"✅ **Кеш обновлён!**\n\n"
            f"📚 Загружено фраз: {total}\n"
            f"📊 Всего в кеше: {sum(len(p) for p in phrase_cache.values())}"
        )
    
    @dp.message(F.text.lower() == ".апд")
    async def cmd_update_dot(message: Message):
        logger.info(f"🔍 КОМАНДА .апд от {message.from_user.id}")
        if not is_admin(message.from_user.id):
            return await message.answer("❌ Только админы!")
        
        await message.answer("🔄 Обновляю кеш из БД...")
        total = await load_phrases_from_chat()  # ← теперь await!
        await message.answer(
            f"✅ **Кеш обновлён!**\n\n"
            f"📚 Загружено фраз: {total}\n"
            f"📊 Всего в кеше: {sum(len(p) for p in phrase_cache.values())}"
        )
    
    logger.info("✅ Команды кеша (/check, .чек, /upd, .апд) зарегистрированы")
    
    # ============================================================
    # КОМАНДЫ В МЕНЮ
    # ============================================================
    
    await bot.set_my_commands([
        BotCommand(command="/start", description="Регистрация"),
        BotCommand(command="/name", description="Задать имя"),
        BotCommand(command="/me", description="Анкета"),
        BotCommand(command="/profile", description="Анкета"),
        BotCommand(command="/shop", description="Магазин"),
        BotCommand(command="/top_streak", description="Топ стриков"),
        BotCommand(command="/top_messages", description="Топ сообщений за сегодня"),
        BotCommand(command="/redemption", description="Прогресс восстановления стрика"),
        BotCommand(command="/check", description="Проверить кеш фраз (админ)"),
        BotCommand(command="/upd", description="Обновить кеш фраз (админ)"),
        BotCommand(command="/coins", description="Управление коинами (админ)"),
        BotCommand(command="/bypass", description="Выдать щит (админ)"),
        BotCommand(command="/rank", description="Сменить ранг (админ)"),
    ])
    logger.info("✅ Команды в меню установлены")
    
    # ============================================================
    # ПЛАНИРОВЩИК
    # ============================================================
    
    scheduler.add_job(check_inactive_users, 'interval', minutes=30, args=(bot,), id='check_inactive')
    scheduler.add_job(check_expired_redemptions_task, 'interval', minutes=15, args=(bot,), id='check_redemptions')
    scheduler.add_job(daily_reset_and_reward, 'cron', hour=0, minute=0, timezone='Europe/Moscow', args=(bot,), id='daily_reset')
    scheduler.add_job(weekly_streak_reward, 'cron', day_of_week='sun', hour=23, minute=59, timezone='Europe/Moscow', args=(bot,), id='weekly_reward')
    scheduler.start()
    logger.info("🦊 Планировщик запущен")
    
    # ============================================================
    # ЗАПУСК
    # ============================================================
    
    await on_startup(bot)
    
    try:
        logger.info("🦊 Dori запущен и ждёт команды...")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
