import json
import logging
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.llm import generate_report
from services.supabase_client import (
    get_transactions,
    get_category_breakdown,
    get_user_tags,
    get_transactions_by_tag,
    get_category_breakdown_by_tag,
)
from utils.tag_parser import extract_tags_from_text

router = Router()
logger = logging.getLogger(__name__)


def _month_range() -> tuple[str, str]:
    """Возвращает (date_from, date_to) для текущего месяца."""
    today = date.today()
    date_from = today.replace(day=1).isoformat()
    date_to = (today + timedelta(days=1)).isoformat()
    return date_from, date_to


async def _send_report(message: Message, transactions: list, breakdown: list, title: str):
    """Формирует и отправляет отчёт через LLM или fallback."""
    if not transactions:
        await message.answer(f"По запросу «{title}» записей нет.")
        return

    try:
        report_data = {"transactions": transactions, "category_breakdown": breakdown}
        transactions_json = json.dumps(report_data, ensure_ascii=False, default=str)
        report_text = await generate_report(transactions_json)
        await message.answer(report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка генерации отчёта: {e}")
        total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
        total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        await message.answer(
            f"📊 <b>{title}</b>\n\n"
            f"Расходы: <b>{total_expense:.0f} ₽</b>\n"
            f"Доходы: <b>{total_income:.0f} ₽</b>\n"
            f"Записей: {len(transactions)}",
            parse_mode="HTML",
        )


@router.message(Command("report"))
async def cmd_report(message: Message):
    user = message.from_user
    date_from, date_to = _month_range()

    # Проверяем, передан ли тег прямо в команде: /report #дача
    command_text = message.text or ""
    _, tags_in_command = extract_tags_from_text(command_text)

    # Также проверяем аргументы без # — /report дача
    parts = command_text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    tag_from_arg = arg.lstrip("#").lower() if arg and not arg.startswith("/") else ""

    tag_filter = (tags_in_command[0] if tags_in_command else tag_from_arg) or None

    if tag_filter:
        await message.answer(f"📊 Готовлю отчёт по тегу #{tag_filter}...")
        transactions = get_transactions_by_tag(user.id, tag_filter, date_from, date_to)
        breakdown = get_category_breakdown_by_tag(user.id, tag_filter, date_from, date_to)
        await _send_report(message, transactions, breakdown, f"#{tag_filter}")
        return

    # Без тега — стандартный отчёт + кнопки тегов если они есть
    await message.answer("📊 Готовлю отчёт...")
    transactions = get_transactions(user.id, date_from, date_to)

    if not transactions:
        await message.answer("За этот месяц записей нет. Начни записывать расходы!")
        return

    breakdown = get_category_breakdown(user.id, date_from, date_to)
    await _send_report(message, transactions, breakdown, f"Месяц {date.today().strftime('%B %Y')}")

    # Показываем кнопки тегов если у пользователя есть теги
    user_tags = get_user_tags(user.id)
    if user_tags:
        # Показываем до 8 тегов в кнопках (по 2 в ряд)
        buttons = [
            InlineKeyboardButton(text=f"#{t['name']}", callback_data=f"report_tag:{t['name']}")
            for t in user_tags[:8]
        ]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        await message.answer(
            "🏷 Отфильтровать по тегу:",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("report_tag:"))
async def callback_report_tag(callback: CallbackQuery):
    """Отчёт по конкретному тегу из кнопки."""
    tag_name = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    date_from, date_to = _month_range()

    await callback.message.edit_text(f"📊 Готовлю отчёт по тегу #{tag_name}...")
    await callback.answer()

    transactions = get_transactions_by_tag(user_id, tag_name, date_from, date_to)
    breakdown = get_category_breakdown_by_tag(user_id, tag_name, date_from, date_to)
    await _send_report(callback.message, transactions, breakdown, f"#{tag_name}")
