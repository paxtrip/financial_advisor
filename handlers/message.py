import logging

from aiogram import Router, F
from aiogram.types import Message

from services.llm import parse_user_message
from services.supabase_client import get_or_create_user, save_transaction
from handlers.edit import handle_edit

router = Router()
logger = logging.getLogger(__name__)


def _format_confirmation(parsed: dict) -> str:
    """Форматирует подтверждение записи для пользователя."""
    type_emoji = "💸" if parsed.get("type") == "expense" else "💰"
    type_text = "Расход" if parsed.get("type") == "expense" else "Доход"
    category = parsed.get("category") or "—"
    store = parsed.get("store_name") or ""
    date = parsed.get("date") or "сегодня"

    store_text = f" ({store})" if store else ""
    items_text = ""
    if parsed.get("items"):
        lines = [f"  • {it['name']} — {it['total']} ₽" for it in parsed["items"]]
        items_text = "\n" + "\n".join(lines)

    return (
        f"{type_emoji} <b>{type_text} записан</b>\n"
        f"Сумма: <b>{parsed['amount']} ₽</b>\n"
        f"Категория: {category}{store_text}\n"
        f"Дата: {date}"
        f"{items_text}"
    )


@router.message(F.text)
async def handle_text_message(message: Message):
    user = message.from_user
    get_or_create_user(user.id, user.username, user.first_name)

    try:
        parsed, raw_data = await parse_user_message(message.text)
    except Exception as e:
        logger.error(f"Ошибка парсинга LLM: {e}")
        await message.answer("Произошла ошибка при обработке сообщения. Попробуй ещё раз.")
        return

    # Обработка по intent
    if parsed.intent in ("add_expense", "add_income"):
        # Нужно уточнение?
        if parsed.clarification_needed:
            await message.answer(parsed.clarification_needed)
            return

        if not parsed.amount:
            await message.answer("Не удалось определить сумму. Напиши, сколько ты потратил?")
            return

        # Склеиваем дату и время в ISO-формат для TIMESTAMPTZ
        receipt_datetime = parsed.date
        if receipt_datetime and parsed.time:
            receipt_datetime = f"{parsed.date}T{parsed.time}"

        tx_data = {
            "type": parsed.type or ("expense" if parsed.intent == "add_expense" else "income"),
            "amount": parsed.amount,
            "category": parsed.category,
            "store_name": parsed.store_name,
            "description": parsed.description,
            "date": receipt_datetime,
            "source": "text",
            "raw_input": message.text,
            "llm_raw": parsed.model_dump(),
            "items": [item.model_dump() for item in parsed.items],
        }

        try:
            tx = save_transaction(user.id, tx_data)
            confirmation = _format_confirmation(tx_data)
            await message.answer(confirmation, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
            await message.answer("Ошибка при сохранении записи. Попробуй ещё раз.")

    elif parsed.intent == "report":
        await message.answer("📊 Функция отчётов скоро будет доступна. Пока используй /report")

    elif parsed.intent == "edit":
        await handle_edit(message, raw_data)

    elif parsed.intent == "question":
        await message.answer("Пока я умею только записывать расходы и доходы. Функция вопросов появится позже.")

    elif parsed.intent == "unclear":
        text = parsed.clarification_needed or "Не понял тебя. Напиши о расходе или доходе, например: «Потратил 500 на такси»"
        await message.answer(text)

    else:
        await message.answer("Не понял тебя. Напиши о расходе, например: «Потратил 500 на такси»")
