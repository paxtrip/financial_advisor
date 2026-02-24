import re


def extract_tags_from_text(text: str) -> tuple[str, list[str]]:
    """Извлекает #хештеги из текста.

    Возвращает (clean_text, tags) где:
    - clean_text — исходный текст без #тегов
    - tags — список тегов в нижнем регистре без символа #
    """
    pattern = r"#([а-яёa-z][а-яёa-z0-9_]*)"
    tags = re.findall(pattern, text, flags=re.IGNORECASE)
    clean_text = re.sub(r"#[а-яёa-z][а-яёa-z0-9_]*", "", text, flags=re.IGNORECASE)
    clean_text = re.sub(r"\s{2,}", " ", clean_text).strip()
    return clean_text, [t.lower() for t in tags]


def normalize_tags(tags: list[str]) -> list[str]:
    """Нормализует список тегов: нижний регистр, убирает #, дубли."""
    result = []
    seen = set()
    for tag in tags:
        normalized = tag.lstrip("#").lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def merge_tags(*tag_lists: list[str]) -> list[str]:
    """Объединяет несколько списков тегов без дублей."""
    seen = set()
    result = []
    for tags in tag_lists:
        for tag in tags:
            normalized = tag.lstrip("#").lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result
