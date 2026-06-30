# code.py

import aiosqlite
from aiogram import F
from aiogram.types import Message
from aiogram.filters import Command

from database import (
    get_user, get_user_by_identifier, add_coins, set_shield
)
from config import ADMIN_IDS, is_admin, DB_PATH
from core import chat_filter


# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ
# ============================================================

async def get_target_user(message: Message, identifier: str = None):
    """Определяет целевого пользователя по идентификатору или ответу на сообщение"""
    if identifier:
        clean_id = identifier.lstrip('@')
        user = await get_user_by_identifier(clean_id)
        if user:
            return user
    if message.reply_to_message:
        user = await get_user(message.reply_to_message.from_user.id)
        if user:
            return user
    return None


# ============================================================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_admin_handlers(dp):
    """Регистрирует все админ-команды"""
    dp.message.register(cmd_coins, Command("coins"))
    dp.message.register(cmd_coins, F.text.lower().startswith(".выдать "))
    dp.message.register(cmd_coins, F.text.lower().startswith(".забрать "))
    dp.message.register(cmd_bypass, Command("bypass"))
    dp.message.register(cmd_bypass, F.text.lower().startswith(".защита "))
    dp.message.register(cmd_rank, Command("rank"))
    dp.message.register(cmd_rank, F.text.lower().startswith(".ранг "))


# ============================================================
# УПРАВЛЕНИЕ КОИНАМИ
# ============================================================

async def cmd_coins(message: Message):
    """Выдать или забрать коины у пользователя"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    # Определяем действие
    if text.startswith("/coins"):
        if len(parts) < 4:
            return await message.answer(
                "📝 Используй:\n"
                "/coins give @username N\n"
                "/coins take @username N\n"
                "Или с ответом на сообщение:\n"
                "/coins give N"
            )
        action = parts[1].lower()
        identifier = parts[2].replace('@', '')
        try:
            amount = float(parts[3])
        except ValueError:
            return await message.answer("❌ Сумма должна быть числом.")
    
    elif text.lower().startswith(".выдать "):
        if len(parts) < 2:
            return await message.answer("📝 Используй: .выдать @username N")
        if parts[1].lstrip('@').isdigit():
            # .выдать N (без username, в ответ на сообщение)
            try:
                amount = float(parts[1])
            except ValueError:
                return await message.answer("❌ Сумма должна быть числом.")
            identifier = None
            action = 'give'
        else:
            identifier = parts[1].replace('@', '')
            try:
                amount = float(parts[2])
            except ValueError:
                return await message.answer("❌ Сумма должна быть числом.")
            action = 'give'
    
    elif text.lower().startswith(".забрать "):
        if len(parts) < 2:
            return await message.answer("📝 Используй: .забрать @username N")
        if parts[1].lstrip('@').isdigit():
            # .забрать N (без username, в ответ на сообщение)
            try:
                amount = float(parts[1])
            except ValueError:
                return await message.answer("❌ Сумма должна быть числом.")
            identifier = None
            action = 'take'
        else:
            identifier = parts[1].replace('@', '')
            try:
                amount = float(parts[2])
            except ValueError:
                return await message.answer("❌ Сумма должна быть числом.")
            action = 'take'
    else:
        return
    
    # Определяем пользователя
    user = None
    if identifier:
        user = await get_user_by_identifier(identifier)
    else:
        user = await get_target_user(message, None)
    
    if not user:
        return await message.answer("❌ Пользователь не найден.\nУкажи @username или ответь на сообщение.")
    
    # Применяем
    await add_coins(user['user_id'], amount if action == 'give' else -amount)
    name = user.get('name', user.get('telegram_username', 'пользователя'))
    await message.answer(f"✅ {action} {amount} коинов для {name} (ID: {user['user_id']})")


# ============================================================
# ВЫДАЧА ЩИТА
# ============================================================

async def cmd_bypass(message: Message):
    """Выдать щит пользователю на N часов"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    # Определяем команду
    if text.startswith("/bypass"):
        if len(parts) < 3:
            return await message.answer(
                "📝 Используй:\n"
                "/bypass @username часы\n"
                "Или с ответом на сообщение:\n"
                "/bypass часы"
            )
        identifier = parts[1].replace('@', '')
        try:
            hours = int(parts[2])
        except ValueError:
            return await message.answer("❌ Часы должны быть числом.")
    
    elif text.lower().startswith(".защита "):
        if len(parts) < 2:
            return await message.answer(
                "📝 Используй:\n"
                ".защита @username часы\n"
                "Или с ответом на сообщение:\n"
                ".защита часы"
            )
        if parts[1].isdigit():
            # .защита часы (без username, в ответ на сообщение)
            try:
                hours = int(parts[1])
            except ValueError:
                return await message.answer("❌ Часы должны быть числом.")
            identifier = None
        else:
            identifier = parts[1].replace('@', '')
            try:
                hours = int(parts[2])
            except ValueError:
                return await message.answer("❌ Часы должны быть числом.")
    else:
        return
    
    # Определяем пользователя
    user = None
    if identifier:
        user = await get_user_by_identifier(identifier)
    else:
        user = await get_target_user(message, None)
    
    if not user:
        return await message.answer("❌ Пользователь не найден.\nУкажи @username или ответь на сообщение.")
    
    # Применяем
    await set_shield(user['user_id'], hours)
    name = user.get('name', user.get('telegram_username', 'пользователя'))
    await message.answer(f"✅ Щит на {hours} часов для {name} (ID: {user['user_id']})")


