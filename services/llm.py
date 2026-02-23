import json
import logging
from datetime import date

import httpx

from config import settings
from models.schemas import ParsedExpense, ParsedReceipt
from prompts.system_prompts import (
    PARSE_MESSAGE_PROMPT,
    PARSE_PHOTO_PROMPT,
    CATEGORIZE_ITEMS_PROMPT,
    REPORT_PROMPT,
)

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def call_llm(
    messages: list[dict],
    model: str | None = None,
    response_format: dict | None = None,
) -> str:
    """Базовый вызов LLM через OpenRouter. Возвращает текст ответа."""
    model = model or settings.LLM_MODEL

    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }
    if response_format:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    logger.debug(f"LLM response: {content[:200]}")
    return content


def _parse_json_response(raw: str) -> dict:
    """Парсит JSON из ответа LLM, убирая возможные markdown-обёртки."""
    text = raw.strip()
    if text.startswith("```"):
        # Убираем ```json ... ```
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


async def parse_user_message(text: str) -> ParsedExpense:
    """Парсит текстовое сообщение пользователя через LLM."""
    current_date = date.today().isoformat()
    prompt = PARSE_MESSAGE_PROMPT.format(current_date=current_date)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text},
    ]

    raw = await call_llm(messages, response_format={"type": "json_object"})
    data = _parse_json_response(raw)
    return ParsedExpense.model_validate(data)


async def parse_receipt_photo(base64_image: str) -> ParsedReceipt:
    """Парсит фото чека через Vision LLM."""
    messages = [
        {"role": "system", "content": PARSE_PHOTO_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Распознай этот чек."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                },
            ],
        },
    ]

    raw = await call_llm(
        messages,
        model=settings.VISION_LLM_MODEL,
        response_format={"type": "json_object"},
    )
    data = _parse_json_response(raw)
    return ParsedReceipt.model_validate(data)


async def categorize_items(items: list[dict]) -> list[dict]:
    """Категоризирует позиции из чека через LLM."""
    items_text = json.dumps(
        [{"name": item["name"]} for item in items], ensure_ascii=False
    )

    messages = [
        {"role": "system", "content": CATEGORIZE_ITEMS_PROMPT},
        {"role": "user", "content": items_text},
    ]

    raw = await call_llm(messages, response_format={"type": "json_object"})
    result = _parse_json_response(raw)

    # LLM с response_format=json_object может обернуть массив в объект,
    # например {"items": [...]} вместо [...]. Извлекаем массив.
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for value in result.values():
            if isinstance(value, list):
                return value
    logger.warning(f"categorize_items: неожиданный формат ответа: {type(result)}")
    return []


async def generate_report(transactions_json: str) -> str:
    """Генерирует текстовый отчёт по транзакциям."""
    messages = [
        {"role": "system", "content": REPORT_PROMPT},
        {"role": "user", "content": f"Вот данные транзакций:\n{transactions_json}"},
    ]

    return await call_llm(messages)
