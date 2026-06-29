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
    sync_all_files, sync_phrases_to_file, sync_ranks_to_file
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

temp_phrases = {}
temp_page = {}
temp_files = {}

# ============================================================
# 2. РЕГИСТРАЦИЯ ХЕНДЛЕРОВ
# ============================================================

def register_handlers(dp):
    # Команды пользователей
    dp.message.register(cmd_start, Command("start"), chat_filter)
    dp.message.register(cmd_name, Command("name"), chat_filter)
    dp.message.register(cmd_me, Command("me", "profile"), chat_filter)
    dp.message.register(cmd_shop, Command("shop"), chat_filter)
    
    # Команды админов
    dp.message.register(cmd_coins, Command("coins"), chat_filter)
    dp.message.register(cmd_bypass, Command("bypass"), chat_filter)
    dp.message.register(cmd_sms, Command("sms"), chat_filter)
    dp.message.register(cmd_rank, Command("rank"), chat_filter)
    
    # Обработка всех сообщений
    dp.message.register(process_message, chat_filter)
    
    # FSM - фразы
    dp.message.register(get_full_phrase, PhraseBuilder.waiting_for_full_phrase, chat_filter)
    dp.callback_query.register(get_trigger, PhraseBuilder.waiting_for_trigger, F.data.startswith("trigger_"))
    dp.callback_query.register(get_mood, PhraseBuilder.waiting_for_mood, F.data.startswith("mood_"))
    dp.callback_query.register(save_phrase, PhraseBuilder.confirmation, F.data == "confirm_save")
    
    # FSM - удаление фраз
    dp.message.register(process_remove_number, PhraseRemover.waiting_for_number, chat_filter)
    
    # FSM - загрузка файлов
    dp.message.register(upload_image, FileUpload.waiting_for_image, chat_filter)
    dp.message.register(upload_meme, FileUpload.waiting_for_meme, chat_filter)
    
    # FSM - удаление файлов
    dp.message.register(process_remove_file_number, FileRemover.waiting_for_number, chat_filter)
    
    # Кнопки меню админа
    dp.callback_query.register(admin_phrases_list, F.data == "admin_phrases")
    dp.callback_query.register(admin_images_menu, F.data == "admin_images")
    dp.callback_query.register(admin_memes_menu, F.data == "admin_memes")
    dp.callback_query.register(next_page, F.data == "next_page")
    dp.callback_query.register(prev_page, F.data == "prev_page")
    dp.callback_query.register(remove_phrase, F.data == "remove_phrase")
    dp.callback_query.register(start_add_phrase, F.data == "add_phrase")
    dp.callback_query.register(cancel_add, F.data == "cancel_add")
    dp.callback_query.register(sync_files, F.data == "sync_files")
    
    # Кнопки для файлов
    dp.callback_query.register(admin_images_list, F.data == "images_list")
    dp.callback_query.register(admin_memes_list, F.data == "memes_list")
    dp.callback_query.register(upload_new_image, F.data == "upload_image")
    dp.callback_query.register(upload_new_meme, F.data == "upload_meme")
    dp.callback_query.register(remove_file_menu, F.data == "remove_file")
    dp.callback_query.register(next_file_page, F.data == "next_file_page")
    dp.callback_query.register(prev_file_page, F.data == "prev_file_page")
    dp.callback_query.register(back_to_sms, F.data == "back_to_sms")
    
    # Ранговые фразы
    dp.callback_query.register(admin_ranks_list, F.data == "admin_ranks")
    dp.callback_query.register(show_rank_phrases, F.data.startswith("rank_"))
    dp.callback_query.register(back_to_sms, F.data == "back_to_sms")
    
    # Магазин
    dp.callback_query.register(process_shop, F.data.in_(["buy_shield", "use_shield"]))

# ============================================================
# 3. ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
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
            "/shop - купить щит"
        )

