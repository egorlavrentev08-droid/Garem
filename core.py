import os
import logging
from datetime import datetime
from aiogram import F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импорт из database.py
from database import (
    register_user, get_user, update_user_name, update_last_message,
    add_coins, set_shield, update_streak,
    get_phrases_by_trigger, add_phrase, delete_phrase,
    get_inactive_users
)

# ============================================================
# 0. КОНСТАНТЫ И ФИЛЬТРЫ
# ============================================================

CHAT_ID = -1002497100583
ADMIN_IDS = [6595788533, 1903870420]  # Ты можешь добавить ещё

def is_target_chat(message: Message) -> bool:
    """Проверяет, что сообщение из нужного чата или ЛС"""
    return message.chat.id == CHAT_ID or message.chat.type == 'private'

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ============================================================
# 1. СОСТОЯНИЯ ДЛЯ FSM (конструктор фраз)
# ============================================================

class PhraseBuilder(StatesGroup):
    waiting_for_text = State()
    waiting_for_trigger = State()
    waiting_for_mood = State()
    confirmation = State()

# Хранилище временных данных (в памяти, можно заменить на Redis)
temp_phrases = {}  # user_id -> dict

# ============================================================
# 2. РЕГИСТРАЦИЯ ХЕНДЛЕРОВ (вызывается из main.py)
# ============================================================

def register_handlers(dp):
    """Регистрирует все хендлеры в диспетчере"""
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_name, Command("name"))
    dp.message.register(cmd_me, Command("me", "profile"))
    dp.message.register(cmd_shop, Command("shop"))
    dp.message.register(cmd_coins, Command("coins"))
    dp.message.register(cmd_bypass, Command("bypass"))
    dp.message.register(cmd_sms, Command("sms"))
    
    # FSM шаги
    dp.message.register(get_phrase_text, PhraseBuilder.waiting_for_text)
    dp.callback_query.register(get_trigger, PhraseBuilder.waiting_for_trigger, F.data.startswith("trigger_"))
    dp.callback_query.register(get_mood, PhraseBuilder.waiting_for_mood, F.data.startswith("mood_"))
    dp.callback_query.register(save_phrase, PhraseBuilder.confirmation, F.data == "confirm_save")
    
    # Кнопки меню админа
    dp.callback_query.register(admin_phrases_list, F.data == "admin_phrases")
    dp.callback_query.register(start_add_phrase, F.data == "add_phrase")
    dp.callback_query.register(cancel_add, F.data == "cancel_add")
    
    # Магазин
    dp.callback_query.register(process_shop, F.data.in_(["buy_shield", "use_shield"]))

# ============================================================
# 3. ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
# ============================================================

async def cmd_start(message: Message):
    """Регистрация пользователя"""
    if not is_target_chat(message):
        return await message.answer("Чтобы пользоваться ботом, зайди в чат @Gar3mDi")
    
    await register_user(message.from_user.id)
    await message.answer(
        "🦊 Привет! Я Dori — Архитектор Дисциплины.\n"
        "Ты зарегистрирован.\n\n"
        "Используй /name чтобы задать себе имя.\n"
        "/me — твоя анкета.\n"
        "/shop — магазин."
    )

async def cmd_name(message: Message):
    """Установка уникального имени"""
    if not is_target_chat(message):
        return
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
    """Анкета пользователя"""
    if not is_target_chat(message):
        return
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала зарегистрируйся: /start")
    
    shield_status = "🛡️ Активен" if user['shield_until'] and user['shield_until'] > datetime.now() else "❌ Не активен"
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
    """Магазин"""
    if not is_target_chat(message):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🛡️ Купить щит (100 коинов)", callback_data="buy_shield")],
        [InlineKeyboardButton("⚡ Использовать щит (36 часов)", callback_data="use_shield")]
    ])
    await message.answer("🛒 Магазин:", reply_markup=kb)

async def process_shop(callback: CallbackQuery):
    """Обработка кнопок магазина"""
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
    else:  # use_shield
        if user['shield_until'] and user['shield_until'] > datetime.now():
            await callback.answer("⏳ У тебя уже есть активный щит.", show_alert=True)
        else:
            await set_shield(callback.from_user.id, 36)
            await callback.answer("⚡ Щит активирован на 36 часов!", show_alert=True)

# ============================================================
# 4. АДМИНСКИЕ КОМАНДЫ
# ============================================================

async def cmd_coins(message: Message, command: CommandObject):
    """Выдать/забрать коины (только для админов)"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    args = message.text.split()
    if len(args) < 4 or args[1] not in ['give', 'take']:
        return await message.answer("Используй: /coins give/take @username (n)")
    
    action, username, amount = args[1], args[2].replace('@', ''), float(args[3])
    # Получаем пользователя по имени
    # В реальности нужно добавить функцию get_user_by_name() в database.py
    await message.answer(f"✅ Коины обновлены: {action} {amount} (нужна реализация get_user_by_name)")

async def cmd_bypass(message: Message, command: CommandObject):
    """Выдать щит (только для админов)"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Используй: /bypass @username (часы)")
    
    username, hours = args[1].replace('@', ''), int(args[2])
    # Нужна реализация get_user_by_name()
    await message.answer(f"✅ Щит установлен на {hours} часов (нужна реализация get_user_by_name)")

# ============================================================
# 5. АДМИНСКОЕ МЕНЮ /sms
# ============================================================

