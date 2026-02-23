-- ============================================
-- Схема БД для финансового ассистента (Supabase)
-- Выполнить в SQL Editor Supabase
-- ============================================

-- 1. Пользователи
CREATE TABLE users (
    id BIGINT PRIMARY KEY,                    -- telegram user id
    username TEXT,
    first_name TEXT,
    timezone TEXT DEFAULT 'Europe/Moscow',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Категории (с возможностью иерархии в будущем)
CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),      -- NULL = глобальная категория
    name TEXT NOT NULL,
    parent_id INT REFERENCES categories(id),  -- для иерархии (v2)
    is_income BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 3. Магазины
CREATE TABLE stores (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    name TEXT NOT NULL,
    chain TEXT,
    address TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, name, address)
);

-- 4. Псевдонимы магазинов ("магазин у дома" → Пятёрочка)
CREATE TABLE store_aliases (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) NOT NULL,
    alias TEXT NOT NULL,
    store_id INT REFERENCES stores(id) NOT NULL,
    UNIQUE(user_id, alias)
);

-- 5. Транзакции (расходы и доходы)
CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('expense', 'income')),
    amount NUMERIC(12, 2) NOT NULL,
    category_id INT REFERENCES categories(id),
    store_id INT REFERENCES stores(id),
    description TEXT,
    receipt_date TIMESTAMPTZ,
    source TEXT DEFAULT 'text' CHECK (source IN ('text', 'photo', 'qr', 'voice')),
    raw_input TEXT,
    llm_parsed_json JSONB,
    qr_raw TEXT,                       -- строка QR-кода (для защиты от дублей)
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_transactions_user_date ON transactions(user_id, receipt_date);
CREATE INDEX idx_transactions_user_category ON transactions(user_id, category_id);
CREATE UNIQUE INDEX idx_transactions_qr_raw ON transactions(user_id, qr_raw) WHERE qr_raw IS NOT NULL;

-- 6. Позиции из чека (детализация транзакции)
CREATE TABLE transaction_items (
    id SERIAL PRIMARY KEY,
    transaction_id INT REFERENCES transactions(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity NUMERIC(10, 3) DEFAULT 1,
    price NUMERIC(12, 2) NOT NULL,
    total NUMERIC(12, 2) NOT NULL,
    category_id INT REFERENCES categories(id)
);

-- ============================================
-- Начальные данные: базовые категории расходов
-- ============================================
INSERT INTO categories (name, is_income) VALUES
    ('Продукты', FALSE),
    ('Транспорт', FALSE),
    ('Жильё', FALSE),
    ('Развлечения', FALSE),
    ('Одежда', FALSE),
    ('Здоровье', FALSE),
    ('Кафе', FALSE),
    ('Подписки', FALSE),
    ('Связь', FALSE),
    ('Образование', FALSE),
    ('Бытовая химия', FALSE),
    ('Товары для дома', FALSE),
    ('Другое', FALSE);

-- Категории доходов
INSERT INTO categories (name, is_income) VALUES
    ('Зарплата', TRUE),
    ('Подработка', TRUE),
    ('Переводы', TRUE),
    ('Другой доход', TRUE);
