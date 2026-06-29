import aiosqlite
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from database import (
    get_user, get_user_by_identifier, add_coins, set_shield,
    get_top_streak, get_top_messages_today,
    sync_all_files
)

from core import CHAT_ID, ADMIN_IDS, DB_PATH, is_admin, chat_filter

# ============================================================
# РЕГИСТРАЦИЯ АДМИН-ХЕНДЛЕРОВ
# ============================================================

def register_admin_handlers(dp):
    # Админ-команды
    dp.message.register(cmd_coins, Command("coins"), chat_filter)
    dp.message.register(cmd_coins, F.text.lower().startswith(".выдать "), chat_filter)
    dp.message.register(cmd_coins, F.text.lower().startswith(".забрать "), chat_filter)
    dp.message.register(cmd_bypass, Command("bypass"), chat_filter)
    dp.message.register(cmd_bypass, F.text.lower().startswith(".защита "), chat_filter)
    dp.message.register(cmd_rank, Command("rank"), chat_filter)
    dp.message.register(cmd_rank, F.text.lower().startswith(".ранг "), chat_filter)
    dp.message.register(cmd_reload_cache, Command("reload_cache"), chat_filter)
    dp.message.register(cmd_show_cache, Command("show_cache"), chat_filter)


# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ
# ============================================================

async def get_target_user(message: Message, identifier: str = None):
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
# УПРАВЛЕНИЕ КОИНАМИ
# ============================================================

async def cmd_coins(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    if text.startswith("/coins"):
        if len(parts) < 4:
            return await message.answer("Используй: /coins give/take @username N")
        action = parts[1].lower()
        identifier = parts[2].replace('@', '')
        try:
            amount = float(parts[3])
        except ValueError:
            return await message.answer("❌ Сумма должна быть числом.")
    
    elif text.lower().startswith(".выдать "):
        if len(parts) < 2:
            return await message.answer("Используй: .выдать @username N")
        if parts[1].lstrip('@').isdigit():
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
            return await message.answer("Используй: .забрать @username N")
        if parts[1].lstrip('@').isdigit():
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
    
    user = None
    if identifier:
        user = await get_user_by_identifier(identifier)
    else:
        user = await get_target_user(message, None)
    
    if not user:
        return await message.answer("❌ Пользователь не найден.")
    
    await add_coins(user['user_id'], amount if action == 'give' else -amount)
    await message.answer(f"✅ {action} {amount} для {user.get('name', 'пользователя')}")


# ============================================================
# ВЫДАЧА ЩИТА
# ============================================================

async def cmd_bypass(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    if text.startswith("/bypass"):
        if len(parts) < 3:
            return await message.answer("Используй: /bypass @username часы")
        identifier = parts[1].replace('@', '')
        try:
            hours = int(parts[2])
        except ValueError:
            return await message.answer("❌ Часы должны быть числом.")
    
    elif text.lower().startswith(".защита "):
        if len(parts) < 2:
            return await message.answer("Используй: .защита @username часы")
        if parts[1].isdigit():
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
    
    user = None
    if identifier:
        user = await get_user_by_identifier(identifier)
    else:
        user = await get_target_user(message, None)
    
    if not user:
        return await message.answer("❌ Пользователь не найден.")
    
    await set_shield(user['user_id'], hours)
    await message.answer(f"✅ Щит на {hours} ч. для {user.get('name', 'пользователя')}")


# ============================================================
# СМЕНА РАНГА
# ============================================================

async def cmd_rank(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    rank_map = {
        '0': 'Новичок', '1': 'Кандидат', '2': 'Знакомый',
        '3': 'Хороший', '4': 'Душа', '5': 'Старожил',
        '6': 'Гордость', '7': 'Авторитет', '8': 'Незаменимый'
    }
    
    if text.startswith("/rank"):
        if len(parts) < 3:
            return await message.answer("Используй: /rank @username <ранг>")
        identifier = parts[1].replace('@', '')
        rank_input = parts[2].strip()
    elif text.lower().startswith(".ранг "):
        if len(parts) < 3:
            return await message.answer("Используй: .ранг @username <ранг>")
        identifier = parts[1].replace('@', '')
        rank_input = parts[2].strip()
    else:
        return
    
    user = await get_user_by_identifier(identifier)
    if not user:
        return await message.answer(f"❌ Пользователь не найден.")
    
    new_rank = rank_map.get(rank_input, rank_input)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank, user['user_id']))
        await db.commit()
    
    await message.answer(f"✅ Ранг изменён на {new_rank} для {user.get('name', identifier)}")


# ============================================================
# УПРАВЛЕНИЕ КЕШЕМ
# ============================================================

async def cmd_reload_cache(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    from cofe import load_phrases_from_chat
    total = await load_phrases_from_chat(message.bot)
    await message.answer(f"✅ Кеш перезагружен! {total} фраз.")


async def cmd_show_cache(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    from cofe import phrase_cache
    text = "📚 **КЕШ ФРАЗ**\n\n"
    for trigger, phrases in phrase_cache.items():
        trigger_name = {
            '1_DAY_INACTIVE': '1 день неактива',
            '2_PLUS_DAYS_INACTIVE': '2+ дней',
            'ACTIVITY_RESUMED_AFTER_BREAK': 'Возвращение',
            'RANK': 'Ранги',
            'STREAK_ACHIEVEMENT': 'Достижения'
        }.get(trigger, trigger)
        text += f"**{trigger_name}**: {len(phrases)} шт.\n"
        for p in phrases[:3]:
            text += f"  • {p['text'][:40]}...\n"
        text += "\n"
    await message.answer(text)
