# fin_assist — Персональный финансовый ассистент

Telegram-бот для учёта личных финансов. Записывает расходы и доходы из текстовых сообщений и фотографий чеков, автоматически категоризирует покупки и строит отчёты.

## Возможности

- **Текстовый ввод** — напишите боту "кофе 250р" или "зарплата 80000", и он сам разберёт сумму, категорию, магазин и дату
- **Распознавание чеков** — отправьте фото чека: бот найдёт QR-код и получит данные через API, либо распознает текст через Vision LLM
- **Автоматическая категоризация** — расходы распределяются по категориям (продукты, транспорт, развлечения и т.д.)
- **Отчёты** — команда `/report` покажет статистику расходов за выбранный период
- **Естественный диалог** — бот понимает разговорный русский язык и задаёт уточняющие вопросы при необходимости

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3.12 + [aiogram 3](https://docs.aiogram.dev/) |
| База данных | [Supabase](https://supabase.com/) (PostgreSQL) |
| LLM | [OpenRouter](https://openrouter.ai/) (по умолчанию Gemini 2.5 Flash) |
| Данные чеков | [proverkacheka.com](https://proverkacheka.com/) API |
| QR-декодирование | pyzbar + Pillow |
| Валидация | Pydantic |
| HTTP-клиент | httpx |

## Структура проекта

```
├── bot.py                   # Точка входа, запуск polling
├── config.py                # Настройки из .env (pydantic-settings)
├── supabase_schema.sql      # Полная схема БД
├── handlers/
│   ├── start.py             # /start, /help, регистрация пользователя
│   ├── message.py           # Текст → LLM парсинг → сохранение
│   ├── photo.py             # Фото → QR / Vision LLM → сохранение
│   ├── reports.py           # /report — отчёты за период
│   └── edit.py              # Редактирование/удаление (в разработке)
├── services/
│   ├── llm.py               # OpenRouter API
│   ├── receipt_qr.py        # API proverkacheka.com
│   ├── receipt_photo.py     # Vision LLM для фото без QR
│   └── supabase_client.py   # CRUD операции с Supabase
├── models/
│   └── schemas.py           # Pydantic-модели
├── prompts/
│   └── system_prompts.py    # System prompts для LLM
├── utils/
│   └── qr_decoder.py        # Декодирование QR из изображений
└── docs/                    # Документация и ТЗ
```

## Установка и запуск

### 1. Клонируйте репозиторий

```bash
git clone git@github.com:paxtrip/financial_advisor.git
cd financial_advisor
```

### 2. Создайте виртуальное окружение

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Установите зависимости

```bash
pip install -r requirements.txt
```

Для декодирования QR-кодов также нужна системная библиотека:

```bash
# Ubuntu/Debian
sudo apt install libzbar0
```

### 4. Настройте переменные окружения

```bash
cp .env.example .env
```

Заполните `.env`:

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `SUPABASE_URL` | URL вашего проекта Supabase |
| `SUPABASE_KEY` | Anon/service key Supabase |
| `OPENROUTER_API_KEY` | API-ключ OpenRouter |
| `LLM_MODEL` | Модель для парсинга текста (по умолчанию `google/gemini-2.5-flash`) |
| `VISION_LLM_MODEL` | Модель для распознавания фото (по умолчанию `google/gemini-2.5-flash`) |
| `PROVERKACHEKA_TOKEN` | Токен API proverkacheka.com |

### 5. Создайте таблицы в Supabase

Выполните SQL из файла `supabase_schema.sql` в SQL-редакторе вашего проекта Supabase.

### 6. Запустите бота

```bash
python bot.py
```

## Схема базы данных

6 таблиц: `users`, `categories`, `stores`, `store_aliases`, `transactions`, `transaction_items`.

Подробная схема — в файле [`supabase_schema.sql`](supabase_schema.sql).

## Статус

MVP — бот работает, основной функционал реализован. В разработке:

- Редактирование и удаление записей
- Пользовательские псевдонимы магазинов
- Бюджеты и лимиты по категориям

## Лицензия

Проект пока не имеет открытой лицензии.
