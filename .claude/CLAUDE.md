Всегда веди диалог на русском языке.

## Правила работы

1. Прежде чем писать код, опиши свой подход и дождись подтверждения. Всегда задавай уточняющие вопросы, если требования неясны.
2. Если задача затрагивает больше 3 файлов, остановись и разбей её на более мелкие подзадачи.
3. После написания кода, перечисли, что может сломаться, и предложи тесты для проверки.
4. При баге сначала напиши тест, который его воспроизводит, затем исправляй код, пока тест не проходит.
5. Каждый раз, когда я исправляю тебя, добавляй новое правило в этот файл, чтобы это больше не повторялось.
6. При изменении схемы БД — всегда обновляй `supabase_schema.sql`, чтобы он отражал актуальное состояние.
7. В системе настроен SOCKS-прокси. Бота запускать через: `env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy -u FTP_PROXY -u ftp_proxy .venv/bin/python bot.py`

## О проекте

**fin_assist** — персональный финансовый ассистент в виде Telegram-бота. Записывает расходы/доходы из текста и фото чеков, категоризирует, строит отчёты.

- Разработчик: один человек, без опыта программирования, работает через Claude Code
- Стадия: MVP, бот работает
- Цель: сначала для себя, потом возможно коммерчески

## Стек

- **Python 3.12** + **aiogram 3** (Telegram-бот, async)
- **Supabase** (PostgreSQL) — БД, хранение всех данных
- **OpenRouter API** — LLM (модель настраивается в .env, по умолчанию `google/gemini-2.5-flash`)
- **proverkacheka.com API** — получение данных чека по QR-коду
- **pyzbar + Pillow** — декодирование QR из фотографий
- **Pydantic** — валидация данных от LLM
- **httpx** — асинхронные HTTP-запросы

## Структура проекта

```
fin_assist/
├── bot.py                      # Точка входа, запуск polling
├── config.py                   # Настройки из .env (pydantic-settings)
├── supabase_schema.sql         # Полная схема БД (всегда держать актуальной!)
├── handlers/
│   ├── start.py                # /start, /help + регистрация пользователя в БД
│   ├── message.py              # Текст → LLM парсинг → сохранение в БД
│   ├── photo.py                # Фото → QR → proverkacheka / Vision LLM → сохранение
│   ├── reports.py              # /report — отчёты за период
│   └── edit.py                 # Редактирование/удаление транзакций (inline-кнопки)
├── services/
│   ├── llm.py                  # OpenRouter API (парсинг текста, фото, категоризация, отчёты)
│   ├── receipt_qr.py           # proverkacheka.com API (чек по QR)
│   ├── receipt_photo.py        # Vision LLM для фото без QR
│   └── supabase_client.py      # Все CRUD операции с Supabase
├── models/
│   └── schemas.py              # Pydantic-модели (ParsedExpense, ParsedReceipt и др.)
├── prompts/
│   └── system_prompts.py       # System prompts для LLM
├── utils/
│   └── qr_decoder.py           # Декодирование QR из изображения (pyzbar)
├── docs/
│   ├── project.md              # Полное ТЗ — перечень функциональных возможностей
│   ├── documentation_api.md    # Документация API proverkacheka.com
│   ├── Grok_1.md               # Анализ и рекомендации от Grok
│   └── Gemini_2.md             # Анализ и рекомендации от Gemini
├── .env                        # Секреты (не коммитить!)
├── .env.example                # Шаблон для .env
└── .gitignore
```

## Схема БД (Supabase)

6 таблиц: `users`, `categories`, `stores`, `store_aliases`, `transactions`, `transaction_items`

Ключевые моменты:
- `transactions.qr_raw` — строка QR-кода, уникальный индекс для защиты от дублей
- `transactions.llm_parsed_json` (JSONB) — сырой ответ LLM, страховка для перепарсинга
- `categories.user_id = NULL` — глобальная категория, видна всем
- `stores` — `retailPlace` из чека (торговая марка), `chain` = юрлицо (`user`), `address` = фактический адрес
- Суммы в API proverkacheka приходят **в копейках**, делим на 100

## Поток обработки

1. **Текст** → `handlers/message.py` → `services/llm.py` (парсинг) → `models/schemas.py` (валидация) → `services/supabase_client.py` (сохранение)
2. **Фото** → `handlers/photo.py` → `utils/qr_decoder.py` (ищем QR) → если QR найден: `services/receipt_qr.py` (proverkacheka) → если нет: `services/receipt_photo.py` (Vision LLM) → сохранение
3. **Отчёт** → `handlers/reports.py` → запрос к БД → `services/llm.py` (форматирование)
4. **Редактирование** → `handlers/message.py` (intent="edit") → `handlers/edit.py` (inline-кнопки) → callback → `services/supabase_client.py` (удаление/обновление)

## Что ещё нужно сделать (TODO)

- [x] Проверка дублей QR перед сохранением (поле `qr_raw` добавлено в БД)
- [x] Полноценное редактирование/удаление записей (`handlers/edit.py`)
- [ ] Определить какие поля API proverkacheka содержат адрес (логирование добавлено)
- [ ] Пользовательские псевдонимы магазинов через диалог
- [ ] Бюджеты и лимиты по категориям
- [ ] Скрипт запуска бота (обход прокси)
