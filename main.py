import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Импорт из твоих файлов
from database import initialize_database
from core import register_handlers, check_inactive_users, chat_filter

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация планировщика
scheduler = AsyncIOScheduler()

async def on_startup():
    """Действия при старте бота"""
    logger.info("🦊 Инициализация базы данных...")
    await initialize_database()
    logger.info("🦊 База данных готова.")
    logger.info("🦊 Бот запускается...")

async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("🦊 Бот останавливается...")
    scheduler.shutdown()

async def main():
    """Главная функция запуска"""
    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # ============================================================
    # 🛡️ ВАЖНО: Передаём экземпляр бота в фильтр проверки чата
    # ============================================================
    chat_filter.bot = bot  # Без этой строки фильтр не сработает!
    
    # Регистрируем все хендлеры из core.py
    register_handlers(dp)
    
    # Устанавливаем команды в меню бота
    await bot.set_my_commands([
        BotCommand(command="/start", description="Регистрация"),
        BotCommand(command="/name", description="Задать имя"),
        BotCommand(command="/me", description="Анкета"),
        BotCommand(command="/profile", description="Анкета"),
        BotCommand(command="/shop", description="Магазин"),
        BotCommand(command="/sms", description="Управление фразами (админ)"),
        BotCommand(command="/coins", description="Управление коинами (админ)"),
        BotCommand(command="/bypass", description="Выдать щит (админ)")
    ])
    
    # Запускаем планировщик для проверки бездействия
    # Каждые 30 минут проверяем, кто не писал > 24 часов
    scheduler.add_job(
        check_inactive_users, 
        'interval', 
        minutes=30, 
        args=(bot,)
    )
    scheduler.start()
    logger.info("🦊 Планировщик запущен (проверка каждые 30 минут)")
    
    # Запускаем бота
    await on_startup()
    try:
        logger.info("🦊 Dori запущен и ждёт команды...")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