async def cmd_sms(message: Message):
    """Панель управления фразами"""
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Ты не админ.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("📝 Фразы", callback_data="admin_phrases")],
        [InlineKeyboardButton("🖼️ Картинки без текста", callback_data="admin_images")],
        [InlineKeyboardButton("📝🖼️ Картинки с текстом", callback_data="admin_memes")],
        [InlineKeyboardButton("🏆 Фразы рангов", callback_data="admin_ranks")]
    ])
    await message.answer("📋 Панель управления фразами:", reply_markup=kb)

async def admin_phrases_list(callback: CallbackQuery):
    """Показывает список фраз для выбранного триггера (по умолчанию 1_DAY_INACTIVE)"""
    phrases = await get_phrases_by_trigger("1_DAY_INACTIVE", limit=5)
    text = "📝 Фразы (1 день неактива):\n\n"
    for i, p in enumerate(phrases, 1):
        text += f"{i}. {p['phrase_text']} {p['emoji'] or ''}\n"
    if not phrases:
        text += "Пока нет фраз."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("➕ Добавить", callback_data="add_phrase")],
        [InlineKeyboardButton("➖ Убрать", callback_data="remove_phrase")],
        [InlineKeyboardButton("📄 Далее", callback_data="next_page")]
    ])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

async def start_add_phrase(callback: CallbackQuery, state: FSMContext):
    """Запускает конструктор фраз"""
    await callback.message.answer("✍️ Введи текст новой фразы (без эмодзи и триггеров):")
    await state.set_state(PhraseBuilder.waiting_for_text)
    await callback.answer()

async def cancel_add(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления"""
    await state.clear()
    if callback.from_user.id in temp_phrases:
        del temp_phrases[callback.from_user.id]
    await callback.message.edit_text("❌ Добавление отменено.")
    await callback.answer()

# ============================================================
# 6. FSM ШАГИ (пошаговый конструктор)
# ============================================================

async def get_phrase_text(message: Message, state: FSMContext):
    """Шаг 1: получаем текст фразы"""
    temp_phrases[message.from_user.id] = {"text": message.text}
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("1 день неактива", callback_data="trigger_1DAY")],
        [InlineKeyboardButton("Несколько дней неактива", callback_data="trigger_2PLUS")],
        [InlineKeyboardButton("Возвращение после перерыва", callback_data="trigger_RESUMED")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
    ])
    await message.answer("📌 Выбери триггер для этой фразы:", reply_markup=kb)
    await state.set_state(PhraseBuilder.waiting_for_trigger)

async def get_trigger(callback: CallbackQuery, state: FSMContext):
    """Шаг 2: выбираем триггер"""
    trigger_map = {
        "trigger_1DAY": "1_DAY_INACTIVE",
        "trigger_2PLUS": "2_PLUS_DAYS_INACTIVE",
        "trigger_RESUMED": "ACTIVITY_RESUMED_AFTER_BREAK"
    }
    trigger = trigger_map[callback.data]
    temp_phrases[callback.from_user.id]["trigger"] = trigger
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("😰 ANXIOUS", callback_data="mood_ANXIOUS")],
        [InlineKeyboardButton("😡 ANGRY", callback_data="mood_ANGRY")],
        [InlineKeyboardButton("😏 SARCASTIC", callback_data="mood_SARCASTIC")],
        [InlineKeyboardButton("💪 MOTIVATIONAL", callback_data="mood_MOTIVATIONAL")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
    ])
    await callback.message.edit_text("🎭 Теперь выбери настроение:", reply_markup=kb)
    await state.set_state(PhraseBuilder.waiting_for_mood)
    await callback.answer()

async def get_mood(callback: CallbackQuery, state: FSMContext):
    """Шаг 3: выбираем настроение и показываем предпросмотр"""
    mood = callback.data.replace("mood_", "")
    temp_phrases[callback.from_user.id]["mood"] = mood
    
    data = temp_phrases[callback.from_user.id]
    preview = (
        f"📝 **Новая фраза:**\n"
        f"\"{data['text']}\"\n"
        f"!триггер: {data['trigger']}\n"
        f"{{настроение: {mood}}}\n\n"
        f"Сохранить?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("✅ Сохранить", callback_data="confirm_save")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
    ])
    await callback.message.edit_text(preview, reply_markup=kb)
    await state.set_state(PhraseBuilder.confirmation)
    await callback.answer()

async def save_phrase(callback: CallbackQuery, state: FSMContext):
    """Шаг 4: сохраняем в БД"""
    data = temp_phrases[callback.from_user.id]
    await add_phrase(
        trigger=data['trigger'],
        mood=data['mood'],
        text=data['text'],
        emoji=None  # Эмодзи можно добавить позже
    )
    await callback.message.edit_text("✅ Фраза успешно добавлена!")
    del temp_phrases[callback.from_user.id]
    await state.clear()
    await callback.answer()

# ============================================================
# 7. ПЛАНИРОВЩИК (будет вызван из main.py)
# ============================================================

async def check_inactive_users(bot: Bot):
    """Проверяет бездействие и отправляет напоминания"""
    inactive = await get_inactive_users()
    for user in inactive:
        # Определяем триггер: 1 день или 2+ дней
        hours_since = (datetime.now() - user['last_message']).total_seconds() / 3600
        if hours_since > 48:
            trigger = "2_PLUS_DAYS_INACTIVE"
        else:
            trigger = "1_DAY_INACTIVE"
        
        # Получаем фразу (в реальности с учётом ранга и настроения)
        phrases = await get_phrases_by_trigger(trigger, limit=1)
        if phrases:
            phrase = phrases[0]
            text = f"{phrase['phrase_text']} {phrase['emoji'] or ''}"
            try:
                await bot.send_message(user['user_id'], text)
            except:
                pass  # Если пользователь заблокировал бота
