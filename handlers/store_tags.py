import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.supabase_client import (
    get_user_stores,
    get_store_by_name,
    save_store_tags,
    remove_store_tag,
)
from utils.tag_parser import normalize_tags, extract_tags_from_text

router = Router()
logger = logging.getLogger(__name__)


class StoreTagStates(StatesGroup):
    waiting_for_tags = State()      # ждём теги после выбора магазина кнопкой
    waiting_for_del_tag = State()   # ждём тег для удаления


def _format_store(store: dict) -> str:
    name = store["name"]
    address = f" ({store['address']})" if store.get("address") else ""
    tags = store.get("tags", [])
    tags_text = "  Теги: " + " ".join(f"#{t}" for t in tags) if tags else "  Теги: нет"
    return f"🏪 <b>{name}</b>{address}\n{tags_text}"


# /my_stores — список магазинов с тегами

@router.message(Command("my_stores"))
async def cmd_my_stores(message: Message):
    stores = get_user_stores(message.from_user.id)
    if not stores:
        await message.answer("У тебя пока нет сохранённых магазинов.")
        return

    lines = ["<b>Твои магазины:</b>\n"]
    for store in stores:
        lines.append(_format_store(store))
    await message.answer("\n".join(lines), parse_mode="HTML")


# /store_tag — управление тегами магазина

@router.message(Command("store_tag"))
async def cmd_store_tag(message: Message, state: FSMContext):
    user_id = message.from_user.id
    # Разбираем аргументы: /store_tag [Название] [#тег1 #тег2] [-#тег3]
    parts = (message.text or "").split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        # Без аргументов — показываем кнопки магазинов
        await _show_store_buttons(message, user_id, action="add")
        return

    # Есть аргументы — разбираем название и теги
    # Удаляемые теги начинаются с -#
    tokens = arg.split()
    del_tags = [t[1:] for t in tokens if t.startswith("-#")]
    add_tags_raw = [t for t in tokens if t.startswith("#")]
    # Название — всё до первого тега/флага
    name_tokens = [t for t in tokens if not t.startswith("#") and not t.startswith("-#")]
    store_name = " ".join(name_tokens).strip()

    if not store_name:
        await _show_store_buttons(message, user_id, action="add")
        return

    store = get_store_by_name(user_id, store_name)
    if not store:
        await message.answer(f"Магазин «{store_name}» не найден. Проверь название — оно должно совпадать с тем, как записано в базе.")
        return

    results = []

    # Добавляем теги
    if add_tags_raw:
        tags = normalize_tags(add_tags_raw)
        save_store_tags(store["id"], user_id, tags)
        results.append("Добавлены: " + " ".join(f"#{t}" for t in tags))

    # Удаляем теги
    for tag in del_tags:
        removed = remove_store_tag(store["id"], user_id, tag)
        if removed:
            results.append(f"Удалён: #{tag.lstrip('#').lower()}")
        else:
            results.append(f"Тег #{tag.lstrip('#').lower()} не найден у магазина")

    if not results:
        # Нет тегов — показываем текущее состояние
        updated = get_store_by_name(user_id, store_name)
        stores = get_user_stores(user_id)
        store_full = next((s for s in stores if s["id"] == store["id"]), store)
        await message.answer(_format_store(store_full), parse_mode="HTML")
        return

    store_full_list = get_user_stores(user_id)
    store_full = next((s for s in store_full_list if s["id"] == store["id"]), store)
    text = f"✅ Магазин обновлён:\n\n{_format_store(store_full)}\n\n" + "\n".join(results)
    await message.answer(text, parse_mode="HTML")


async def _show_store_buttons(message: Message, user_id: int, action: str):
    """Показывает список магазинов кнопками."""
    stores = get_user_stores(user_id)
    if not stores:
        await message.answer("У тебя пока нет сохранённых магазинов.")
        return

    buttons = [
        [InlineKeyboardButton(
            text=s["name"],
            callback_data=f"st_{action}:{s['id']}"
        )]
        for s in stores[:20]  # лимит 20 магазинов
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выбери магазин:", reply_markup=keyboard)


# Callbacks после выбора магазина кнопкой

@router.callback_query(F.data.startswith("st_add:"))
async def callback_store_add_tags(callback: CallbackQuery, state: FSMContext):
    """Пользователь выбрал магазин — просим написать теги для добавления."""
    store_id = int(callback.data.split(":")[1])
    await state.set_state(StoreTagStates.waiting_for_tags)
    await state.update_data(store_id=store_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "🏷 Напиши теги для добавления через пробел или запятую.\n"
        "Для удаления тега поставь минус перед #: <code>-#старый_тег</code>\n"
        "Пример: <code>#продукты #еда -#старый</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(StoreTagStates.waiting_for_tags, F.text)
async def handle_store_tag_input(message: Message, state: FSMContext):
    """Обрабатывает введённые теги для магазина."""
    data = await state.get_data()
    store_id = data.get("store_id")
    user_id = message.from_user.id

    tokens = message.text.replace(",", " ").split()
    del_tags = [t[1:] for t in tokens if t.startswith("-#")]
    add_tags_raw = [t for t in tokens if t.startswith("#") or (not t.startswith("-") and t.strip())]
    # Фильтруем — только теги (с # или без минуса)
    add_tags_raw = [t for t in tokens if not t.startswith("-")]

    await state.clear()

    results = []

    if add_tags_raw:
        tags = normalize_tags(add_tags_raw)
        if tags:
            save_store_tags(store_id, user_id, tags)
            results.append("Добавлены: " + " ".join(f"#{t}" for t in tags))

    for tag in del_tags:
        removed = remove_store_tag(store_id, user_id, tag)
        if removed:
            results.append(f"Удалён: #{tag.lstrip('#').lower()}")
        else:
            results.append(f"Тег #{tag.lstrip('#').lower()} не найден у магазина")

    if not results:
        await message.answer("Не распознал теги. Попробуй ещё раз.")
        return

    stores = get_user_stores(user_id)
    store_full = next((s for s in stores if s["id"] == store_id), None)
    store_text = _format_store(store_full) if store_full else ""

    text = f"✅ Магазин обновлён:\n\n{store_text}\n\n" + "\n".join(results)
    await message.answer(text, parse_mode="HTML")
