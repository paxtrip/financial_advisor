import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from handlers import start, photo, reports, edit, message, store_tags

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Регистрация обработчиков (порядок важен: команды и фото до общего текстового)
dp.include_router(start.router)
dp.include_router(reports.router)
dp.include_router(photo.router)
dp.include_router(store_tags.router)  # /store_tag, /my_stores
dp.include_router(edit.router)        # callback-обработчики для inline-кнопок редактирования
dp.include_router(message.router)     # последний — ловит все текстовые сообщения


async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
