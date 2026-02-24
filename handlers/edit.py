import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from models.schemas import EditRequest
from services.supabase_client import (
    get_last_transactions,
    delete_transaction,
    update_transaction,
    find_category_by_name,
    add_tags_to_transaction,
)
from utils.tag_parser import normalize_tags

router = Router()
logger = logging.getLogger(__name__)


class TagStates(StatesGroup):
    waiting_for_tags = State()


def _format_transaction(tx: dict) -> str:
    """Форматирует транзакцию для показа пользователю."""
    type_emoji = "💸" if tx.get("type") == "expense" else "💰"
    amount = tx.get("amount", 0)
    category = tx.get("categories", {})
    cat_name = category.get("name", "—") if category else "—"
    store = tx.get("stores", {})
    store_name = store.get("name", "") if store else ""
    description = tx.get("description") or ""
    date = tx.get("receipt_date") or tx.get("created_at", "")[:10]

    store_text = f" ({store_name})" if store_name else ""
    desc_text = f"\n📝 {description}" if description else ""

    return (
        f"{type_emoji} <b>{amount} ₽</b> — {cat_name}{store_text}\n"
        f"📅 {date}{desc_text}"
    )


def _find_transaction_by_filter(transactions: list[dict], amount_filter: float | None) -> dict | None:
    """Находит транзакцию по фильтру суммы среди последних."""
    if not transactions:
        return None
    if amount_filter is not None:
        for tx in transactions:
            if tx.get("amount") == amount_filter:
                return tx
    return transactions[0]


async def handle_edit(message: Message, parsed_data: dict):
    """Обрабатывает intent=edit из message.py."""
    user_id = message.from_user.id

    try:
        edit_req = EditRequest.model_validate(parsed_data)
    except Exception as e:
        logger.error(f"Ошибка валидации EditRequest: {e}")
        await message.answer("Не удалось разобрать запрос на редактирование. Попробуй переформулировать.")
        return

    if edit_req.clarification_needed:
        await message.answer(edit_req.clarification_needed)
        return

    # Получаем последние транзакции для поиска
    transactions = get_last_transactions(user_id, limit=10)
    if not transactions:
        await message.answer("У тебя пока нет записей для редактирования.")
        return

    tx = _find_transaction_by_filter(transactions, edit_req.amount_filter)
    if not tx:
        await message.answer("Не нашёл подходящую запись. Попробуй уточнить.")
        return

    tx_id = tx["id"]

    if edit_req.action == "delete":
        text = f"🗑 <b>Удалить эту запись?</b>\n\n{_format_transaction(tx)}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del:{tx_id}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel"),
            ]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    elif edit_req.action == "update":
        if not edit_req.field or not edit_req.new_value:
            await message.answer("Что именно изменить? Укажи поле и новое значение, например: «Измени сумму последней траты на 300»")
            return

        field_names = {"amount": "Сумма", "category": "Категория", "description": "Описание"}
        field_display = field_names.get(edit_req.field, edit_req.field)

        # Текущее значение
        if edit_req.field == "amount":
            old_value = str(tx.get("amount", "—"))
        elif edit_req.field == "category":
            cat = tx.get("categories", {})
            old_value = cat.get("name", "—") if cat else "—"
        elif edit_req.field == "description":
            old_value = tx.get("description") or "—"
        else:
            old_value = "—"

        text = (
            f"✏️ <b>Изменить запись?</b>\n\n"
            f"{_format_transaction(tx)}\n\n"
            f"<b>{field_display}:</b> {old_value} → {edit_req.new_value}"
        )

        # Кодируем callback_data: upd:{tx_id}:{field}:{new_value}
        # Ограничение 64 байта — используем короткие префиксы
        cb_data = f"upd:{tx_id}:{edit_req.field}:{edit_req.new_value}"
        if len(cb_data.encode("utf-8")) > 64:
            # Слишком длинный — обрезаем new_value
            max_val_len = 64 - len(f"upd:{tx_id}:{edit_req.field}:".encode("utf-8"))
            truncated = edit_req.new_value
            while len(f"upd:{tx_id}:{edit_req.field}:{truncated}".encode("utf-8")) > 64:
                truncated = truncated[:-1]
            cb_data = f"upd:{tx_id}:{edit_req.field}:{truncated}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=cb_data),
                InlineKeyboardButton(text="❌ Отмена", callback_data="edit_cancel"),
            ]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    else:
        await message.answer("Не понял действие. Скажи «удали» или «измени».")


