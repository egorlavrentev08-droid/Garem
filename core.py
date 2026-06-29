import os
import random
import logging
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
    get_inactive_users, increment_streak
)

# ============================================================
# 0. ФИЛЬТР ПРОВЕРКИ УЧАСТНИКА ЧАТА
# ============================================================

CHAT_ID = -1002497100583
CHAT_LINK = "@Gar3mDi"
ADMIN_IDS = [6595788533, 1903870420]

class ChatMemberFilter(BaseFilter):
    """Проверяет, состоит ли пользователь в чате @Gar3mDi"""
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
# 1. СОСТОЯНИЯ ДЛЯ FSM (конструктор и удаление)
# ============================================================

class PhraseBuilder(StatesGroup):
    waiting_for_text = State()
    waiting_for_emoji = State()
    waiting_for_trigger = State()
    waiting_for_mood = State()
    confirmation = State()

class PhraseRemover(StatesGroup):
    waiting_for_number = State()

temp_phrases = {}
temp_page = {}  # Храним текущую страницу для каждого админа

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
    
    # Обработка всех сообщений для начисления коинов
    dp.message.register(process_message, chat_filter)
    
    # FSM шаги (конструктор фраз)
    dp.message.register(get_phrase_text, PhraseBuilder.waiting_for_text, chat_filter)
    dp.message.register(get_phrase_emoji, PhraseBuilder.waiting_for_emoji, chat_filter)
    dp.callback_query.register(get_trigger, PhraseBuilder.waiting_for_trigger, F.data.startswith("trigger_"))
    dp.callback_query.register(get_mood, PhraseBuilder.waiting_for_mood, F.data.startswith("mood_"))
    dp.callback_query.register(save_phrase, PhraseBuilder.confirmation, F.data == "confirm_save")
    
    # FSM шаги (удаление)
    dp.message.register(process_remove_number, PhraseRemover.waiting_for_number, chat_filter)
    
    # Кнопки меню админа
    dp.callback_query.register(admin_phrases_list, F.data == "admin_phrases")
    dp.callback_query.register(next_page, F.data == "next_page")
    dp.callback_query.register(remove_phrase, F.data == "remove_phrase")
    dp.callback_query.register(start_add_phrase, F.data == "add_phrase")
    dp.callback_query.register(cancel_add, F.data == "cancel_add")
    
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
    else:
        if user['shield_until'] and datetime.fromisoformat(user['shield_until']) > datetime.now():
            await callback.answer("⏳ У тебя уже есть активный щит.", show_alert=True)
        else:
            await set_shield(callback.from_user.id, 36)
            await callback.answer("⚡ Щит активирован на 36 часов!", show_alert=True)

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
        return await message.answer(
            f"❌ Пользователь с идентификатором '{identifier}' не найден.\n"
            "Проверь:\n"
            "- ID (только цифры)\n"
            "- Telegram username (без @)\n"
            "- Имя из /name"
        )
    
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
        return await message.answer(
            f"❌ Пользователь с идентификатором '{identifier}' не найден.\n"
            "Проверь:\n"
            "- ID (только цифры)\n"
            "- Telegram username (без @)\n"
            "- Имя из /name"
        )
    
    await set_shield(user['user_id'], hours)
    await message.answer(f"✅ Щит установлен на {hours} часов для {user.get('name', identifier)} (ID: {user['user_id']})")

# ============================================================
# 5. АДМИНСКОЕ МЕНЮ /sms (с пагинацией по 15 и удалением)
# ============================================================

async def cmd_sms(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Фразы", callback_data="admin_phrases")],
        [InlineKeyboardButton(text="🖼️ Картинки без текста", callback_data="admin_images")],
        [InlineKeyboardButton(text="📝🖼️ Картинки с текстом", callback_data="admin_memes")],
        [InlineKeyboardButton(text="🏆 Фразы рангов", callback_data="admin_ranks")]
    ])
    await message.answer("📋 Панель управления фразами:", reply_markup=kb)

