import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Импорты твоих модулей (которые мы создадим)
# from handlers import user_router, admin_router
# from database import create_pool 

# Настройка логирования, чтобы видеть ошибки в консоли
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Твой токен (лучше брать из .env, но пока для теста можно вписать сюда)
TOKEN = "ТВОЙ_ТОКЕН_ОТ_BOTFATHER"

async def main():
    # 1. Инициализация бота и диспетчера
    bot = Bot(
        token=TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 2. Инициализация базы данных (пример)
    # await create_pool() 
    # logging.info("База данных подключена")

    # 3. Регистрация роутеров (сюда мы будем подключать файлы из папки handlers)
    # dp.include_router(user_router)
    # dp.include_router(admin_router)

    # 4. Запуск бота
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот выключен")
