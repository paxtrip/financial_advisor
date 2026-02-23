import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

PROVERKACHEKA_URL = "https://proverkacheka.com/api/v1/check/get"


async def fetch_receipt_by_qr(qr_raw: str) -> dict | None:
    """
    Получает данные чека по содержимому QR-кода через proverkacheka.com.

    qr_raw — строка вида: t=20260222T1830&s=847.00&fn=1234567890&i=12345&fp=1234567890&n=1

    Возвращает dict с данными чека или None при ошибке.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                PROVERKACHEKA_URL,
                json={"token": settings.PROVERKACHEKA_TOKEN, "qrraw": qr_raw},
            )

        if response.status_code != 200:
            logger.warning(f"proverkacheka вернул {response.status_code}")
            return None

        data = response.json()
        if data.get("code") != 1:
            logger.warning(f"proverkacheka error: {data}")
            return None

        receipt = data["data"]["json"]

        # Логируем все ключи и значения (кроме items) для отладки
        debug_fields = {k: v for k, v in receipt.items() if k != "items"}
        logger.info(f"Поля чека: {debug_fields}")

        # retailPlace = торговая марка ("Магазин Абсолют", "Народный")
        # user = юрлицо (ИП Иванов, ООО "Рога и копыта")
        # Адрес может быть в разных полях
        retail_place = receipt.get("retailPlace", "")
        organization = receipt.get("user", "")
        address = (
            receipt.get("retailPlaceAddres")
            or receipt.get("retailPlaceAddress")
            or receipt.get("buyerAddress")
            or receipt.get("sellerAddress")
            or ""
        )

        # Имя магазина: приоритет — торговая марка, потом юрлицо
        store_name = retail_place or organization

        return {
            "store_name": store_name,
            "store_organization": organization,
            "store_address": address,
            "retail_place": retail_place,
            "date": receipt.get("dateTime", ""),
            "total": receipt.get("totalSum", 0) / 100,  # копейки → рубли
            "items": [
                {
                    "name": item.get("name", ""),
                    "quantity": item.get("quantity", 1),
                    "price": item.get("price", 0) / 100,
                    "total": item.get("sum", 0) / 100,
                }
                for item in receipt.get("items", [])
            ],
        }

    except Exception as e:
        logger.error(f"Ошибка proverkacheka: {e}")
        return None
