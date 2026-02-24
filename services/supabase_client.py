from supabase import create_client, Client

from config import settings
from utils.tag_parser import normalize_tags

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


def get_or_create_user(telegram_id: int, username: str | None, first_name: str | None) -> dict:
    """Создаёт пользователя или возвращает существующего."""
    result = supabase.table("users").select("*").eq("id", telegram_id).execute()

    if result.data:
        return result.data[0]

    new_user = (
        supabase.table("users")
        .insert({"id": telegram_id, "username": username, "first_name": first_name})
        .execute()
    )
    return new_user.data[0]


def get_categories(user_id: int, is_income: bool = False) -> list[dict]:
    """Получает категории: глобальные + пользовательские."""
    result = (
        supabase.table("categories")
        .select("*")
        .eq("is_income", is_income)
        .or_(f"user_id.is.null,user_id.eq.{user_id}")
        .execute()
    )
    return result.data


def find_category_by_name(user_id: int, name: str) -> dict | None:
    """Ищет категорию по имени (сначала пользовательскую, потом глобальную)."""
    result = (
        supabase.table("categories")
        .select("*")
        .ilike("name", name)
        .or_(f"user_id.is.null,user_id.eq.{user_id}")
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def find_or_create_store(
    user_id: int,
    store_name: str,
    address: str | None = None,
    chain: str | None = None,
) -> int:
    """Находит магазин или создаёт новый. Возвращает store_id."""
    # Сначала проверим псевдонимы
    alias_result = (
        supabase.table("store_aliases")
        .select("store_id")
        .eq("user_id", user_id)
        .ilike("alias", store_name)
        .limit(1)
        .execute()
    )
    if alias_result.data:
        return alias_result.data[0]["store_id"]

    # Ищем магазин по имени
    store_result = (
        supabase.table("stores")
        .select("id, address, chain")
        .eq("user_id", user_id)
        .ilike("name", store_name)
        .limit(1)
        .execute()
    )
    if store_result.data:
        store = store_result.data[0]
        # Если у найденного магазина уже есть адрес и он отличается от нового —
        # это другая точка с тем же брендом, создаём отдельную запись
        if address and store.get("address") and store["address"] != address:
            store_data = {"user_id": user_id, "name": store_name, "address": address}
            if chain:
                store_data["chain"] = chain
            new_store = supabase.table("stores").insert(store_data).execute()
            return new_store.data[0]["id"]
        # Обновляем адрес/chain, если пришли новые данные
        updates = {}
        if address and not store.get("address"):
            updates["address"] = address
        if chain and not store.get("chain"):
            updates["chain"] = chain
        if updates:
            supabase.table("stores").update(updates).eq("id", store["id"]).execute()
        return store["id"]

    # Создаём новый
    store_data = {"user_id": user_id, "name": store_name}
    if address:
        store_data["address"] = address
    if chain:
        store_data["chain"] = chain
    new_store = supabase.table("stores").insert(store_data).execute()
    return new_store.data[0]["id"]


def check_qr_duplicate(user_id: int, qr_raw: str) -> bool:
    """Проверяет, есть ли уже транзакция с таким QR-кодом."""
    result = (
        supabase.table("transactions")
        .select("id")
        .eq("user_id", user_id)
        .eq("qr_raw", qr_raw)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


def save_transaction(user_id: int, data: dict) -> dict:
    """Сохраняет транзакцию и позиции."""
    store_id = None
    if data.get("store_name"):
        store_id = find_or_create_store(
            user_id,
            data["store_name"],
            address=data.get("store_address"),
            chain=data.get("store_organization"),
        )

    category = find_category_by_name(user_id, data["category"]) if data.get("category") else None
    category_id = category["id"] if category else None

    tx = (
        supabase.table("transactions")
        .insert(
            {
                "user_id": user_id,
                "type": data["type"],
                "amount": data["amount"],
                "category_id": category_id,
                "store_id": store_id,
                "description": data.get("description"),
                "receipt_date": data.get("date"),
                "source": data.get("source", "text"),
                "raw_input": data.get("raw_input"),
                "llm_parsed_json": data.get("llm_raw"),
                "qr_raw": data.get("qr_raw"),
            }
        )
        .execute()
    )

    tx_id = tx.data[0]["id"]

    # Собираем теги: из данных + постоянные теги магазина
    tx_tag_names: list[str] = list(data.get("tags") or [])
    if store_id:
        store_tag_ids = get_store_tags(store_id)
        # Получаем имена тегов магазина чтобы смержить без дублей
        if store_tag_ids:
            store_tags_rows = (
                supabase.table("tags")
                .select("name")
                .in_("id", store_tag_ids)
                .execute()
            ).data
            for row in store_tags_rows:
                if row["name"] not in tx_tag_names:
                    tx_tag_names.append(row["name"])

    if tx_tag_names:
        tx_tag_ids = _resolve_tag_ids(user_id, tx_tag_names)
        supabase.table("transaction_tags").insert(
            [{"transaction_id": tx_id, "tag_id": tid} for tid in tx_tag_ids]
        ).execute()

    if data.get("items"):
        items_to_insert = []

        for item in data["items"]:
            item_data = {
                "transaction_id": tx_id,
                "name": item["name"],
                "quantity": item.get("quantity", 1),
                "price": item["price"],
                "total": item["total"],
            }
            if item.get("category"):
                item_cat = find_category_by_name(user_id, item["category"])
                if item_cat:
                    item_data["category_id"] = item_cat["id"]
            items_to_insert.append((item_data, item.get("tags") or []))

        # Вставляем позиции и сохраняем теги позиций
        for item_data, item_tags in items_to_insert:
            inserted = supabase.table("transaction_items").insert(item_data).execute()
            item_id = inserted.data[0]["id"]
            if item_tags:
                item_tag_ids = _resolve_tag_ids(user_id, item_tags)
                supabase.table("transaction_item_tags").insert(
                    [{"transaction_item_id": item_id, "tag_id": tid} for tid in item_tag_ids]
                ).execute()

    return tx.data[0]


def get_transactions(user_id: int, date_from: str, date_to: str) -> list[dict]:
    """Получает транзакции за период."""
    result = (
        supabase.table("transactions")
        .select("*, categories(name), stores(name)")
        .eq("user_id", user_id)
        .gte("receipt_date", date_from)
        .lte("receipt_date", date_to)
        .order("receipt_date", desc=True)
        .execute()
    )
    return result.data


def get_category_breakdown(user_id: int, date_from: str, date_to: str) -> list[dict]:
    """Разбивка расходов по категориям за период.
    Для транзакций с позициями — суммирует по категориям позиций.
    Для транзакций без позиций — берёт категорию транзакции."""

    # 1. Все расходные транзакции за период
    txs = (
        supabase.table("transactions")
        .select("id, amount, category_id, categories(name)")
        .eq("user_id", user_id)
        .eq("type", "expense")
        .gte("receipt_date", date_from)
        .lte("receipt_date", date_to)
        .execute()
    ).data

    if not txs:
        return []

    tx_ids = [tx["id"] for tx in txs]

    # 2. Позиции этих транзакций
    items = (
        supabase.table("transaction_items")
        .select("transaction_id, total, category_id, categories(name)")
        .in_("transaction_id", tx_ids)
        .execute()
    ).data

    tx_ids_with_items = {item["transaction_id"] for item in items}
    totals: dict[str, float] = {}

    # Суммируем по категориям позиций
    for item in items:
        cat = item.get("categories")
        name = cat["name"] if cat else "Другое"
        totals[name] = totals.get(name, 0) + float(item["total"])

    # Транзакции без позиций — по категории транзакции
    for tx in txs:
        if tx["id"] not in tx_ids_with_items:
            cat = tx.get("categories")
            name = cat["name"] if cat else "Другое"
            totals[name] = totals.get(name, 0) + float(tx["amount"])

    return sorted(
        [{"category": k, "total": round(v, 2)} for k, v in totals.items()],
        key=lambda x: x["total"],
        reverse=True,
    )


def add_tags_to_transaction(transaction_id: int, user_id: int, tags: list[str]) -> list[str]:
    """Добавляет теги к транзакции. Возвращает список сохранённых тегов (без дублей)."""
    saved = []
    for tag in normalize_tags(tags):
        tag_id = get_or_create_tag(user_id, tag)
        existing = (
            supabase.table("transaction_tags")
            .select("tag_id")
            .eq("transaction_id", transaction_id)
            .eq("tag_id", tag_id)
            .limit(1)
            .execute()
        )
        if not existing.data:
            supabase.table("transaction_tags").insert(
                {"transaction_id": transaction_id, "tag_id": tag_id}
            ).execute()
            saved.append(tag)
    return saved


def get_or_create_tag(user_id: int, name: str) -> int:
    """Находит тег по имени или создаёт новый. Возвращает tag_id."""
    normalized = name.lstrip("#").lower().strip()
    result = (
        supabase.table("tags")
        .select("id")
        .eq("user_id", user_id)
        .eq("name", normalized)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["id"]
    new_tag = supabase.table("tags").insert({"user_id": user_id, "name": normalized}).execute()
    return new_tag.data[0]["id"]


def _resolve_tag_ids(user_id: int, tags: list[str]) -> list[int]:
    """Преобразует список имён тегов в список tag_id."""
    return [get_or_create_tag(user_id, t) for t in tags if t.strip()]


def get_store_tags(store_id: int) -> list[int]:
    """Возвращает список tag_id постоянных тегов магазина."""
    result = (
        supabase.table("store_tags")
        .select("tag_id")
        .eq("store_id", store_id)
        .execute()
    )
    return [row["tag_id"] for row in result.data]


def save_store_tags(store_id: int, user_id: int, tags: list[str]) -> None:
    """Добавляет постоянные теги магазину (без дублей)."""
    tag_ids = _resolve_tag_ids(user_id, tags)
    if not tag_ids:
        return
    existing = get_store_tags(store_id)
    new_rows = [
        {"store_id": store_id, "tag_id": tid}
        for tid in tag_ids
        if tid not in existing
    ]
    if new_rows:
        supabase.table("store_tags").insert(new_rows).execute()


def get_last_transactions(user_id: int, limit: int = 5) -> list[dict]:
    """Получает последние N транзакций."""
    result = (
        supabase.table("transactions")
        .select("*, categories(name), stores(name)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def delete_transaction(transaction_id: int, user_id: int) -> bool:
    """Удаляет транзакцию (только свою)."""
    result = (
        supabase.table("transactions")
        .delete()
        .eq("id", transaction_id)
        .eq("user_id", user_id)
        .execute()
    )
    return len(result.data) > 0


def update_transaction(transaction_id: int, user_id: int, updates: dict) -> dict | None:
    """Обновляет поля транзакции (только свою). Возвращает обновлённую запись или None."""
    allowed_fields = {"amount", "category_id", "description"}
    filtered = {k: v for k, v in updates.items() if k in allowed_fields}
    if not filtered:
        return None

    result = (
        supabase.table("transactions")
        .update(filtered)
        .eq("id", transaction_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0] if result.data else None


def get_user_tags(user_id: int) -> list[dict]:
    """Возвращает все теги пользователя, отсортированные по имени."""
    result = (
        supabase.table("tags")
        .select("id, name")
        .eq("user_id", user_id)
        .order("name")
        .execute()
    )
    return result.data


def get_transactions_by_tag(
    user_id: int, tag_name: str, date_from: str, date_to: str
) -> list[dict]:
    """Возвращает транзакции за период, помеченные указанным тегом."""
    normalized = tag_name.lstrip("#").lower().strip()

    tag_result = (
        supabase.table("tags")
        .select("id")
        .eq("user_id", user_id)
        .eq("name", normalized)
        .limit(1)
        .execute()
    )
    if not tag_result.data:
        return []
    tag_id = tag_result.data[0]["id"]

    link_result = (
        supabase.table("transaction_tags")
        .select("transaction_id")
        .eq("tag_id", tag_id)
        .execute()
    )
    if not link_result.data:
        return []
    tx_ids = [row["transaction_id"] for row in link_result.data]

    result = (
        supabase.table("transactions")
        .select("*, categories(name), stores(name)")
        .eq("user_id", user_id)
        .in_("id", tx_ids)
        .gte("receipt_date", date_from)
        .lte("receipt_date", date_to)
        .order("receipt_date", desc=True)
        .execute()
    )
    return result.data


def get_category_breakdown_by_tag(
    user_id: int, tag_name: str, date_from: str, date_to: str
) -> list[dict]:
    """Разбивка по категориям для транзакций с указанным тегом."""
    txs = get_transactions_by_tag(user_id, tag_name, date_from, date_to)
    expense_txs = [t for t in txs if t["type"] == "expense"]
    if not expense_txs:
        return []

    tx_ids = [tx["id"] for tx in expense_txs]
    items = (
        supabase.table("transaction_items")
        .select("transaction_id, total, category_id, categories(name)")
        .in_("transaction_id", tx_ids)
        .execute()
    ).data

    tx_ids_with_items = {item["transaction_id"] for item in items}
    totals: dict[str, float] = {}

    for item in items:
        cat = item.get("categories")
        name = cat["name"] if cat else "Другое"
        totals[name] = totals.get(name, 0) + float(item["total"])

    for tx in expense_txs:
        if tx["id"] not in tx_ids_with_items:
            cat = tx.get("categories")
            name = cat["name"] if cat else "Другое"
            totals[name] = totals.get(name, 0) + float(tx["amount"])

    return sorted(
        [{"category": k, "total": round(v, 2)} for k, v in totals.items()],
        key=lambda x: x["total"],
        reverse=True,
    )


def get_user_stores(user_id: int) -> list[dict]:
    """Возвращает все магазины пользователя с их тегами."""
    stores = (
        supabase.table("stores")
        .select("id, name, address")
        .eq("user_id", user_id)
        .order("name")
        .execute()
    ).data

    if not stores:
        return []

    store_ids = [s["id"] for s in stores]
    links = (
        supabase.table("store_tags")
        .select("store_id, tags(name)")
        .in_("store_id", store_ids)
        .execute()
    ).data

    tags_by_store: dict[int, list[str]] = {}
    for link in links:
        sid = link["store_id"]
        tag_name = link.get("tags", {}).get("name")
        if tag_name:
            tags_by_store.setdefault(sid, []).append(tag_name)

    for store in stores:
        store["tags"] = tags_by_store.get(store["id"], [])

    return stores


def get_store_by_name(user_id: int, name: str) -> dict | None:
    """Ищет магазин пользователя по точному имени (без учёта регистра)."""
    result = (
        supabase.table("stores")
        .select("id, name, address")
        .eq("user_id", user_id)
        .ilike("name", name)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def remove_store_tag(store_id: int, user_id: int, tag_name: str) -> bool:
    """Удаляет тег с магазина. Возвращает True если тег был удалён."""
    normalized = tag_name.lstrip("#").lower().strip()
    tag_result = (
        supabase.table("tags")
        .select("id")
        .eq("user_id", user_id)
        .eq("name", normalized)
        .limit(1)
        .execute()
    )
    if not tag_result.data:
        return False
    tag_id = tag_result.data[0]["id"]

    result = (
        supabase.table("store_tags")
        .delete()
        .eq("store_id", store_id)
        .eq("tag_id", tag_id)
        .execute()
    )
    return len(result.data) > 0