# --- Callback обработчики ---

@router.callback_query(F.data.startswith("del:"))
async def callback_delete(callback: CallbackQuery):
    """Подтверждение удаления."""
    tx_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    success = delete_transaction(tx_id, user_id)

    if success:
        await callback.message.edit_text("✅ Запись удалена.", parse_mode="HTML")
    else:
        await callback.message.edit_text("⚠️ Запись не найдена — возможно, уже удалена.", parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data.startswith("upd:"))
async def callback_update(callback: CallbackQuery):
    """Подтверждение редактирования."""
    parts = callback.data.split(":", 3)  # upd:tx_id:field:new_value
    if len(parts) != 4:
        await callback.message.edit_text("⚠️ Ошибка данных кнопки.")
        await callback.answer()
        return

    _, tx_id_str, field, new_value = parts
    tx_id = int(tx_id_str)
    user_id = callback.from_user.id

    updates = {}
    if field == "amount":
        try:
            updates["amount"] = float(new_value)
        except ValueError:
            await callback.message.edit_text("⚠️ Неверный формат суммы.")
            await callback.answer()
            return
    elif field == "category":
        category = find_category_by_name(user_id, new_value)
        if not category:
            await callback.message.edit_text(f"⚠️ Категория «{new_value}» не найдена.")
            await callback.answer()
            return
        updates["category_id"] = category["id"]
    elif field == "description":
        updates["description"] = new_value
    else:
        await callback.message.edit_text("⚠️ Неизвестное поле для редактирования.")
        await callback.answer()
        return

    result = update_transaction(tx_id, user_id, updates)

    if result:
        await callback.message.edit_text("✅ Запись обновлена.", parse_mode="HTML")
    else:
        await callback.message.edit_text("⚠️ Не удалось обновить — запись не найдена.", parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data == "edit_cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена операции."""
    await state.clear()
    await callback.message.edit_text("↩️ Операция отменена.")
    await callback.answer()


# --- Теги ---

@router.callback_query(F.data.startswith("tag_add:"))
async def callback_tag_add(callback: CallbackQuery, state: FSMContext):
    """Запрашивает теги для транзакции."""
    tx_id = int(callback.data.split(":")[1])
    await state.set_state(TagStates.waiting_for_tags)
    await state.update_data(tag_tx_id=tx_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🏷 Напиши теги через пробел или запятую.\n"
        "Можно с # или без: <code>дача работа праздник</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(TagStates.waiting_for_tags, F.text)
async def handle_tag_input(message: Message, state: FSMContext):
    """Сохраняет введённые теги к транзакции."""
    data = await state.get_data()
    tx_id = data.get("tag_tx_id")
    user_id = message.from_user.id

    # Парсим ввод: разбиваем по пробелам и запятым
    raw_tags = [t.strip() for t in message.text.replace(",", " ").split()]
    tags = normalize_tags(raw_tags)

    if not tags:
        await state.clear()
        await message.answer("Не распознал теги. Попробуй ещё раз.")
        return

    saved = add_tags_to_transaction(tx_id, user_id, tags)
    await state.clear()

    if saved:
        tags_text = " ".join(f"#{t}" for t in saved)
        await message.answer(f"✅ Теги добавлены: {tags_text}")
    else:
        await message.answer("Эти теги уже были добавлены к записи.")
