import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import initialize_database
from core import register_handlers, chat_filter
from code import check_inactive_users

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def on_startup():
    logger.info("🦊 Инициализация базы данных...")
    await initialize_database()
    logger.info("🦊 База данных готова.")
    logger.info("🦊 Бот запускается...")

async def on_shutdown():
    logger.info("🦊 Бот останавливается...")
    scheduler.shutdown()

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    chat_filter.bot = bot
    
    register_handlers(dp)
    
    await bot.set_my_commands([
        BotCommand(command="/start", description="Регистрация"),
        BotCommand(command="/name", description="Задать имя"),
        BotCommand(command="/me", description="Анкета"),
        BotCommand(command="/profile", description="Анкета"),
        BotCommand(command="/shop", description="Магазин")
    ])
    
    scheduler.add_job(
        check_inactive_users, 
        'interval', 
        minutes=30, 
        args=(bot,)
    )
    scheduler.start()
    logger.info("🦊 Планировщик запущен (проверка каждые 30 минут)")
    
    await on_startup()
    try:
        logger.info("🦊 Dori запущен и ждёт команды...")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
