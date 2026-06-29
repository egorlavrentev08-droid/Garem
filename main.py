import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, Message
from aiogram.filters import Command
from aiogram import F
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
    
    logger.info("📚 Загрузка фраз из чата-библиотеки...")
    total = await load_phrases_from_chat(bot)
    logger.info(f"📚 Загружено {total} фраз")
    
    # 🔥 ПЕРЕДАЁМ ФУНКЦИИ ИЗ COFE В CORE
    set_phrase_functions(
        get_random_phrase,
        get_rank_phrase_from_cache,
        get_streak_achievement_from_cache
    )
    logger.info("✅ Функции фраз переданы в core")
    
    logger.info("🦊 Бот готов к работе!")


async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("🦊 Бот останавливается...")
    scheduler.shutdown()


# ============================================================
# КОМАНДЫ ДЛЯ ПРОВЕРКИ И ОБНОВЛЕНИЯ КЕША (ПРЯМО В MAIN)
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
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def main():
    """Главная функция запуска"""
    
    # Получаем токен
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN не найден в переменных окружения!")
        return
    
    # Инициализация бота и диспетчера
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    
    # ============================================================
    # 🛡️ ВАЖНО: Передаём экземпляр бота в фильтр проверки чата
    # ============================================================
    chat_filter.bot = bot
    
    # ============================================================
    # 📋 РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
    # ============================================================
    
    # Основные хендлеры (пользователи)
    register_handlers(dp)
    logger.info("✅ Основные хендлеры зарегистрированы")
    
    # Админ-хендлеры
    register_admin_handlers(dp)
    logger.info("✅ Админ-хендлеры зарегистрированы")
    
    # Чат-библиотека
    register_library_handlers(dp)
    logger.info("✅ Чат-библиотека зарегистрирована")
    
    # ============================================================
    # 🔥 КОМАНДЫ ДЛЯ КЕША (ПРЯМО ЗДЕСЬ, ЧТОБЫ ТОЧНО РАБОТАЛИ)
    # ============================================================
    
    dp.message.register(cmd_check_cache, Command("check"))
    dp.message.register(cmd_check_cache, F.text.lower() == ".чек")
    dp.message.register(cmd_update_cache, Command("upd"))
    dp.message.register(cmd_update_cache, F.text.lower() == ".апд")
    logger.info("✅ Команды кеша зарегистрированы")
    
    # ============================================================
    # 📋 КОМАНДЫ В МЕНЮ БОТА
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
    
    # ============================================================
    # 🚀 ЗАПУСК БОТА
    # ============================================================
    
    await on_startup(bot)
    
    try:
        logger.info("🦊 Dori запущен и ждёт команды...")
        await dp.start_polling(bot)
    finally:
        await on_shutdown()


# ============================================================
# ТОЧКА ВХОДА
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
