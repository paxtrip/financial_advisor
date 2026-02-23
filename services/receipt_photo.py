import logging

from services.llm import parse_receipt_photo
from models.schemas import ParsedReceipt

logger = logging.getLogger(__name__)


async def parse_photo(base64_image: str) -> ParsedReceipt | None:
    """
    Парсит фото чека через Vision LLM.
    Возвращает ParsedReceipt или None при ошибке.
    """
    try:
        result = await parse_receipt_photo(base64_image)

        if result.error:
            logger.warning(f"Vision LLM: {result.error}")
            return None

        return result

    except Exception as e:
        logger.error(f"Ошибка парсинга фото: {e}")
        return None