# ============================================================
# СМЕНА РАНГА
# ============================================================

async def cmd_rank(message: Message):
    """Принудительно меняет ранг пользователя"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    # Маппинг цифр на ранги
    rank_map = {
        '0': 'Новичок',
        '1': 'Кандидат',
        '2': 'Знакомый',
        '3': 'Хороший',
        '4': 'Душа',
        '5': 'Старожил',
        '6': 'Гордость',
        '7': 'Авторитет',
        '8': 'Незаменимый'
    }
    
    # Определяем команду
    if text.startswith("/rank"):
        if len(parts) < 3:
            return await message.answer(
                "📝 Используй:\n"
                "/rank @username <название_ранга>\n"
                "/rank @username <0-8>\n\n"
                "0 - Новичок\n"
                "1 - Кандидат\n"
                "2 - Знакомый\n"
                "3 - Хороший\n"
                "4 - Душа\n"
                "5 - Старожил\n"
                "6 - Гордость\n"
                "7 - Авторитет\n"
                "8 - Незаменимый"
            )
        identifier = parts[1].replace('@', '')
        rank_input = parts[2].strip()
    
    elif text.lower().startswith(".ранг "):
        if len(parts) < 3:
            return await message.answer(
                "📝 Используй:\n"
                ".ранг @username <название_ранга>\n"
                ".ранг @username <0-8>\n\n"
                "0 - Новичок\n"
                "1 - Кандидат\n"
                "2 - Знакомый\n"
                "3 - Хороший\n"
                "4 - Душа\n"
                "5 - Старожил\n"
                "6 - Гордость\n"
                "7 - Авторитет\n"
                "8 - Незаменимый"
            )
        identifier = parts[1].replace('@', '')
        rank_input = parts[2].strip()
    else:
        return
    
    # Определяем пользователя
    user = await get_user_by_identifier(identifier)
    if not user:
        return await message.answer(f"❌ Пользователь '{identifier}' не найден.")
    
    # Определяем ранг (число или название)
    if rank_input in rank_map:
        new_rank = rank_map[rank_input]
    else:
        new_rank = rank_input
    
    # Проверяем, что ранг существует в маппинге рангов
    valid_ranks = ['Новичок', 'Кандидат', 'Знакомый', 'Хороший', 
                   'Душа', 'Старожил', 'Гордость', 'Авторитет', 'Незаменимый']
    if new_rank not in valid_ranks:
        return await message.answer(
            f"❌ Неверный ранг: {new_rank}\n\n"
            f"Доступные ранги:\n"
            f"{chr(10).join('• ' + r for r in valid_ranks)}"
        )
    
    # Применяем
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank, user['user_id']))
        await db.commit()
    
    name = user.get('name', user.get('telegram_username', identifier))
    await message.answer(f"✅ Ранг изменён на '{new_rank}' для {name} (ID: {user['user_id']})")
