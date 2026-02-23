# fin_assist — Персональный финансовый ассистент

Telegram-бот для учёта личных финансов. Записывает расходы и доходы из текстовых сообщений и фотографий чеков, автоматически категоризирует покупки по иерархическим подкатегориям и строит точные отчёты с разбивкой по позициям чека.

## Возможности

- **Текстовый ввод** — напишите "кофе 250р" или "зарплата 80000", бот сам разберёт сумму, категорию, магазин и дату
- **Распознавание чеков** — отправьте фото чека: бот найдёт QR-код и получит данные через API, либо распознает текст через Vision LLM
- **Иерархические категории** — 13 родительских категорий и 19 подкатегорий (Молочное, Мясо и рыба, Такси, Кофе и фастфуд и т.д.)
- **Точные отчёты** — суммы в отчёте считаются по позициям чека, а не по одной категории транзакции (чек из супермаркета правильно разбивается на Молочное, Бакалею, Бытовую химию)
- **Редактирование** — изменение и удаление записей через inline-кнопки
- **Защита от дублей** — повторная отправка того же чека не создаёт дубль
- **Естественный диалог** — бот понимает разговорный русский и задаёт уточняющие вопросы

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3.12 + [aiogram 3](https://docs.aiogram.dev/) |
| База данных | [Supabase](https://supabase.com/) (PostgreSQL) |
| LLM | [OpenRouter](https://openrouter.ai/) (по умолчанию DeepSeek V3) |
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
│   └── edit.py              # Редактирование/удаление (inline-кнопки)
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

Для декодирования QR-кодов нужна системная библиотека:

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
| `SUPABASE_KEY` | Anon key Supabase |
| `OPENROUTER_API_KEY` | API-ключ OpenRouter |
| `LLM_MODEL` | Модель для парсинга текста (по умолчанию `deepseek/deepseek-v3.2`) |
| `VISION_LLM_MODEL` | Модель для распознавания фото |
| `PROVERKACHEKA_TOKEN` | Токен API proverkacheka.com |

### 5. Создайте таблицы в Supabase

Выполните SQL из файла `supabase_schema.sql` в SQL Editor вашего проекта Supabase.

### 6. Запустите бота

```bash
python bot.py
```

## Схема базы данных

6 таблиц: `users`, `categories`, `stores`, `store_aliases`, `transactions`, `transaction_items`.

Категории иерархические — `categories.parent_id` связывает подкатегории с родительскими. Подробная схема — в файле [`supabase_schema.sql`](supabase_schema.sql).

## Статус

MVP — бот работает, основной функционал реализован.

**В планах:**
- Пользовательские псевдонимы магазинов
- Бюджеты и лимиты по категориям
- Отчёт за произвольный период
- Голосовой ввод
- Экспорт в CSV

## Лицензия

Проект пока не имеет открытой лицензии.
