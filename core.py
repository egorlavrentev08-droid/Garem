import os
import random
import logging
import aiosqlite
from datetime import datetime, timedelta
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, FSInputFile
from aiogram.filters import Command, CommandObject, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорт из database.py
from database import (
    register_user, get_user, update_user_name, update_last_message,
    add_coins, set_shield, update_streak, 
    get_user_by_identifier,
    get_phrases_by_trigger, add_phrase, delete_phrase,
    get_inactive_users, increment_streak,
    get_rank_phrase_by_name, get_total_phrases_count,
    sync_all_files, sync_phrases_to_file, sync_ranks_to_file,
    get_top_streak, get_top_messages_today,
    reset_daily_messages, get_streak_achievement,
    award_daily_top, award_weekly_top,
    increment_messages_today,
    start_redemption, update_redemption_progress,
    get_redemption_status, complete_redemption,
    fail_redemption, check_expired_redemptions,
    add_reward_history
)

# ============================================================
# 0. ФИЛЬТР ПРОВЕРКИ УЧАСТНИКА ЧАТА
# ============================================================

CHAT_ID = -1002497100583
CHAT_LINK = "@Gar3mDi"
ADMIN_IDS = [6595788533, 1903870420]
DB_PATH = "dori.db"

class ChatMemberFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        # Админы могут писать боту в ЛС без проверки
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

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

chat_filter = ChatMemberFilter()

# ============================================================
# 1. СОСТОЯНИЯ ДЛЯ FSM
# ============================================================

class PhraseBuilder(StatesGroup):
    waiting_for_full_phrase = State()
    waiting_for_trigger = State()
    waiting_for_mood = State()
    confirmation = State()

class PhraseRemover(StatesGroup):
    waiting_for_number = State()

class FileUpload(StatesGroup):
    waiting_for_image = State()
    waiting_for_meme = State()

class FileRemover(StatesGroup):
    waiting_for_number = State()

class ChooseTrigger(StatesGroup):
    waiting_for_trigger = State()

temp_phrases = {}
temp_page = {}
temp_files = {}

# ============================================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КОМАНД
# ============================================================

async def get_target_user(message: Message, identifier: str = None):
    """
    Определяет целевого пользователя:
    1. Если есть identifier (username или ID) - ищем по нему
    2. Если есть ответ на сообщение - берём автора ответа
    3. Иначе - текущий пользователь
    """
    if identifier:
        # Убираем @ если есть
        clean_id = identifier.lstrip('@')
        user = await get_user_by_identifier(clean_id)
        if user:
            return user
    
    # Проверяем ответ на сообщение
    if message.reply_to_message:
        user = await get_user(message.reply_to_message.from_user.id)
        if user:
            return user
    
    return None

# ============================================================
# 3. РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_handlers(dp):
    # --- ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ (ТОЛЬКО ИЗ ЧАТА) ---
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
    
    # --- ТОПЫ (ТОЛЬКО ИЗ ЧАТА) ---
    dp.message.register(cmd_top_streak, Command("top_streak"), chat_filter)
    dp.message.register(cmd_top_streak, F.text.lower() == ".топ стрик", chat_filter)
    dp.message.register(cmd_top_streak, F.text.lower() == "топ стрик", chat_filter)
    dp.message.register(cmd_top_messages, Command("top_messages"), chat_filter)
    dp.message.register(cmd_top_messages, F.text.lower() == ".топ соо", chat_filter)
    dp.message.register(cmd_top_messages, F.text.lower() == "топ соо", chat_filter)
    
    # --- АДМИН-КОМАНДЫ (ТОЛЬКО ИЗ ЧАТА) ---
    dp.message.register(cmd_sms, Command("sms"), chat_filter)
    dp.message.register(cmd_sms, Command("content"), chat_filter)
    dp.message.register(cmd_sms, F.text.lower() == ".контент", chat_filter)
    dp.message.register(cmd_sms, F.text.lower() == ".смс", chat_filter)
    dp.message.register(cmd_coins, Command("coins"), chat_filter)
    dp.message.register(cmd_coins, F.text.lower().startswith(".выдать "), chat_filter)
    dp.message.register(cmd_coins, F.text.lower().startswith(".забрать "), chat_filter)
    dp.message.register(cmd_bypass, Command("bypass"), chat_filter)
    dp.message.register(cmd_bypass, F.text.lower().startswith(".защита "), chat_filter)
    dp.message.register(cmd_rank, Command("rank"), chat_filter)
    dp.message.register(cmd_rank, F.text.lower().startswith(".ранг "), chat_filter)
    
    # --- ОБРАБОТКА ВСЕХ СООБЩЕНИЙ В ЧАТЕ ---
    dp.message.register(process_message, chat_filter)
    
    # ============================================================
    # 🔥 FSM - РАБОТАЮТ В ЛИЧНЫХ СООБЩЕНИЯХ (БЕЗ chat_filter)
    # ============================================================
    
    # FSM - выбор триггера
    dp.callback_query.register(choose_trigger, ChooseTrigger.waiting_for_trigger, F.data.startswith("trigger_"))
    
    # FSM - добавление фразы
    dp.message.register(get_full_phrase, PhraseBuilder.waiting_for_full_phrase)
    dp.callback_query.register(get_trigger, PhraseBuilder.waiting_for_trigger, F.data.startswith("trigger_"))
    dp.callback_query.register(get_mood, PhraseBuilder.waiting_for_mood, F.data.startswith("mood_"))
    dp.callback_query.register(save_phrase, PhraseBuilder.confirmation, F.data == "confirm_save")
    
    # FSM - удаление фразы
    dp.message.register(process_remove_number, PhraseRemover.waiting_for_number)
    
    # FSM - загрузка картинок
    dp.message.register(upload_image, FileUpload.waiting_for_image)
    dp.message.register(upload_meme, FileUpload.waiting_for_meme)
    
    # FSM - удаление файлов
    dp.message.register(process_remove_file_number, FileRemover.waiting_for_number)
    
    # ============================================================
    # 🔘 КНОПКИ МЕНЮ (callback)
    # ============================================================
    dp.callback_query.register(admin_phrases_list, F.data == "admin_phrases")
    dp.callback_query.register(admin_images_menu, F.data == "admin_images")
    dp.callback_query.register(admin_memes_menu, F.data == "admin_memes")
    dp.callback_query.register(next_page, F.data == "next_page")
    dp.callback_query.register(prev_page, F.data == "prev_page")
    dp.callback_query.register(remove_phrase, F.data == "remove_phrase")
    dp.callback_query.register(start_add_phrase, F.data == "add_phrase")
    dp.callback_query.register(cancel_add, F.data == "cancel_add")
    dp.callback_query.register(sync_files, F.data == "sync_files")
    dp.callback_query.register(admin_images_list, F.data == "images_list")
    dp.callback_query.register(admin_memes_list, F.data == "memes_list")
    dp.callback_query.register(upload_new_image, F.data == "upload_image")
    dp.callback_query.register(upload_new_meme, F.data == "upload_meme")
    dp.callback_query.register(remove_file_menu, F.data == "remove_file")
    dp.callback_query.register(next_file_page, F.data == "next_file_page")
    dp.callback_query.register(prev_file_page, F.data == "prev_file_page")
    dp.callback_query.register(back_to_sms, F.data == "back_to_sms")
    dp.callback_query.register(admin_ranks_list, F.data == "admin_ranks")
    dp.callback_query.register(show_rank_phrases, F.data.startswith("rank_"))
    dp.callback_query.register(back_to_sms, F.data == "back_to_sms")
    dp.callback_query.register(process_shop, F.data.in_(["buy_shield", "use_shield"]))