async def cmd_name(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("Используй: /name ТвоёИмя")
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
    text = (
        f"📋 Анкета {user['name'] or 'Без имени'}\n"
        f"| Ранг: {user['rank']}\n"
        f"| Стриков: {user['streak']} дней\n"
        f"| Стриков Рекорд: {user['streak_record']} дней\n"
        f"| Коинов: {user['coins']:.1f}\n"
        f"| Щит действует: {shield_status}"
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
# 4. АДМИНСКИЕ КОМАНДЫ
# ============================================================

async def cmd_coins(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    args = message.text.split()
    if len(args) < 4 or args[1] not in ['give', 'take']:
        return await message.answer("Используй: /coins give/take @username (n) или /coins give/take user_id (n)")
    
    action = args[1]
    identifier = args[2].replace('@', '')
    try:
        amount = float(args[3])
    except ValueError:
        return await message.answer("❌ Сумма должна быть числом.")
    
    user = await get_user_by_identifier(identifier)
    if not user:
        return await message.answer(f"❌ Пользователь с идентификатором '{identifier}' не найден.")
    
    await add_coins(user['user_id'], amount if action == 'give' else -amount)
    await message.answer(f"✅ Коины обновлены: {action} {amount} для {user.get('name', identifier)} (ID: {user['user_id']})")

async def cmd_bypass(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Используй: /bypass @username (часы) или /bypass user_id (часы)")
    
    identifier = args[1].replace('@', '')
    try:
        hours = int(args[2])
    except ValueError:
        return await message.answer("❌ Часы должны быть числом.")
    
    user = await get_user_by_identifier(identifier)
    if not user:
        return await message.answer(f"❌ Пользователь с идентификатором '{identifier}' не найден.")
    
    await set_shield(user['user_id'], hours)
    await message.answer(f"✅ Щит установлен на {hours} часов для {user.get('name', identifier)} (ID: {user['user_id']})")

async def cmd_rank(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Используй: /rank @username <название_ранга>")
    
    identifier = args[1].replace('@', '')
    new_rank = args[2].strip()
    
    user = await get_user_by_identifier(identifier)
    if not user:
        return await message.answer(f"❌ Пользователь с идентификатором '{identifier}' не найден.")
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET rank = ? WHERE user_id = ?", (new_rank, user['user_id']))
        await db.commit()
    
    rank_phrase = await get_rank_phrase_by_name(new_rank)
    if rank_phrase:
        await message.answer(f"🏆 Ранг пользователя {user.get('name', identifier)} изменён на {new_rank}.\n\n{rank_phrase}")
    else:
        await message.answer(f"✅ Ранг изменён на {new_rank}.")

# ============================================================
# 5. АДМИНСКОЕ МЕНЮ /sms (полное)
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
# 6. УПРАВЛЕНИЕ ФРАЗАМИ (как было)
# ============================================================

async def admin_phrases_list(callback: CallbackQuery):
    trigger = "1_DAY_INACTIVE"
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
         InlineKeyboardButton(text="📄 Далее", callback_data="next_page")]
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
         InlineKeyboardButton(text="📄 Далее", callback_data="next_page")]
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
         InlineKeyboardButton(text="📄 Далее", callback_data="next_page")]
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

async def get_full_phrase(message: Message, state: FSMContext):
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
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")]
    ])
    await message.answer("📌 Выбери триггер для этой фразы:", reply_markup=kb)
    await state.set_state(PhraseBuilder.waiting_for_trigger)

async def get_trigger(callback: CallbackQuery, state: FSMContext):
    trigger_map = {
        "trigger_1DAY": "1_DAY_INACTIVE",
        "trigger_2PLUS": "2_PLUS_DAYS_INACTIVE",
        "trigger_RESUMED": "ACTIVITY_RESUMED_AFTER_BREAK"
    }
    trigger = trigger_map[callback.data]
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
# 7. УПРАВЛЕНИЕ КАРТИНКАМИ (pic/)
# ============================================================

async def admin_images_menu(callback: CallbackQuery):
    """Меню управления картинками без текста"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список картинок", callback_data="images_list")],
        [InlineKeyboardButton(text="📤 Загрузить картинку", callback_data="upload_image")],
        [InlineKeyboardButton(text="🗑️ Удалить картинку", callback_data="remove_file")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sms")]
    ])
    await callback.message.edit_text("🖼️ Управление картинками без текста:", reply_markup=kb)

async def admin_images_list(callback: CallbackQuery):
    """Показывает список картинок в папке pic/"""
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
# 8. УПРАВЛЕНИЕ МЕМАМИ (mems/)
# ============================================================

async def admin_memes_menu(callback: CallbackQuery):
    """Меню управления мемами (картинки с текстом)"""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список мемов", callback_data="memes_list")],
        [InlineKeyboardButton(text="📤 Загрузить мем", callback_data="upload_meme")],
        [InlineKeyboardButton(text="🗑️ Удалить мем", callback_data="remove_file")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_sms")]
    ])
    await callback.message.edit_text("📝🖼️ Управление мемами:", reply_markup=kb)

async def admin_memes_list(callback: CallbackQuery):
    """Показывает список мемов в папке mems/"""
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
# 9. УДАЛЕНИЕ ФАЙЛОВ (общее для pic/ и mems/)
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
    
    # Определяем, из какой папки удаляем
    # Проверяем последний просмотр — если были в pic/ или mems/
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
# 10. РАНГОВЫЕ ФРАЗЫ
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
# 11. ОБРАБОТКА ВСЕХ СООБЩЕНИЙ
# ============================================================

async def process_message(message: Message):
    if message.chat.id != CHAT_ID:
        return
    
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    await update_last_message(message.from_user.id)
    await add_coins(message.from_user.id, 0.1)
    
    current_streak = user['streak'] or 0
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
# 12. ПЛАНИРОВЩИК
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
                await update_streak(user['user_id'], 0, user['streak_record'])
                
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
                    else:
                        await bot.send_message(user['user_id'], "💔 Стрик сброшен. Начни заново.")

# ============================================================
# 13. ВОЗВРАТ В МЕНЮ
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

# ===== ОТМЕНА ДОБАВЛЕНИЯ =====

async def cancel_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id in temp_phrases:
        del temp_phrases[callback.from_user.id]
    await callback.message.edit_text("❌ Добавление отменено.")
