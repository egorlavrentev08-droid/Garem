# core.py

import os
import random
import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command, BaseFilter

from database import (
    register_user, get_user, update_user_name, update_last_message,
    add_coins, set_shield, update_streak, get_user_by_identifier,
    get_inactive_users, increment_streak,
    increment_messages_today,
    start_redemption, update_redemption_progress,
    get_redemption_status, complete_redemption,
    add_reward_history,
    add_shield, use_shield, get_shield_count
)

from config import CHAT_ID, CHAT_LINK, ADMIN_IDS, is_admin

logger = logging.getLogger(__name__)

# ============================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ДЛЯ ФУНКЦИЙ ИЗ COFE
# ============================================================

_get_random_phrase = None
_get_rank_phrase = None
_get_streak_achievement = None


def set_phrase_functions(get_random, get_rank, get_streak):
    """Устанавливает функции из cofe.py"""
    global _get_random_phrase, _get_rank_phrase, _get_streak_achievement
    _get_random_phrase = get_random
    _get_rank_phrase = get_rank
    _get_streak_achievement = get_streak


async def get_random_phrase(trigger: str, mood: str = None) -> str | None:
    if _get_random_phrase:
        return await _get_random_phrase(trigger, mood)
    return None


async def get_rank_phrase(rank_name: str) -> str | None:
    if _get_rank_phrase:
        return await _get_rank_phrase(rank_name)
    return None


async def get_streak_achievement(day: int) -> str | None:
    if _get_streak_achievement:
        return await _get_streak_achievement(day)
    return None


# ============================================================
# 🔥 ФИЛЬТР ПРОВЕРКИ ЧАТА (ТОЛЬКО ОСНОВНОЙ ЧАТ!)
# ============================================================

def chat_filter(message: Message) -> bool:
    """Проверяет, что сообщение пришло строго из основного чата"""
    return message.chat.id == CHAT_ID


# ============================================================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_handlers(dp):
    # --- ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ ---
    dp.message.register(cmd_start, Command("start"), chat_filter)
    dp.message.register(cmd_name, Command("name"), chat_filter)
    dp.message.register(cmd_name, F.text.lower().startswith(".имя "), chat_filter)
    dp.message.register(cmd_me, Command("me"), chat_filter)
    dp.message.register(cmd_me, Command("profile"), chat_filter)
    dp.message.register(cmd_me, F.text.lower() == ".я", chat_filter)
    dp.message.register(cmd_me, F.text.lower() == ".профиль", chat_filter)
    dp.message.register(cmd_shop, Command("shop"), chat_filter)
    dp.message.register(cmd_shop, F.text.lower() == ".шоп", chat_filter)
    dp.message.register(cmd_shop, F.text.lower() == ".щит", chat_filter)
    dp.message.register(cmd_redemption, Command("redemption"), chat_filter)
    dp.message.register(cmd_redemption, F.text.lower() == ".искупление", chat_filter)
    
    # --- ТОПЫ ---
    dp.message.register(cmd_top_streak, Command("top_streak"), chat_filter)
    dp.message.register(cmd_top_streak, F.text.lower() == ".топ стрик", chat_filter)
    dp.message.register(cmd_top_streak, F.text.lower() == "топ стрик", chat_filter)
    dp.message.register(cmd_top_messages, Command("top_messages"), chat_filter)
    dp.message.register(cmd_top_messages, F.text.lower() == ".топ соо", chat_filter)
    dp.message.register(cmd_top_messages, F.text.lower() == "топ соо", chat_filter)
    
    # --- ОБРАБОТКА ВСЕХ СООБЩЕНИЙ В ОСНОВНОМ ЧАТЕ ---
    dp.message.register(process_message, F.chat.id == CHAT_ID, chat_filter)
    
    # --- МАГАЗИН (callback) ---
    dp.callback_query.register(process_shop, F.data.in_(["buy_shield", "use_shield"]))


# ============================================================
# КОМАНДЫ ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

async def cmd_start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await register_user(message.from_user.id, message.from_user.username)
        await message.answer(
            "🦊 Привет! Я Dori — Архитектор Дисциплины!\n"
            "Ты зарегистрировался\n\n"
            "Используй /name чтобы задать себе имя."
        )
    else:
        await message.answer(
            "🦊 Привет! Я Dori — Архитектор Дисциплины!\n\n"
            "/me - профиль\n"
            "/shop - магазин\n"
            ".топ стрик - топ стриков\n"
            ".топ соо - топ сообщений за сегодня\n"
            ".искупление - прогресс восстановления стрика"
        )