# ============================================================
# 4. ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
# ============================================================

async def cmd_start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await register_user(message.from_user.id, message.from_user.username)
        await message.answer(
            "🦊 Привет! Я Dori — Архитектор Дисциплины и бот чата **GD**.\n"
            "Ты зарегистрировался\n\n"
            "Используй /name чтобы задать себе имя."
        )
    else:
        await message.answer(
            "🦊 Привет! Я Dori — Архитектор Дисциплины и бот чата **GD**.\n\n"
            "/me - профиль\n"
            "/shop - купить щит\n"
            ".топ стрик - топ стриков\n"
            ".топ соо - топ сообщений за сегодня\n"
            ".искупление - прогресс восстановления стрика"
        )

async def cmd_name(message: Message):
    # Определяем текст команды (поддержка /name и .имя)
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
    
    shield_status = "🛡️ Активен" if user['shield_until'] and datetime.fromisoformat(user['shield_until']) > datetime.now() else "❌ Не активен"
    
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
        f"| Стриков Рекорд: {user['streak_record']} дней\n"
        f"| Коинов: {user['coins']:.1f}\n"
        f"| Щит действует: {shield_status}{redemption_text}"
    )
    await message.answer(text)

async def cmd_shop(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ Купить щит (100 коинов)", callback_data="buy_shield")],
        [InlineKeyboardButton(text="⚡ Использовать щит (36 часов)", callback_data="use_shield")]
    ])
    await message.answer("🛒 Магазин:", reply_markup=kb)

