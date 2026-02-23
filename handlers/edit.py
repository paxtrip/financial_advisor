import logging

from aiogram import Router
from aiogram.types import Message

from services.supabase_client import get_last_transactions, delete_transaction

router = Router()
logger = logging.getLogger(__name__)


# Этот модуль будет расширен позже.
# Пока — заглушка. Вызывается из handlers/message.py по intent="edit".