async def admin_phrases_list(callback: CallbackQuery):
    # Получаем 15 фраз для 1 дня неактива (страница 1)
    phrases = await get_phrases_by_trigger("1_DAY_INACTIVE", limit=15, offset=0)
    temp_page[callback.from_user.id] = {"trigger": "1_DAY_INACTIVE", "page": 1}
    
    text = "📝 Фразы (1 день неактива):\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i}. {p['phrase_text']} {p['emoji'] or ''}\n"
    if not phrases:
        text += "Пока нет фраз."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_phrase")],
        [InlineKeyboardButton(text="➖ Убрать", callback_data="remove_phrase")],
        [InlineKeyboardButton(text="📄 Далее", callback_data="next_page")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def next_page(callback: CallbackQuery):
    """Переключает на следующую страницу (следующие 15 фраз)"""
    current = temp_page.get(callback.from_user.id, {"trigger": "1_DAY_INACTIVE", "page": 1})
    next_page_num = current["page"] + 1
    offset = (next_page_num - 1) * 15
    
    phrases = await get_phrases_by_trigger(current["trigger"], limit=15, offset=offset)
    if not phrases:
        return await callback.answer("📄 Это была последняя страница.", show_alert=True)
    
    temp_page[callback.from_user.id] = {"trigger": current["trigger"], "page": next_page_num}
    
    text = f"📝 Фразы ({current['trigger']}) — страница {next_page_num}:\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i + offset}. {p['phrase_text']} {p['emoji'] or ''}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_phrase")],
        [InlineKeyboardButton(text="➖ Убрать", callback_data="remove_phrase")],
        [InlineKeyboardButton(text="📄 Далее", callback_data="next_page")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)

async def remove_phrase(callback: CallbackQuery, state: FSMContext):
    """Запускает удаление по номеру"""
    await callback.message.answer("🔢 Введи **номер фразы** из списка, которую хочешь убрать (например, 3):")
    await state.set_state(PhraseRemover.waiting_for_number)

async def process_remove_number(message: Message, state: FSMContext):
    """Обрабатывает ввод номера и удаляет фразу"""
    try:
        number = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Нужно ввести число. Попробуй ещё раз.")
    
    # Получаем текущий список фраз
    current = temp_page.get(message.from_user.id, {"trigger": "1_DAY_INACTIVE", "page": 1})
    offset = (current["page"] - 1) * 15
    phrases = await get_phrases_by_trigger(current["trigger"], limit=15, offset=offset)
    
    if number < 1 or number > len(phrases):
        return await message.answer(f"❌ Введите число от 1 до {len(phrases)}.")
    
    phrase_to_remove = phrases[number - 1]
    await delete_phrase(phrase_to_remove['id'])
    
    await message.answer(f"✅ Фраза №{number} удалена!")
    await state.clear()

async def start_add_phrase(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✍️ Введи текст новой фразы (без эмодзи и триггеров):")
    await state.set_state(PhraseBuilder.waiting_for_text)

async def cancel_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.from_user.id in temp_phrases:
        del temp_phrases[callback.from_user.id]
    await callback.message.edit_text("❌ Добавление отменено.")

# ============================================================
# 6. ОБРАБОТКА ВСЕХ СООБЩЕНИЙ (начисление коинов и стрика)
# ============================================================

async def process_message(message: Message):
    if message.chat.id != CHAT_ID:
        return
    
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    await update_last_message(message.from_user.id)
    await add_coins(message.from_user.id, 0.1)
    
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
# 7. FSM ШАГИ (конструктор с эмодзи)
# ============================================================

async def get_phrase_text(message: Message, state: FSMContext):
    temp_phrases[message.from_user.id] = {"text": message.text}
    await message.answer("✍️ Теперь отправь **эмодзи** для этой фразы (одним сообщением, например: 😰):")
    await state.set_state(PhraseBuilder.waiting_for_emoji)

async def get_phrase_emoji(message: Message, state: FSMContext):
    emoji = message.text.strip()
    temp_phrases[message.from_user.id]["emoji"] = emoji
    
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
    await callback.message.edit_text("✅ Фраза успешно добавлена с эмодзи!")
    del temp_phrases[callback.from_user.id]
    await state.clear()

# ============================================================
# 8. ПЛАНИРОВЩИК
# ============================================================

async def check_inactive_users(bot: Bot):
    inactive = await get_inactive_users()
    
    for user in inactive:
        if not user['last_message']:
            continue
        
        hours_since = (datetime.now() - datetime.fromisoformat(user['last_message'])).total_seconds() / 3600
        
        if hours_since > 48:
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