async def cmd_name(message: Message):
    text = message.text
    if text.startswith("/name"):
        args = text.split(maxsplit=1)
    elif text.lower().startswith(".имя "):
        args = [".имя", text[5:].strip()]
    else:
        return
    
    if len(args) < 2:
        return await message.answer("Используй: /name ТвоёИмя или .имя ТвоёИмя")
    
    new_name = args[1].strip()
    if len(new_name) > 50:
        return await message.answer("❌ Имя слишком длинное (макс. 50 символов).")
    
    success = await update_user_name(message.from_user.id, new_name)
    if success:
        await message.answer(f"✅ Теперь ты {new_name}!")
    else:
        await message.answer("❌ Это имя уже занято. Выбери другое.")


async def cmd_me(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала зарегистрируйся: /start")
    
    # Статус щита
    shield_status = "❌ Не активен"
    shield_time_left = ""
    if user['shield_until']:
        try:
            shield_time = datetime.fromisoformat(user['shield_until'])
            if shield_time > datetime.now():
                hours_left = (shield_time - datetime.now()).total_seconds() / 3600
                shield_status = f"🛡️ Активен ({int(hours_left)} ч.)"
            else:
                shield_status = "❌ Истёк"
        except:
            pass
    
    # Количество щитов
    shield_count = await get_shield_count(message.from_user.id)
    
    # Искупление
    redemption = await get_redemption_status(message.from_user.id)
    redemption_text = ""
    if redemption and redemption['active']:
        progress = redemption['progress']
        target = redemption['target']
        redemption_text = f"\n| 🔄 Искупление: {progress}/{target} сообщений"
    
    text = (
        f"📋 Анкета {user['name'] or 'Без имени'}\n"
        f"| Ранг: {user['rank']}\n"
        f"| Стриков: {user['streak']} дней\n"
        f"| Рекорд: {user['streak_record']} дней\n"
        f"| Коинов: {user['coins']:.1f}\n"
        f"| Щитов: {shield_count} шт.\n"
        f"| Щит: {shield_status}{redemption_text}"
    )
    await message.answer(text)


# ============================================================
# МАГАЗИН
# ============================================================

async def cmd_shop(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала зарегистрируйся: /start")
    
    shield_count = await get_shield_count(message.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🛡️ Купить щит (100 коинов) [{shield_count} шт.]", callback_data="buy_shield")],
        [InlineKeyboardButton(text="⚡ Активировать щит (36 часов)", callback_data="use_shield")]
    ])
    await message.answer(
        f"🛒 **Магазин**\n\n"
        f"💰 Коинов: {user['coins']:.1f}\n"
        f"🛡️ Щитов в запасе: {shield_count} шт.\n\n"
        f"💡 Щит защищает стрик от сброса на 36 часов",
        reply_markup=kb
    )


async def process_shop(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        return await callback.answer("Сначала зарегистрируйся: /start", show_alert=True)
    
    if callback.data == "buy_shield":
        if user['coins'] < 100:
            return await callback.answer("❌ Недостаточно коинов! Нужно 100.", show_alert=True)
        
        await add_coins(callback.from_user.id, -100)
        await add_shield(callback.from_user.id, 1)
        
        shield_count = await get_shield_count(callback.from_user.id)
        
        await callback.answer("✅ Щит куплен!", show_alert=True)
        await callback.message.edit_text(
            f"✅ Щит куплен!\n\n"
            f"🛡️ Теперь у тебя {shield_count} щитов.\n"
            f"Используй 'Активировать щит', чтобы защитить стрик."
        )
    
    elif callback.data == "use_shield":
        shield_count = await get_shield_count(callback.from_user.id)
        if shield_count == 0:
            return await callback.answer("❌ У тебя нет щитов! Купи в магазине.", show_alert=True)
        
        if user['shield_until']:
            try:
                shield_time = datetime.fromisoformat(user['shield_until'])
                if shield_time > datetime.now():
                    hours_left = (shield_time - datetime.now()).total_seconds() / 3600
                    return await callback.answer(
                        f"⏳ У тебя уже активен щит ({int(hours_left)} ч.)", 
                        show_alert=True
                    )
            except:
                pass
        
        await use_shield(callback.from_user.id)
        await set_shield(callback.from_user.id, 36)
        
        shield_count = await get_shield_count(callback.from_user.id)
        
        await callback.answer("⚡ Щит активирован на 36 часов!", show_alert=True)
        await callback.message.edit_text(
            f"🛡️ Щит активирован на 36 часов!\n\n"
            f"Осталось щитов: {shield_count} шт."
        )


# ============================================================
# ТОПЫ
# ============================================================

async def cmd_top_streak(message: Message):
    from database import get_top_streak
    top = await get_top_streak(15)
    
    if not top:
        return await message.answer("📊 Пока нет данных. Напиши что-нибудь!")
    
    text = "🏆 **ТОП СТРИКОВ**\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user.get('name', user.get('telegram_username', 'Без имени'))
        text += f"{medal} **{name}** — {user['streak']} дней\n"
    
    text += "\n✨ **Награды в конце недели:**\n🥇 10000 | 🥈 5000 | 🥉 1000 коинов"
    await message.answer(text)


async def cmd_top_messages(message: Message):
    from database import get_top_messages_today
    top = await get_top_messages_today(15)
    
    if not top:
        return await message.answer("📊 Сегодня пока никто не писал. Будь первым!")
    
    text = "💬 **ТОП СООБЩЕНИЙ** (за сегодня)\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user.get('name', user.get('telegram_username', 'Без имени'))
        text += f"{medal} **{name}** — {user['messages_today']} сообщений\n"
    
    text += "\n✨ **1 место** получит 100 коинов в 00:00 МСК!"
    await message.answer(text)


# ============================================================
# ИСКУПЛЕНИЕ
# ============================================================

async def cmd_redemption(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала зарегистрируйся: /start")
    
    redemption = await get_redemption_status(message.from_user.id)
    
    if not redemption or not redemption['active']:
        return await message.answer(
            "❌ У тебя нет активного искупления.\n"
            "Оно появляется, если ты потерял стрик."
        )
    
    progress = redemption['progress']
    target = redemption['target']
    streak_to_restore = redemption['streak_to_restore']
    remaining = target - progress
    
    try:
        expires = datetime.fromisoformat(redemption['expires_at'])
        hours_left = (expires - datetime.now()).total_seconds() / 3600
    except:
        hours_left = 24
    
    text = (
        f"🔄 **Восстановление стрика**\n\n"
        f"Цель: {target} сообщений\n"
        f"Прогресс: {progress} сообщений\n"
        f"Осталось: {remaining} сообщений\n"
        f"Восстановится стрик: {streak_to_restore} дней\n"
        f"⏳ Осталось: ~{int(hours_left)} часов\n\n"
        f"{'🔥 ДАВАЙ, ТЫ СМОЖЕШЬ!' if progress > 100 else '💪 ПИШИ БОЛЬШЕ!'}"
    )
    await message.answer(text)


# ============================================================
# ОБРАБОТКА ВСЕХ СООБЩЕНИЙ В ОСНОВНОМ ЧАТЕ
# ============================================================

async def process_message(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    await update_last_message(message.from_user.id)
    await add_coins(message.from_user.id, 0.1)
    await increment_messages_today(message.from_user.id)
    
    current_streak = user['streak'] or 0
    
    # --- ИСКУПЛЕНИЕ ---
    redemption = await get_redemption_status(message.from_user.id)
    if redemption and redemption['active']:
        await update_redemption_progress(message.from_user.id)
        
        updated = await get_redemption_status(message.from_user.id)
        progress = updated['progress']
        target = updated['target']
        streak_to_restore = updated['streak_to_restore']
        
        if progress >= target:
            await complete_redemption(message.from_user.id)
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            await message.answer(
                f"🎉 **{name}** восстановил стрик в {streak_to_restore} дней! 🦊"
            )
            await message.bot.send_message(
                CHAT_ID,
                f"🎉 **{name}** восстановил стрик в {streak_to_restore} дней! 🔥"
            )
            return
        else:
            if progress % 50 == 0:
                remaining = target - progress
                await message.answer(
                    f"📊 {progress}/{target} сообщений до восстановления. Осталось {remaining}!"
                )
    
    # --- ПРОВЕРКА РАНГОВ ---
    rank_mapping = {
        0: "Новичок", 2: "Кандидат", 5: "Знакомый",
        9: "Хороший", 16: "Душа", 24: "Старожил",
        34: "Гордость", 47: "Авторитет", 60: "Незаменимый"
    }
    
    for min_streak, rank_name in sorted(rank_mapping.items()):
        if current_streak >= min_streak and user['rank'] != rank_name:
            async with aiosqlite.connect("dori.db") as db:
                await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank_name, user['user_id']))
                await db.commit()
            
            rank_phrase = await get_rank_phrase(rank_name)
            if rank_phrase:
                await message.answer(f"🏆 Поздравляю! Ты достиг ранга {rank_name}!\n\n{rank_phrase}")
            else:
                await message.answer(f"🏆 Поздравляю! Ты достиг ранга {rank_name}!")
            break
    
    # --- ДОСТИЖЕНИЯ ---
    achievement_days = [7, 14, 31, 99, 356]
    if current_streak in achievement_days:
        async with aiosqlite.connect("dori.db") as db:
            cursor = await db.execute(
                "SELECT 1 FROM rewards_history WHERE user_id = ? AND reward_type = 'achievement' AND streak = ?",
                (user['user_id'], current_streak)
            )
            already = await cursor.fetchone()
        
        if not already:
            phrase = await get_streak_achievement(current_streak)
            if not phrase:
                phrase = f"Ты достиг {current_streak} дней стрика! 🦊"
            
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            await message.bot.send_message(
                CHAT_ID,
                f"🎉 **{name}** заработал {current_streak}-дневный стрик!\n\n{phrase}"
            )
            await add_reward_history(user['user_id'], 'achievement', 0, 0, current_streak)
    
    # --- ОБНОВЛЕНИЕ СТРИКА ---
    if user['last_message']:
        try:
            last_msg_time = datetime.fromisoformat(user['last_message'])
            if datetime.now() - last_msg_time > timedelta(hours=24):
                new_streak = await increment_streak(message.from_user.id)
                if new_streak in [5, 10, 25, 50, 100]:
                    await message.answer(f"🎉 {new_streak} дней подряд! Ты крут!")
        except:
            pass


# ============================================================
# ПЛАНИРОВЩИК
# ============================================================

async def check_inactive_users(bot: Bot):
    inactive = await get_inactive_users()
    
    for user in inactive:
        if not user['last_message']:
            continue
        
        hours_since = (datetime.now() - datetime.fromisoformat(user['last_message'])).total_seconds() / 3600
        
        if 24 <= hours_since < 48:
            phrase = await get_random_phrase("1_DAY_INACTIVE")
            if phrase:
                await bot.send_message(user['user_id'], phrase)
            else:
                await bot.send_message(user['user_id'], "📣 Ты пропал на сутки. Напиши что-нибудь!")
        
        elif hours_since >= 48:
            shield_active = user['shield_until'] and datetime.fromisoformat(user['shield_until']) > datetime.now()
            
            if shield_active:
                await set_shield(user['user_id'], 0)
                await bot.send_message(
                    user['user_id'],
                    "🛡️ Щит спас стрик! Но он сгорел. Купи новый в /shop."
                )
            else:
                old_streak = user['streak']
                await update_streak(user['user_id'], 0, user['streak_record'])
                await start_redemption(user['user_id'], old_streak)
                
                name = user.get('name', user.get('telegram_username', 'Кто-то'))
                
                await bot.send_message(
                    user['user_id'],
                    f"💔 Стрик в {old_streak} дней сброшен.\n\n"
                    f"🔄 **Шанс восстановить!**\n"
                    f"Напиши **200 сообщений** за сегодня!\n\n"
                    f"Прогресс: **.искупление**"
                )
                
                await bot.send_message(
                    CHAT_ID,
                    f"😱 **{name}** проиграл стрик в {old_streak} дней!\n"
                    f"Но может восстановить — 200 сообщений за сегодня. 👀"
                )
                
                if random.choice([True, False]):
                    phrase = await get_random_phrase("2_PLUS_DAYS_INACTIVE")
                    if phrase:
                        await bot.send_message(user['user_id'], phrase)
                else:
                    meme_folder = 'Content/mems/'
                    if os.path.exists(meme_folder) and os.listdir(meme_folder):
                        meme_file = random.choice(os.listdir(meme_folder))
                        meme_path = os.path.join(meme_folder, meme_file)
                        await bot.send_photo(user['user_id'], photo=FSInputFile(meme_path))


# ============================================================
# НАГРАДЫ
# ============================================================

async def daily_reset_and_reward(bot: Bot):
    from database import award_daily_top, reset_daily_messages
    winner = await award_daily_top()
    if winner:
        name = winner.get('name', winner.get('telegram_username', 'Кто-то'))
        await bot.send_message(CHAT_ID, f"🌟 **{name}** лидер по сообщениям! +100 коинов! 🪙")
    await reset_daily_messages()
    logger.info("🔄 Daily reset")


async def weekly_streak_reward(bot: Bot):
    from database import award_weekly_top
    winners = await award_weekly_top()
    if winners:
        text = "🏆 **ЕЖЕНЕДЕЛЬНЫЙ ТОП**\n\n"
        for user, pos, coins in winners:
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            medal = ["🥇", "🥈", "🥉"][pos - 1]
            text += f"{medal} **{name}** — {user['streak']} дней (+{coins} коинов)\n"
        await bot.send_message(CHAT_ID, text)
        logger.info("🔄 Weekly rewards")


async def check_expired_redemptions_task(bot: Bot):
    from database import check_expired_redemptions, get_user
    expired = await check_expired_redemptions()
    for user_id in expired:
        user = await get_user(user_id)
        if user:
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            await bot.send_message(
                user_id,
                f"💀 Время вышло. Стрик не восстановлен. Начинай с нуля, {name}! 💪"
            )
            await bot.send_message(
                CHAT_ID,
                f"⏰ **{name}** не успел восстановить стрик. Начинает с нуля. 😈"
      )
