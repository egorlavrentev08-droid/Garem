import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Импорт из твоих файлов
from database import initialize_database
from core import (
    register_handlers, 
    check_inactive_users, 
    chat_filter,
    daily_reset_and_reward,
    weekly_streak_reward,
    check_expired_redemptions_task
)

# Загружаем переменные окружения (не обязательны, но для других переменных)
load_dotenv()

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
    # ============================================================
    # 🤖 ТОКЕН БЕРЕТСЯ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ХОСТИНГА
    # ============================================================
    bot = Bot(token=os.getenv("BOT_TOKEN"))
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
        BotCommand(command="/sms", description="Управление контентом (админ)"),
        BotCommand(command="/top_streak", description="Топ стриков"),
        BotCommand(command="/top_messages", description="Топ сообщений за сегодня"),
        BotCommand(command="/redemption", description="Прогресс восстановления стрика"),
        BotCommand(command="/redemption_stats", description="Статистика искуплений (админ)"),
    ])
    
    # ============================================================
    # 📅 НАСТРОЙКА ПЛАНИРОВЩИКА
    # ============================================================
    
    # 1. Проверка бездействия (каждые 30 минут)
    scheduler.add_job(
        check_inactive_users, 
        'interval', 
        minutes=30, 
        args=(bot,),
        id='check_inactive'
    )
    logger.info("🦊 Планировщик: проверка бездействия каждые 30 минут")
    
    # 2. Проверка просроченных искуплений (каждые 15 минут)
    scheduler.add_job(
        check_expired_redemptions_task,
        'interval',
        minutes=15,
        args=(bot,),
        id='check_redemptions'
    )
    logger.info("🦊 Планировщик: проверка искуплений каждые 15 минут")
    
    # 3. Ежедневный сброс и награда в 00:00 МСК
    scheduler.add_job(
        daily_reset_and_reward,
        'cron',
        hour=0, minute=0,
        timezone='Europe/Moscow',
        args=(bot,),
        id='daily_reset'
    )
    logger.info("🦊 Планировщик: ежедневный сброс в 00:00 МСК")
    
    # 4. Еженедельная награда в воскресенье 23:59 МСК
    scheduler.add_job(
        weekly_streak_reward,
        'cron',
        day_of_week='sun', hour=23, minute=59,
        timezone='Europe/Moscow',
        args=(bot,),
        id='weekly_reward'
    )
    logger.info("🦊 Планировщик: еженедельная награда в вс 23:59 МСК")
    
    # Запускаем планировщик
    scheduler.start()
    logger.info("🦊 Планировщик запущен")
    
    # Запускаем бота
    await on_startup()
    try:
        logger.info("🦊 Dori запущен и ждёт команды...")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
