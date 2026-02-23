import base64
import logging
from collections import Counter

from aiogram import Router, F
from aiogram.types import Message

from services.llm import categorize_items
from services.receipt_qr import fetch_receipt_by_qr
from services.receipt_photo import parse_photo
from services.supabase_client import get_or_create_user, save_transaction, check_qr_duplicate
from utils.qr_decoder import try_decode_qr

router = Router()
logger = logging.getLogger(__name__)


def _format_receipt_confirmation(receipt_data: dict) -> str:
    """Форматирует подтверждение распознанного чека."""
    store = receipt_data.get("store_name") or "Неизвестный магазин"
    total = receipt_data.get("total", 0)
    date = receipt_data.get("date") or "сегодня"
    address = receipt_data.get("store_address") or ""
    organization = receipt_data.get("store_organization") or ""
    retail_place = receipt_data.get("retail_place") or ""
    items = receipt_data.get("items", [])

    lines = [f"🧾 <b>Чек распознан</b>"]
    lines.append(f"Магазин: <b>{store}</b>")
    if retail_place and retail_place != store:
        lines.append(f"Торговая марка: {retail_place}")
    if organization:
        lines.append(f"Организация: {organization}")
    if address:
        lines.append(f"Адрес: {address}")
    lines.append(f"Сумма: <b>{total} ₽</b>")
    lines.append(f"Дата: {date}")

    if items:
        lines.append(f"\nПозиции ({len(items)}):")
        for item in items[:10]:  # показываем макс. 10 позиций
            name = item.get("name", "—")
            item_total = item.get("total", 0)
            lines.append(f"  • {name} — {item_total} ₽")
        if len(items) > 10:
            lines.append(f"  ... и ещё {len(items) - 10} позиций")

    return "\n".join(lines)


@router.message(F.photo)
async def handle_photo(message: Message):
    user = message.from_user
    get_or_create_user(user.id, user.username, user.first_name)

    await message.answer("📸 Обрабатываю фото...")

    # Скачиваем фото (берём самое большое разрешение)
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    image_bytes = file_bytes.read()

    receipt_data = None
    source = "photo"

    # 1. Пытаемся найти QR-код
    qr_data = try_decode_qr(image_bytes)

    if qr_data:
        logger.info(f"QR найден: {qr_data[:50]}...")
        receipt_data = await fetch_receipt_by_qr(qr_data)
        if receipt_data:
            source = "qr"
            # Категоризируем позиции через LLM
            try:
                categorized = await categorize_items(receipt_data["items"])
                if isinstance(categorized, list):
                    for i, cat_item in enumerate(categorized):
                        if i < len(receipt_data["items"]):
                            receipt_data["items"][i]["category"] = cat_item.get("category")
            except Exception as e:
                logger.warning(f"Ошибка категоризации: {e}")

    # 2. Если QR не найден или proverkacheka не ответил — Vision LLM
    if not receipt_data:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        parsed = await parse_photo(b64)

        if not parsed:
            await message.answer(
                "Не удалось распознать чек. Попробуй сделать фото получше или напиши вручную."
            )
            return

        # Склеиваем дату и время в ISO-формат для TIMESTAMPTZ
        receipt_datetime = parsed.date
        if receipt_datetime and parsed.time:
            receipt_datetime = f"{parsed.date}T{parsed.time}"

        receipt_data = {
            "store_name": parsed.store_name,
            "store_address": parsed.store_address,
            "date": receipt_datetime,
            "total": parsed.total,
            "items": [item.model_dump() for item in parsed.items],
        }

        # Категоризируем позиции через LLM (для Vision-пути)
        if receipt_data.get("items"):
            try:
                categorized = await categorize_items(receipt_data["items"])
                if isinstance(categorized, list):
                    for i, cat_item in enumerate(categorized):
                        if i < len(receipt_data["items"]):
                            receipt_data["items"][i]["category"] = cat_item.get("category")
            except Exception as e:
                logger.warning(f"Ошибка категоризации (vision): {e}")

    # 3. Определяем основную категорию по самой частой среди позиций
    items = receipt_data.get("items", [])
    item_categories = [item.get("category") for item in items if item.get("category")]
    if item_categories:
        main_category = Counter(item_categories).most_common(1)[0][0]
    else:
        main_category = "Продукты"

    # 4. Проверяем дубль QR
    if qr_data and check_qr_duplicate(user.id, qr_data):
        await message.answer("⚠️ Этот чек уже был добавлен ранее.")
        return

    # 5. Сохраняем транзакцию
    tx_data = {
        "type": "expense",
        "amount": receipt_data["total"],
        "category": main_category,
        "store_name": receipt_data.get("store_name"),
        "store_address": receipt_data.get("store_address"),
        "store_organization": receipt_data.get("store_organization"),
        "description": f"Чек на {receipt_data['total']} ₽",
        "date": receipt_data.get("date"),
        "source": source,
        "raw_input": "[фото чека]",
        "llm_raw": receipt_data,
        "items": receipt_data.get("items", []),
        "qr_raw": qr_data,
    }

    try:
        save_transaction(user.id, tx_data)
        confirmation = _format_receipt_confirmation(receipt_data)
        await message.answer(confirmation, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка сохранения чека: {e}")
        await message.answer("Ошибка при сохранении чека. Попробуй ещё раз.")
