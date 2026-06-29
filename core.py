import os
import random
import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command, BaseFilter

# Импорт из database.py
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

# Импорт из config (где все настройки)
from config import CHAT_ID, CHAT_LINK, ADMIN_IDS, is_admin

# ============================================================
# 🔥 ВАЖНО: ФУНКЦИИ ИЗ COFE ПЕРЕДАЮТСЯ ЧЕРЕЗ ПАРАМЕТРЫ
# ============================================================
# Вместо импорта из cofe, мы будем передавать функции через аргументы
# Или просто объявим их как глобальные и установим позже

# Глобальные переменные для функций из cofe
_get_random_phrase = None
_get_rank_phrase = None
_get_streak_achievement = None

def set_phrase_functions(get_random, get_rank, get_streak):
    """Устанавливает функции для работы с фразами из cofe"""
    global _get_random_phrase, _get_rank_phrase, _get_streak_achievement
    _get_random_phrase = get_random
    _get_rank_phrase = get_rank
    _get_streak_achievement = get_streak

# ============================================================
# НАСТРОЙКИ
# ============================================================

DB_PATH = "dori.db"
logger = logging.getLogger(__name__)

# ============================================================
# ФИЛЬТР ПРОВЕРКИ УЧАСТНИКА ЧАТА
# ============================================================

class ChatMemberFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if message.from_user.id in ADMIN_IDS:
            return True
        
        if message.chat.type == 'private':
            try:
                member = await message.bot.get_chat_member(CHAT_ID, message.from_user.id)
                if member.status in ['left', 'kicked']:
                    await message.answer(f"Для пользования ботом сначала зайди в {CHAT_LINK}")
                    return False
                return True
            except:
                await message.answer(f"Для пользования ботом сначала зайди в {CHAT_LINK}")
                return False
        elif message.chat.id != CHAT_ID:
            return False
        return True

chat_filter = ChatMemberFilter()

# ============================================================
# РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_handlers(dp):
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
    dp.message.register(cmd_top_streak, Command("top_streak"), chat_filter)
    dp.message.register(cmd_top_streak, F.text.lower() == ".топ стрик", chat_filter)
    dp.message.register(cmd_top_streak, F.text.lower() == "топ стрик", chat_filter)
    dp.message.register(cmd_top_messages, Command("top_messages"), chat_filter)
    dp.message.register(cmd_top_messages, F.text.lower() == ".топ соо", chat_filter)
    dp.message.register(cmd_top_messages, F.text.lower() == "топ соо", chat_filter)
    dp.message.register(process_message, chat_filter)
    dp.callback_query.register(process_shop, F.data.in_(["buy_shield", "use_shield"]))

# ============================================================
# КОМАНДЫ (с использованием глобальных функций)
# ============================================================

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
# ДАЛЬШЕ ВСЕ КОМАНДЫ КАК БЫЛИ
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

# ... остальные команды без изменений (cmd_name, cmd_me, cmd_shop, process_shop, cmd_top_streak, cmd_top_messages, cmd_redemption)

# ============================================================
# process_message (с использованием get_random_phrase и т.д.)
# ============================================================

async def process_message(message: Message):
    if message.chat.id != CHAT_ID:
        return
    
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    await update_last_message(message.from_user.id)
    await add_coins(message.from_user.id, 0.1)
    await increment_messages_today(message.from_user.id)
    
    current_streak = user['streak'] or 0
    
    # Искупление
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
    
    # Ранги
    rank_mapping = {
        0: "Новичок", 2: "Кандидат", 5: "Знакомый",
        9: "Хороший", 16: "Душа", 24: "Старожил",
        34: "Гордость", 47: "Авторитет", 60: "Незаменимый"
    }
    
    for min_streak, rank_name in sorted(rank_mapping.items()):
        if current_streak >= min_streak and user['rank'] != rank_name:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (rank_name, user['user_id']))
                await db.commit()
            
            rank_phrase = await get_rank_phrase(rank_name)
            if rank_phrase:
                await message.answer(f"🏆 Поздравляю! Ты достиг ранга {rank_name}!\n\n{rank_phrase}")
            else:
                await message.answer(f"🏆 Поздравляю! Ты достиг ранга {rank_name}!")
            break
    
    # Достижения
    achievement_days = [7, 14, 31, 99, 356]
    if current_streak in achievement_days:
        async with aiosqlite.connect(DB_PATH) as db:
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
    
    # Обновление стрика
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
