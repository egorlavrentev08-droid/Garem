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

# 🔥 ИМПОРТИРУЕМ ТОЛЬКО ИЗ CONFIG
from config import CHAT_ID, CHAT_LINK, ADMIN_IDS, is_admin

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
# ФИЛЬТР
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

# ... ДАЛЬШЕ ВЕСЬ ОСТАЛЬНОЙ КОД core.py (команды, process_message, планировщик)
