import json
import logging
from datetime import date, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.llm import generate_report
from services.supabase_client import get_transactions

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("report"))
async def cmd_report(message: Message):
    user = message.from_user
    await message.answer("📊 Готовлю отчёт...")

    # По умолчанию — текущий месяц
    today = date.today()
    date_from = today.replace(day=1).isoformat()
    # receipt_date — TIMESTAMPTZ, поэтому берём начало следующего дня
    # чтобы записи за сегодня (с любым временем) попали в выборку
    date_to = (today + timedelta(days=1)).isoformat()

    transactions = get_transactions(user.id, date_from, date_to)

    if not transactions:
        await message.answer("За этот месяц записей нет. Начни записывать расходы!")
        return

    # Формируем отчёт через LLM
    try:
        transactions_json = json.dumps(transactions, ensure_ascii=False, default=str)
        report_text = await generate_report(transactions_json)
        await message.answer(report_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка генерации отчёта: {e}")
        # Fallback — простой отчёт без LLM
        total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")
        total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        count = len(transactions)

        await message.answer(
            f"📊 <b>Отчёт за {today.strftime('%B %Y')}</b>\n\n"
            f"Расходы: <b>{total_expense:.0f} ₽</b>\n"
            f"Доходы: <b>{total_income:.0f} ₽</b>\n"
            f"Записей: {count}",
            parse_mode="HTML",
        )