async def process_shop(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        return await callback.answer("Сначала зарегистрируйся: /start", show_alert=True)
    
    if callback.data == "buy_shield":
        if user['coins'] < 100:
            return await callback.answer("❌ Недостаточно коинов! Нужно 100.", show_alert=True)
        await add_coins(callback.from_user.id, -100)
        await set_shield(callback.from_user.id, 36)
        await callback.answer("✅ Щит куплен и активирован на 36 часов!", show_alert=True)
        await callback.message.edit_text("🛡️ Щит активирован!")
    
    elif callback.data == "use_shield":
        if user['shield_until']:
            try:
                shield_time = datetime.fromisoformat(user['shield_until'])
                if shield_time > datetime.now():
                    await callback.answer("⏳ У тебя уже есть активный щит.", show_alert=True)
                    return
            except:
                pass
        await set_shield(callback.from_user.id, 36)
        await callback.answer("⚡ Щит активирован на 36 часов!", show_alert=True)
        await callback.message.edit_text("🛡️ Щит активирован!")

# ============================================================
# 5. ТОПЫ
# ============================================================

async def cmd_top_streak(message: Message):
    top = await get_top_streak(15)
    
    if not top:
        return await message.answer("📊 Пока нет данных. Напиши что-нибудь, чтобы попасть в топ!")
    
    text = "🏆 **ТОП СТРИКОВ** (за всё время)\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user.get('name', user.get('telegram_username', 'Без имени'))
        text += f"{medal} **{name}** — {user['streak']} дней\n"
    
    text += "\n✨ **Награды в конце недели:**\n🥇 10000 коинов | 🥈 5000 коинов | 🥉 1000 коинов"
    
    await message.answer(text)

async def cmd_top_messages(message: Message):
    top = await get_top_messages_today(15)
    
    if not top:
        return await message.answer("📊 Сегодня пока никто не писал. Будь первым!")
    
    text = "💬 **ТОП СООБЩЕНИЙ** (за сегодня)\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, user in enumerate(top):
        medal = medals[i] if i < 10 else f"{i+1}."
        name = user.get('name', user.get('telegram_username', 'Без имени'))
        text += f"{medal} **{name}** — {user['messages_today']} сообщений\n"
    
    text += "\n✨ **Первое место** получит 100 коинов в 00:00 МСК!"
    
    await message.answer(text)

# ============================================================
# 6. ИСКУПЛЕНИЕ
# ============================================================

async def cmd_redemption(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала зарегистрируйся: /start")
    
    redemption = await get_redemption_status(message.from_user.id)
    
    if not redemption or not redemption['active']:
        return await message.answer(
            "❌ У тебя нет активного искупления.\n"
            "Оно появляется, если ты потерял стрик из-за неактивности."
        )
    
    progress = redemption['progress']
    target = redemption['target']
    streak_to_restore = redemption['streak_to_restore']
    remaining = target - progress
    
    try:
        expires = datetime.fromisoformat(redemption['expires_at'])
        time_left = expires - datetime.now()
        hours_left = time_left.total_seconds() / 3600
    except:
        hours_left = 24
    
    text = (
        f"🔄 **Восстановление стрика**\n\n"
        f"Цель: {target} сообщений\n"
        f"Прогресс: {progress} сообщений\n"
        f"Осталось: {remaining} сообщений\n"
        f"Восстановится стрик: {streak_to_restore} дней\n"
        f"⏳ Осталось времени: ~{int(hours_left)} часов\n\n"
        f"{'🔥 ДАВАЙ, ТЫ СМОЖЕШЬ!' if progress > 100 else '💪 ПИШИ БОЛЬШЕ!'}"
    )
    
    await message.answer(text)

# ============================================================
# 7. АДМИНСКИЕ КОМАНДЫ
# ============================================================

async def cmd_coins(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    # Определяем действие
    if text.startswith("/coins"):
        if len(parts) < 4:
            return await message.answer("Используй: /coins give/take @username (n) или /coins give/take user_id (n)")
        action = parts[1].lower()
        identifier = parts[2].replace('@', '')
        try:
            amount = float(parts[3])
        except ValueError:
            return await message.answer("❌ Сумма должна быть числом.")
    
    elif text.lower().startswith(".выдать "):
        if len(parts) < 3:
            return await message.answer("Используй: .выдать @username (n) или .выдать (n) (в ответ на сообщение)")
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
        if len(parts) < 3:
            return await message.answer("Используй: .забрать @username (n) или .забрать (n) (в ответ на сообщение)")
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
    
    # Определяем пользователя
    user = None
    if identifier:
        user = await get_user_by_identifier(identifier)
    else:
        user = await get_target_user(message, None)
    
    if not user:
        return await message.answer(f"❌ Пользователь не найден.")
    
    await add_coins(user['user_id'], amount if action == 'give' else -amount)
    await message.answer(f"✅ Коины обновлены: {action} {amount} для {user.get('name', identifier or 'пользователя')} (ID: {user['user_id']})")

async def cmd_bypass(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    text = message.text
    parts = text.split()
    
    # Определяем команду
    if text.startswith("/bypass"):
        if len(parts) < 3:
            return await message.answer("Используй: /bypass @username (часы) или /bypass (часы) (в ответ на сообщение)")
        identifier = parts[1].replace('@', '')
        try:
            hours = int(parts[2])
        except ValueError:
            return await message.answer("❌ Часы должны быть числом.")
    
    elif text.lower().startswith(".защита "):
        if len(parts) < 3:
            return await message.answer("Используй: .защита @username (часы) или .защита (часы) (в ответ на сообщение)")
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
    
    # Определяем пользователя
    user = None
    if identifier:
        user = await get_user_by_identifier(identifier)
    else:
        user = await get_target_user(message, None)
    
    if not user:
        return await message.answer(f"❌ Пользователь не найден.")
    
    await set_shield(user['user_id'], hours)
    await message.answer(f"✅ Щит установлен на {hours} часов для {user.get('name', identifier or 'пользователя')} (ID: {user['user_id']})")

async def cmd_rank(message: Message):
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
            return await message.answer("Используй: /rank @username <название_ранга> или /rank @username (0-8)")
        identifier = parts[1].replace('@', '')
        rank_input = parts[2].strip()
    
    elif text.lower().startswith(".ранг "):
        if len(parts) < 3:
            return await message.answer("Используй: .ранг @username <название_ранга> или .ранг @username (0-8)")
        identifier = parts[1].replace('@', '')
        rank_input = parts[2].strip()
    else:
        return
    
    # Определяем пользователя
    user = await get_user_by_identifier(identifier)
    if not user:
        return await message.answer(f"❌ Пользователь с идентификатором '{identifier}' не найден.")
    
    # Определяем ранг (число или название)
    if rank_input in rank_map:
        new_rank = rank_map[rank_input]
    else:
        new_rank = rank_input
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank, user['user_id']))
        await db.commit()
    
    rank_phrase = await get_rank_phrase_by_name(new_rank)
    if rank_phrase:
        await message.answer(f"🏆 Ранг пользователя {user.get('name', identifier)} изменён на {new_rank}.\n\n{rank_phrase}")
    else:
        await message.answer(f"✅ Ранг изменён на {new_rank}.")

# ============================================================
# 8. АДМИНСКОЕ МЕНЮ /sms (.контент, /content, .смс)
# ============================================================

async def cmd_sms(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Фразы", callback_data="admin_phrases")],
        [InlineKeyboardButton(text="🖼️ Картинки без текста", callback_data="admin_images")],
        [InlineKeyboardButton(text="📝🖼️ Картинки с текстом", callback_data="admin_memes")],
        [InlineKeyboardButton(text="🏆 Фразы рангов", callback_data="admin_ranks")],
        [InlineKeyboardButton(text="🔄 Синхронизировать файлы", callback_data="sync_files")]
    ])
    await message.answer("📋 Панель управления контентом:", reply_markup=kb)

# ===== СИНХРОНИЗАЦИЯ =====

async def sync_files(callback: CallbackQuery):
    await sync_all_files()
    await callback.answer("✅ Все файлы синхронизированы с БД!", show_alert=True)
    await callback.message.edit_text("✅ Файлы успешно синхронизированы!")

# ============================================================
# 9. УПРАВЛЕНИЕ ФРАЗАМИ (с выбором триггера)
# ============================================================

async def admin_phrases_list(callback: CallbackQuery, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 день неактива", callback_data="trigger_1DAY")],
        [InlineKeyboardButton(text="Несколько дней неактива", callback_data="trigger_2PLUS")],
        [InlineKeyboardButton(text="Возвращение после перерыва", callback_data="trigger_RESUMED")],
        [InlineKeyboardButton(text="🏆 Ранговые фразы", callback_data="trigger_RANK")],
        [InlineKeyboardButton(text="🎯 Достижения стрика", callback_data="trigger_STREAK")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sms")]
    ])
    await callback.message.edit_text("📌 Выбери тип фраз:", reply_markup=kb)
    await state.set_state(ChooseTrigger.waiting_for_trigger)

async def choose_trigger(callback: CallbackQuery, state: FSMContext):
    trigger_map = {
        "trigger_1DAY": "1_DAY_INACTIVE",
        "trigger_2PLUS": "2_PLUS_DAYS_INACTIVE",
        "trigger_RESUMED": "ACTIVITY_RESUMED_AFTER_BREAK",
        "trigger_RANK": "RANK",
        "trigger_STREAK": "STREAK_ACHIEVEMENT"
    }
    
    trigger = trigger_map[callback.data]
    await state.clear()
    
    total = await get_total_phrases_count(trigger)
    phrases = await get_phrases_by_trigger(trigger, limit=15, offset=0)
    
    temp_page[callback.from_user.id] = {"trigger": trigger, "page": 1, "total": total}
    max_page = max(1, (total + 14) // 15)
    
    text = f"📝 Фразы ({trigger}) — страница 1/{max_page}:\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i}. {p['phrase_text']} {p['emoji'] or ''}\n"
    if not phrases:
        text += "Пока нет фраз."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_phrase")],
        [InlineKeyboardButton(text="➖ Убрать", callback_data="remove_phrase")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_page")],
        [InlineKeyboardButton(text="🔙 К выбору триггера", callback_data="admin_phrases")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def next_page(callback: CallbackQuery):
    current = temp_page.get(callback.from_user.id, {"trigger": "1_DAY_INACTIVE", "page": 1, "total": 0})
    total = current["total"]
    max_page = max(1, (total + 14) // 15)
    next_page_num = current["page"] + 1
    if next_page_num > max_page:
        next_page_num = 1
    offset = (next_page_num - 1) * 15
    phrases = await get_phrases_by_trigger(current["trigger"], limit=15, offset=offset)
    temp_page[callback.from_user.id] = {"trigger": current["trigger"], "page": next_page_num, "total": total}
    text = f"📝 Фразы ({current['trigger']}) — страница {next_page_num}/{max_page}:\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i + offset}. {p['phrase_text']} {p['emoji'] or ''}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_phrase")],
        [InlineKeyboardButton(text="➖ Убрать", callback_data="remove_phrase")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_page")],
        [InlineKeyboardButton(text="🔙 К выбору триггера", callback_data="admin_phrases")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def prev_page(callback: CallbackQuery):
    current = temp_page.get(callback.from_user.id, {"trigger": "1_DAY_INACTIVE", "page": 1, "total": 0})
    total = current["total"]
    max_page = max(1, (total + 14) // 15)
    prev_page_num = current["page"] - 1
    if prev_page_num < 1:
        prev_page_num = max_page
    offset = (prev_page_num - 1) * 15
    phrases = await get_phrases_by_trigger(current["trigger"], limit=15, offset=offset)
    temp_page[callback.from_user.id] = {"trigger": current["trigger"], "page": prev_page_num, "total": total}
    text = f"📝 Фразы ({current['trigger']}) — страница {prev_page_num}/{max_page}:\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i + offset}. {p['phrase_text']} {p['emoji'] or ''}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_phrase")],
        [InlineKeyboardButton(text="➖ Убрать", callback_data="remove_phrase")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_page")],
        [InlineKeyboardButton(text="🔙 К выбору триггера", callback_data="admin_phrases")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

# ===== ДОБАВЛЕНИЕ ФРАЗ =====

async def start_add_phrase(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Только админ может добавлять фразы!", show_alert=True)
    await callback.message.answer(
        "✍️ Введи фразу в формате:\n"
        "`текст | эмодзи`\n"
        "Пример: `Где ты был? | 😰`"
    )
    await state.set_state(PhraseBuilder.waiting_for_full_phrase)

async def cancel_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id in temp_phrases:
        del temp_phrases[callback.from_user.id]
    await callback.message.edit_text("❌ Добавление отменено.")

async def get_full_phrase(message: Message, state: FSMContext):
    # Проверяем, админ ли пользователь
    if not is_admin(message.from_user.id):
        await message.answer("❌ Только админы могут добавлять фразы!")
        await state.clear()
        return
    
    parts = message.text.split('|', 1)
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Нужно: `текст | эмодзи`\nПример: `Где ты был? | 😰`")
        return
    text = parts[0].strip()
    emoji = parts[1].strip()
    if not text or not emoji:
        await message.answer("❌ Текст и эмодзи не могут быть пустыми!")
        return
    temp_phrases[message.from_user.id] = {"text": text, "emoji": emoji}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 день неактива", callback_data="trigger_1DAY")],
        [InlineKeyboardButton(text="Несколько дней неактива", callback_data="trigger_2PLUS")],
        [InlineKeyboardButton(text="Возвращение после перерыва", callback_data="trigger_RESUMED")],
        [InlineKeyboardButton(text="Достижения стрика", callback_data="trigger_STREAK")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")]
    ])
    await message.answer("📌 Выбери триггер для этой фразы:", reply_markup=kb)
    await state.set_state(PhraseBuilder.waiting_for_trigger)

async def get_trigger(callback: CallbackQuery, state: FSMContext):
    trigger_map = {
        "trigger_1DAY": "1_DAY_INACTIVE",
        "trigger_2PLUS": "2_PLUS_DAYS_INACTIVE",
        "trigger_RESUMED": "ACTIVITY_RESUMED_AFTER_BREAK",
        "trigger_STREAK": "STREAK_ACHIEVEMENT"
    }
    trigger = trigger_map.get(callback.data)
    if not trigger:
        return await callback.answer("❌ Неверный триггер!", show_alert=True)
    
    temp_phrases[callback.from_user.id]["trigger"] = trigger
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😰 ANXIOUS", callback_data="mood_ANXIOUS")],
        [InlineKeyboardButton(text="😡 ANGRY", callback_data="mood_ANGRY")],
        [InlineKeyboardButton(text="😏 SARCASTIC", callback_data="mood_SARCASTIC")],
        [InlineKeyboardButton(text="💪 MOTIVATIONAL", callback_data="mood_MOTIVATIONAL")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")]
    ])
    await callback.message.edit_text("🎭 Теперь выбери настроение:", reply_markup=kb)
    await state.set_state(PhraseBuilder.waiting_for_mood)

async def get_mood(callback: CallbackQuery, state: FSMContext):
    mood = callback.data.replace("mood_", "")
    temp_phrases[callback.from_user.id]["mood"] = mood
    data = temp_phrases[callback.from_user.id]
    preview = (
        f"📝 **Новая фраза:**\n"
        f"\"{data['text']}\"\n"
        f"Эмодзи: {data['emoji']}\n"
        f"!триггер: {data['trigger']}\n"
        f"{{настроение: {mood}}}\n\n"
        f"Сохранить?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="confirm_save")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")]
    ])
    await callback.message.edit_text(preview, reply_markup=kb)
    await state.set_state(PhraseBuilder.confirmation)

async def save_phrase(callback: CallbackQuery, state: FSMContext):
    data = temp_phrases[callback.from_user.id]
    await add_phrase(
        trigger=data['trigger'],
        mood=data['mood'],
        text=data['text'],
        emoji=data['emoji']
    )
    await sync_phrases_to_file()
    await callback.message.edit_text("✅ Фраза успешно добавлена! Файл phrases.txt обновлён.")
    del temp_phrases[callback.from_user.id]
    await state.clear()

# ===== УДАЛЕНИЕ ФРАЗ =====

async def remove_phrase(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Только админ может удалять фразы!", show_alert=True)
    await callback.message.answer("🔢 Введи **номер фразы** из списка, которую хочешь убрать (например, 3):")
    await state.set_state(PhraseRemover.waiting_for_number)

async def process_remove_number(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Только админ может удалять фразы!")
    try:
        number = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Нужно ввести число. Попробуй ещё раз.")
    current = temp_page.get(message.from_user.id, {"trigger": "1_DAY_INACTIVE", "page": 1})
    offset = (current["page"] - 1) * 15
    phrases = await get_phrases_by_trigger(current["trigger"], limit=15, offset=offset)
    if number < 1 or number > len(phrases):
        return await message.answer(f"❌ Введите число от 1 до {len(phrases)}.")
    phrase_to_remove = phrases[number - 1]
    await delete_phrase(phrase_to_remove['id'])
    await sync_phrases_to_file()
    await message.answer(f"✅ Фраза №{number} удалена! Файл phrases.txt обновлён.")
    await state.clear()

# ============================================================
# 10. УПРАВЛЕНИЕ КАРТИНКАМИ (pic/)
# ============================================================

async def admin_images_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список картинок", callback_data="images_list")],
        [InlineKeyboardButton(text="📤 Загрузить картинку", callback_data="upload_image")],
        [InlineKeyboardButton(text="🗑️ Удалить картинку", callback_data="remove_file")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sms")]
    ])
    await callback.message.edit_text("🖼️ Управление картинками без текста:", reply_markup=kb)

async def admin_images_list(callback: CallbackQuery):
    folder = "Content/pic/"
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    files.sort()
    
    total = len(files)
    page = temp_files.get(callback.from_user.id, {}).get("images_page", 1)
    per_page = 10
    max_page = max(1, (total + per_page - 1) // per_page)
    
    if page > max_page:
        page = max_page
    if page < 1:
        page = 1
    
    offset = (page - 1) * per_page
    current_files = files[offset:offset + per_page]
    
    temp_files[callback.from_user.id] = {"images_page": page}
    
    text = f"🖼️ Картинки — страница {page}/{max_page} (всего {total}):\n\n"
    for i, f in enumerate(current_files, 1):
        text += f"{i + offset}. {f}\n"
    if not current_files:
        text += "Пока нет картинок."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_file_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_file_page")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_images")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def upload_new_image(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Только админ!", show_alert=True)
    await callback.message.answer("📤 Отправь картинку (фото или файл). Она сохранится в папку pic/")
    await state.set_state(FileUpload.waiting_for_image)

async def upload_image(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Только админ!")
    
    folder = "Content/pic/"
    os.makedirs(folder, exist_ok=True)
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await message.bot.get_file(file_id)
        file_name = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        file_path = os.path.join(folder, file_name)
        await message.bot.download_file(file.file_path, file_path)
        await message.answer(f"✅ Картинка сохранена: {file_name}")
    elif message.document:
        file_id = message.document.file_id
        file = await message.bot.get_file(file_id)
        file_name = message.document.file_name or f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        file_path = os.path.join(folder, file_name)
        await message.bot.download_file(file.file_path, file_path)
        await message.answer(f"✅ Файл сохранён: {file_name}")
    else:
        await message.answer("❌ Отправь фото или документ.")
        return
    
    await state.clear()

# ============================================================
# 11. УПРАВЛЕНИЕ МЕМАМИ (mems/)
# ============================================================

async def admin_memes_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список мемов", callback_data="memes_list")],
        [InlineKeyboardButton(text="📤 Загрузить мем", callback_data="upload_meme")],
        [InlineKeyboardButton(text="🗑️ Удалить мем", callback_data="remove_file")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sms")]
    ])
    await callback.message.edit_text("📝🖼️ Управление мемами:", reply_markup=kb)

async def admin_memes_list(callback: CallbackQuery):
    folder = "Content/mems/"
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
    
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    files.sort()
    
    total = len(files)
    page = temp_files.get(callback.from_user.id, {}).get("memes_page", 1)
    per_page = 10
    max_page = max(1, (total + per_page - 1) // per_page)
    
    if page > max_page:
        page = max_page
    if page < 1:
        page = 1
    
    offset = (page - 1) * per_page
    current_files = files[offset:offset + per_page]
    
    temp_files[callback.from_user.id] = {"memes_page": page}
    
    text = f"📝🖼️ Мемы — страница {page}/{max_page} (всего {total}):\n\n"
    for i, f in enumerate(current_files, 1):
        text += f"{i + offset}. {f}\n"
    if not current_files:
        text += "Пока нет мемов."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_file_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_file_page")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="admin_memes")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def upload_new_meme(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Только админ!", show_alert=True)
    await callback.message.answer("📤 Отправь мем (фото или файл). Он сохранится в папку mems/")
    await state.set_state(FileUpload.waiting_for_meme)

async def upload_meme(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Только админ!")
    
    folder = "Content/mems/"
    os.makedirs(folder, exist_ok=True)
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await message.bot.get_file(file_id)
        file_name = f"meme_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        file_path = os.path.join(folder, file_name)
        await message.bot.download_file(file.file_path, file_path)
        await message.answer(f"✅ Мем сохранён: {file_name}")
    elif message.document:
        file_id = message.document.file_id
        file = await message.bot.get_file(file_id)
        file_name = message.document.file_name or f"meme_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        file_path = os.path.join(folder, file_name)
        await message.bot.download_file(file.file_path, file_path)
        await message.answer(f"✅ Мем сохранён: {file_name}")
    else:
        await message.answer("❌ Отправь фото или документ.")
        return
    
    await state.clear()

# ============================================================
# 12. УДАЛЕНИЕ ФАЙЛОВ (общее для pic/ и mems/)
# ============================================================

async def remove_file_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌ Только админ!", show_alert=True)
    await callback.message.answer("🔢 Введи **номер файла** из списка картинок или мемов, который хочешь удалить:")
    await state.set_state(FileRemover.waiting_for_number)

async def process_remove_file_number(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Только админ!")
    
    try:
        number = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Нужно ввести число. Попробуй ещё раз.")
    
    user_data = temp_files.get(message.from_user.id, {})
    
    folder = None
    if "images_page" in user_data:
        folder = "Content/pic/"
        page = user_data.get("images_page", 1)
    elif "memes_page" in user_data:
        folder = "Content/mems/"
        page = user_data.get("memes_page", 1)
    else:
        return await message.answer("❌ Сначала открой список картинок или мемов, а потом удаляй.")
    
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    files.sort()
    
    per_page = 10
    offset = (page - 1) * per_page
    current_files = files[offset:offset + per_page]
    
    if number < 1 or number > len(current_files):
        return await message.answer(f"❌ Введите число от 1 до {len(current_files)}.")
    
    file_to_remove = current_files[number - 1]
    file_path = os.path.join(folder, file_to_remove)
    
    try:
        os.remove(file_path)
        await message.answer(f"✅ Файл '{file_to_remove}' удалён!")
    except Exception as e:
        await message.answer(f"❌ Ошибка при удалении: {e}")
    
    await state.clear()

# ===== ПАГИНАЦИЯ ДЛЯ ФАЙЛОВ =====

async def next_file_page(callback: CallbackQuery):
    user_data = temp_files.get(callback.from_user.id, {})
    
    if "images_page" in user_data:
        page_key = "images_page"
        folder = "Content/pic/"
        menu_callback = "admin_images"
    elif "memes_page" in user_data:
        page_key = "memes_page"
        folder = "Content/mems/"
        menu_callback = "admin_memes"
    else:
        return await callback.answer("❌ Сначала открой список.", show_alert=True)
    
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    files.sort()
    total = len(files)
    per_page = 10
    max_page = max(1, (total + per_page - 1) // per_page)
    
    page = user_data.get(page_key, 1) + 1
    if page > max_page:
        page = 1
    
    temp_files[callback.from_user.id] = {page_key: page}
    
    offset = (page - 1) * per_page
    current_files = files[offset:offset + per_page]
    
    text = f"📂 Файлы — страница {page}/{max_page} (всего {total}):\n\n"
    for i, f in enumerate(current_files, 1):
        text += f"{i + offset}. {f}\n"
    if not current_files:
        text += "Пока нет файлов."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_file_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_file_page")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data=menu_callback)]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def prev_file_page(callback: CallbackQuery):
    user_data = temp_files.get(callback.from_user.id, {})
    
    if "images_page" in user_data:
        page_key = "images_page"
        folder = "Content/pic/"
        menu_callback = "admin_images"
    elif "memes_page" in user_data:
        page_key = "memes_page"
        folder = "Content/mems/"
        menu_callback = "admin_memes"
    else:
        return await callback.answer("❌ Сначала открой список.", show_alert=True)
    
    files = [f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    files.sort()
    total = len(files)
    per_page = 10
    max_page = max(1, (total + per_page - 1) // per_page)
    
    page = user_data.get(page_key, 1) - 1
    if page < 1:
        page = max_page
    
    temp_files[callback.from_user.id] = {page_key: page}
    
    offset = (page - 1) * per_page
    current_files = files[offset:offset + per_page]
    
    text = f"📂 Файлы — страница {page}/{max_page} (всего {total}):\n\n"
    for i, f in enumerate(current_files, 1):
        text += f"{i + offset}. {f}\n"
    if not current_files:
        text += "Пока нет файлов."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="prev_file_page"),
         InlineKeyboardButton(text="📄 Далее", callback_data="next_file_page")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data=menu_callback)]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

# ============================================================
# 13. РАНГОВЫЕ ФРАЗЫ
# ============================================================

async def admin_ranks_list(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT DISTINCT mood FROM phrases WHERE trigger_type = 'RANK' AND is_active = 1"
        )
        rows = await cursor.fetchall()
        ranks = [row[0] for row in rows]
    
    if not ranks:
        return await callback.message.edit_text("🏆 Пока нет ранговых фраз.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for rank in ranks:
        kb.inline_keyboard.append([InlineKeyboardButton(text=rank, callback_data=f"rank_{rank}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sms")])
    
    await callback.message.edit_text("🏆 Выбери ранг, чтобы посмотреть его фразы:", reply_markup=kb)

async def show_rank_phrases(callback: CallbackQuery):
    rank_name = callback.data.replace("rank_", "")
    phrases = await get_phrases_by_trigger("RANK", limit=999, mood=rank_name)
    
    text = f"🏆 Фразы для ранга '{rank_name}':\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i}. {p['phrase_text']} {p['emoji'] or ''}\n"
    if not phrases:
        text += "Пока нет фраз для этого ранга."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к списку рангов", callback_data="admin_ranks")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

# ============================================================
# 14. ОБРАБОТКА ВСЕХ СООБЩЕНИЙ (ОСНОВНАЯ ЛОГИКА)
# ============================================================

async def process_message(message: Message):
    if message.chat.id != CHAT_ID:
        return
    
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    # --- ОБНОВЛЯЕМ ОСНОВНЫЕ МЕТРИКИ ---
    await update_last_message(message.from_user.id)
    await add_coins(message.from_user.id, 0.1)
    await increment_messages_today(message.from_user.id)
    
    current_streak = user['streak'] or 0
    
    # --- ПРОВЕРЯЕМ АКТИВНОЕ ИСКУПЛЕНИЕ ---
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
                f"🎉 **{name}** восстановил свой стрик в {streak_to_restore} дней! "
                f"Он написал {target} сообщений за сутки! Дори впечатлён! 🦊"
            )
            await message.bot.send_message(
                CHAT_ID,
                f"🎉 **{name}** восстановил стрик в {streak_to_restore} дней, написав {target} сообщений за сутки! 🔥"
            )
            return
        else:
            if progress % 50 == 0:
                remaining = target - progress
                await message.answer(
                    f"📊 **{user.get('name', 'Ты')}**: {progress}/{target} сообщений до восстановления стрика. "
                    f"Осталось {remaining}!"
                )
    
    # --- ПРОВЕРКА РАНГОВ ---
    rank_mapping = {
        0: "Новичок",
        2: "Кандидат",
        5: "Знакомый",
        9: "Хороший",
        16: "Душа",
        24: "Старожил",
        34: "Гордость",
        47: "Авторитет",
        60: "Незаменимый"
    }
    
    for min_streak, rank_name in sorted(rank_mapping.items()):
        if current_streak >= min_streak and user['rank'] != rank_name:
            new_rank = rank_name
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank, user['user_id']))
                await db.commit()
            
            rank_phrase = await get_rank_phrase_by_name(new_rank)
            if rank_phrase:
                await message.answer(f"🏆 Поздравляю! Ты достиг ранга {new_rank}!\n\n{rank_phrase}")
            else:
                await message.answer(f"🏆 Поздравляю! Ты достиг ранга {new_rank}!")
            break
    
    # --- ПРОВЕРКА ДОСТИЖЕНИЙ (ВСЕОБЩЕЕ ПРИЗНАНИЕ) ---
    achievement_days = [7, 14, 31, 99, 356]
    if current_streak in achievement_days:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT 1 FROM rewards_history WHERE user_id = ? AND reward_type = 'achievement' AND streak = ?",
                (user['user_id'], current_streak)
            )
            already_achieved = await cursor.fetchone()
        
        if not already_achieved:
            phrase = await get_streak_achievement(current_streak)
            if not phrase:
                phrase = f"Ты достиг {current_streak} дней стрика! Дори в шоке! 🦊"
            
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            await message.bot.send_message(
                CHAT_ID,
                f"🎉 **{name}** заработал {current_streak}-дневный стрик!\n\n{phrase}",
                disable_notification=False
            )
            
            await add_reward_history(user['user_id'], 'achievement', 0, 0, current_streak)
    
    # --- ОБНОВЛЕНИЕ СТРИКА (если прошло >24 часа с последнего сообщения) ---
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
# 15. ПЛАНИРОВЩИК - ПРОВЕРКА НЕАКТИВНЫХ
# ============================================================

async def check_inactive_users(bot: Bot):
    inactive = await get_inactive_users()
    
    for user in inactive:
        if not user['last_message']:
            continue
        
        hours_since = (datetime.now() - datetime.fromisoformat(user['last_message'])).total_seconds() / 3600
        
        if 24 <= hours_since < 48:
            phrases = await get_phrases_by_trigger("1_DAY_INACTIVE", limit=1)
            if phrases:
                text = f"{phrases[0]['phrase_text']} {phrases[0]['emoji'] or ''}"
                await bot.send_message(user['user_id'], text)
            else:
                await bot.send_message(user['user_id'], "📣 Ты пропал на сутки. Напиши что-нибудь!")
        
        elif hours_since >= 48:
            shield_active = user['shield_until'] and datetime.fromisoformat(user['shield_until']) > datetime.now()
            
            if shield_active:
                await set_shield(user['user_id'], 0)
                await bot.send_message(
                    user['user_id'], 
                    f"🛡️ Твой щит спас стрик! Но он сгорел. Купи новый в /shop."
                )
            else:
                old_streak = user['streak']
                await update_streak(user['user_id'], 0, user['streak_record'])
                
                await start_redemption(user['user_id'], old_streak)
                
                name = user.get('name', user.get('telegram_username', 'Кто-то'))
                
                await bot.send_message(
                    user['user_id'],
                    f"💔 Твой стрик в {old_streak} дней сброшен.\n\n"
                    f"🔄 **НО!** У тебя есть шанс восстановить его!\n"
                    f"Напиши **200 сообщений** в чат за сегодня — и стрик вернётся!\n\n"
                    f"Прогресс можно отслеживать командой **.искупление** или в анкете **/me**. Удачи! 🍀"
                )
                
                await bot.send_message(
                    CHAT_ID,
                    f"😱 **{name}** проиграл стрик в {old_streak} дней!\n"
                    f"Но у него есть шанс восстановить его — написать 200 сообщений за сегодня.\n"
                    f"Следим за ним! 👀"
                )
                
                outcome = random.choice(['phrase', 'meme'])
                if outcome == 'phrase':
                    phrases = await get_phrases_by_trigger("2_PLUS_DAYS_INACTIVE", limit=1)
                    if phrases:
                        text = f"{phrases[0]['phrase_text']} {phrases[0]['emoji'] or ''}"
                        await bot.send_message(user['user_id'], text)
                else:
                    meme_folder = 'Content/mems/'
                    if os.path.exists(meme_folder) and os.listdir(meme_folder):
                        meme_file = random.choice(os.listdir(meme_folder))
                        meme_path = os.path.join(meme_folder, meme_file)
                        await bot.send_photo(user['user_id'], photo=FSInputFile(meme_path))

# ============================================================
# 16. ПЛАНИРОВЩИК - ЕЖЕДНЕВНЫЕ И ЕЖЕНЕДЕЛЬНЫЕ НАГРАДЫ
# ============================================================

async def daily_reset_and_reward(bot: Bot):
    winner = await award_daily_top()
    if winner:
        name = winner.get('name', winner.get('telegram_username', 'Кто-то'))
        await bot.send_message(
            CHAT_ID,
            f"🌟 **{name}** стал лидером по сообщениям за сегодня! +100 коинов! 🪙"
        )
    
    await reset_daily_messages()
    logger.info("🔄 Daily reset completed")

async def weekly_streak_reward(bot: Bot):
    winners = await award_weekly_top()
    
    if winners:
        text = "🏆 **ЕЖЕНЕДЕЛЬНЫЙ ТОП СТРИКОВ**\n\n"
        for user, position, coins in winners:
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            medal = ["🥇", "🥈", "🥉"][position - 1]
            text += f"{medal} **{name}** — {user['streak']} дней стрика (+{coins} коинов)\n"
        
        await bot.send_message(CHAT_ID, text)
        logger.info("🔄 Weekly rewards distributed")

async def check_expired_redemptions_task(bot: Bot):
    expired_users = await check_expired_redemptions()
    
    for user_id in expired_users:
        user = await get_user(user_id)
        if user:
            name = user.get('name', user.get('telegram_username', 'Кто-то'))
            await bot.send_message(
                user_id,
                f"💀 Ты не успел восстановить стрик. Время вышло.\n"
                f"Начинай с нуля, {name}. Ты сможешь! 💪"
            )
            
            await bot.send_message(
                CHAT_ID,
                f"⏰ **{name}** не успел восстановить стрик. "
                f"Теперь он начинает с нуля. Кто следующий? 😈"
            )

# ============================================================
# 17. ВОЗВРАТ В МЕНЮ
# ============================================================

async def back_to_sms(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Фразы", callback_data="admin_phrases")],
        [InlineKeyboardButton(text="🖼️ Картинки без текста", callback_data="admin_images")],
        [InlineKeyboardButton(text="📝🖼️ Картинки с текстом", callback_data="admin_memes")],
        [InlineKeyboardButton(text="🏆 Фразы рангов", callback_data="admin_ranks")],
        [InlineKeyboardButton(text="🔄 Синхронизировать файлы", callback_data="sync_files")]
    ])
    await callback.message.edit_text("📋 Панель управления контентом:", reply_markup=kb)
