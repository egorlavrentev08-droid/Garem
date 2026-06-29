import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import initialize_database
from config import ADMIN_IDS

# Импортируем всё из core
from core import (
    register_handlers, chat_filter,
    check_inactive_users, daily_reset_and_reward,
    weekly_streak_reward, check_expired_redemptions_task,
    set_phrase_functions  # <-- НОВОЕ
)

# Импортируем из code и cofe
from code import register_admin_handlers
from cofe import (
    register_library_handlers,
    load_phrases_from_chat,
    get_random_phrase,
    get_rank_phrase_from_cache,
    get_streak_achievement_from_cache
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# ============================================================
# ЗАПУСК И ОСТАНОВКА
# ============================================================

async def on_startup(bot: Bot):
    logger.info("🦊 Инициализация базы данных...")
    await initialize_database()
    
    logger.info("📚 Загрузка фраз из чата-библиотеки...")
    total = await load_phrases_from_chat(bot)
    logger.info(f"📚 Загружено {total} фраз")
    
    # 🔥 ПЕРЕДАЁМ ФУНКЦИИ ИЗ COFE В CORE
    set_phrase_functions(
        get_random_phrase,
        get_rank_phrase_from_cache,
        get_streak_achievement_from_cache
    )
    
    logger.info("🦊 Бот готов к работе!")

async def on_shutdown():
    logger.info("🦊 Бот останавливается...")
    scheduler.shutdown()

# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден!")
        return
    
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    
    chat_filter.bot = bot
    
    register_handlers(dp)
    register_admin_handlers(dp)
    register_library_handlers(dp)
    
    await bot.set_my_commands([
        BotCommand(command="/start", description="Регистрация"),
        BotCommand(command="/name", description="Задать имя"),
        BotCommand(command="/me", description="Анкета"),
        BotCommand(command="/profile", description="Анкета"),
        BotCommand(command="/shop", description="Магазин"),
        BotCommand(command="/top_streak", description="Топ стриков"),
        BotCommand(command="/top_messages", description="Топ сообщений"),
        BotCommand(command="/redemption", description="Восстановление стрика"),
        BotCommand(command="/reload_cache", description="Перезагрузить кеш (админ)"),
        BotCommand(command="/show_cache", description="Показать кеш (админ)"),
        BotCommand(command="/coins", description="Коины (админ)"),
        BotCommand(command="/bypass", description="Щит (админ)"),
        BotCommand(command="/rank", description="Ранг (админ)"),
    ])
    
    scheduler.add_job(check_inactive_users, 'interval', minutes=30, args=(bot,), id='check_inactive')
    scheduler.add_job(check_expired_redemptions_task, 'interval', minutes=15, args=(bot,), id='check_redemptions')
    scheduler.add_job(daily_reset_and_reward, 'cron', hour=0, minute=0, timezone='Europe/Moscow', args=(bot,), id='daily_reset')
    scheduler.add_job(weekly_streak_reward, 'cron', day_of_week='sun', hour=23, minute=59, timezone='Europe/Moscow', args=(bot,), id='weekly_reward')
    scheduler.start()
    
    await on_startup(bot)
    try:
        logger.info("🦊 Dori запущен!")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
