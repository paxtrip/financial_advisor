import logging

from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from services.supabase_client import get_or_create_user

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    get_or_create_user(user.id, user.username, user.first_name)
    logger.info(f"Пользователь {user.id} ({user.username}) зарегистрирован")

    await message.answer(
        f"Привет, {user.first_name}! Я твой финансовый ассистент.\n\n"
        "Просто напиши мне о покупке, например:\n"
        "«Потратил 500 на такси»\n"
        "«Купил молоко и хлеб в Пятёрочке за 230 руб»\n\n"
        "Или отправь фото чека — я распознаю его автоматически.\n\n"
        "Команды:\n"
        "/report — отчёт за текущий месяц\n"
        "/my_stores — магазины и их теги\n"
        "/store_tag — управление тегами магазина\n"
        "/help — справка"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Что я умею:</b>\n\n"
        "📝 <b>Записать расход</b> — просто напиши, например:\n"
        "  «Потратил 500 на такси»\n"
        "  «Купил молоко 89 руб в Пятёрочке»\n\n"
        "💰 <b>Записать доход</b> — напиши:\n"
        "  «Получил зарплату 80000»\n\n"
        "📸 <b>Распознать чек</b> — отправь фото чека\n\n"
        "📊 <b>Отчёт</b> — /report или напиши:\n"
        "  «Сколько потратил в этом месяце?»\n\n"
        "✏️ <b>Редактирование</b> — напиши:\n"
        "  «Удали последнюю трату»\n"
        "  «Измени сумму на 500»\n\n"
        "🏷 <b>Хештеги</b> — добавляй прямо в текст:\n"
        "  «Купил удобрения 500р #дача»\n"
        "  /report #дача — отчёт по тегу\n\n"
        "🏪 <b>Теги магазинов</b>:\n"
        "  /my_stores — список магазинов с тегами\n"
        "  /store_tag Пятёрочка #продукты — добавить тег\n"
        "  /store_tag Пятёрочка -#продукты — удалить тег",
        parse_mode="HTML",
    )
