from supabase import create_client, Client

from config import settings

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

    if data.get("items"):
        items = []
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
            items.append(item_data)
        supabase.table("transaction_items").insert(items).execute()

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
