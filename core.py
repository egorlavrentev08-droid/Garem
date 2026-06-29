from aiogram import F, Bot
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

# Импорт всей логики из code.py
from code import (
    cmd_start, cmd_name, cmd_me, cmd_shop,
    cmd_coins, cmd_bypass, cmd_sms, cmd_rank,
    process_message, process_shop,
    admin_phrases_list, choose_trigger, next_page, prev_page,
    start_add_phrase, cancel_add, get_full_phrase, get_trigger, get_mood, save_phrase,
    remove_phrase, process_remove_number,
    admin_images_menu, admin_images_list, upload_new_image, upload_image,
    admin_memes_menu, admin_memes_list, upload_new_meme, upload_meme,
    remove_file_menu, process_remove_file_number, next_file_page, prev_file_page,
    admin_ranks_list, show_rank_phrases,
    back_to_sms, sync_files,
    check_inactive_users
)

# ============================================================
# 0. ФИЛЬТР И НАСТРОЙКИ
# ============================================================

CHAT_ID = -1002497100583
CHAT_LINK = "@Gar3mDi"
ADMIN_IDS = [6595788533, 1903870420]

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

class ChooseTrigger(StatesGroup):
    waiting_for_trigger = State()

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
    
    # FSM - выбор триггера
    dp.callback_query.register(choose_trigger, ChooseTrigger.waiting_for_trigger, F.data.startswith("trigger_"))
    
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
