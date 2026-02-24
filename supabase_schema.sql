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
-- Начальные данные: иерархические категории расходов
-- ============================================

-- Родительские категории (parent_id = NULL)
INSERT INTO categories (name, is_income) VALUES
    ('Продукты питания', FALSE),
    ('Транспорт', FALSE),
    ('Жильё', FALSE),
    ('Развлечения', FALSE),
    ('Одежда и обувь', FALSE),
    ('Здоровье и красота', FALSE),
    ('Кафе и рестораны', FALSE),
    ('Подписки', FALSE),
    ('Связь', FALSE),
    ('Образование', FALSE),
    ('Бытовая химия и дом', FALSE),
    ('Подарки', FALSE),
    ('Другое', FALSE);

-- Подкатегории «Продукты питания»
INSERT INTO categories (name, parent_id, is_income) VALUES
    ('Мясо и рыба',            (SELECT id FROM categories WHERE name='Продукты питания'    AND user_id IS NULL), FALSE),
    ('Молочное',               (SELECT id FROM categories WHERE name='Продукты питания'    AND user_id IS NULL), FALSE),
    ('Овощи и фрукты',         (SELECT id FROM categories WHERE name='Продукты питания'    AND user_id IS NULL), FALSE),
    ('Хлеб и выпечка',         (SELECT id FROM categories WHERE name='Продукты питания'    AND user_id IS NULL), FALSE),
    ('Напитки',                (SELECT id FROM categories WHERE name='Продукты питания'    AND user_id IS NULL), FALSE),
    ('Бакалея',                (SELECT id FROM categories WHERE name='Продукты питания'    AND user_id IS NULL), FALSE);

-- Подкатегории «Бытовая химия и дом»
INSERT INTO categories (name, parent_id, is_income) VALUES
    ('Бытовая химия',          (SELECT id FROM categories WHERE name='Бытовая химия и дом' AND user_id IS NULL), FALSE),
    ('Товары для дома',        (SELECT id FROM categories WHERE name='Бытовая химия и дом' AND user_id IS NULL), FALSE),
    ('Зоотовары',              (SELECT id FROM categories WHERE name='Бытовая химия и дом' AND user_id IS NULL), FALSE);

-- Подкатегории «Здоровье и красота»
INSERT INTO categories (name, parent_id, is_income) VALUES
    ('Аптека',                 (SELECT id FROM categories WHERE name='Здоровье и красота'  AND user_id IS NULL), FALSE),
    ('Косметика и гигиена',    (SELECT id FROM categories WHERE name='Здоровье и красота'  AND user_id IS NULL), FALSE),
    ('Спорт',                  (SELECT id FROM categories WHERE name='Здоровье и красота'  AND user_id IS NULL), FALSE);

-- Подкатегории «Транспорт»
INSERT INTO categories (name, parent_id, is_income) VALUES
    ('Такси',                  (SELECT id FROM categories WHERE name='Транспорт'           AND user_id IS NULL), FALSE),
    ('Бензин',                 (SELECT id FROM categories WHERE name='Транспорт'           AND user_id IS NULL), FALSE),
    ('Общественный транспорт', (SELECT id FROM categories WHERE name='Транспорт'           AND user_id IS NULL), FALSE);

-- Подкатегории «Кафе и рестораны»
INSERT INTO categories (name, parent_id, is_income) VALUES
    ('Рестораны',              (SELECT id FROM categories WHERE name='Кафе и рестораны'    AND user_id IS NULL), FALSE),
    ('Кофе и фастфуд',         (SELECT id FROM categories WHERE name='Кафе и рестораны'    AND user_id IS NULL), FALSE);

-- Подкатегории «Развлечения»
INSERT INTO categories (name, parent_id, is_income) VALUES
    ('Кино и театр',           (SELECT id FROM categories WHERE name='Развлечения'         AND user_id IS NULL), FALSE),
    ('Хобби',                  (SELECT id FROM categories WHERE name='Развлечения'         AND user_id IS NULL), FALSE);

-- Категории доходов
INSERT INTO categories (name, is_income) VALUES
    ('Зарплата', TRUE),
    ('Подработка', TRUE),
    ('Переводы', TRUE),
    ('Другой доход', TRUE);

-- ============================================
-- Система хештегов
-- ============================================

-- 7. Справочник тегов
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) NOT NULL,
    name TEXT NOT NULL,                            -- без #, нижний регистр
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, name)
);

CREATE INDEX idx_tags_user ON tags(user_id);

-- 8. Теги транзакции
CREATE TABLE transaction_tags (
    transaction_id INT REFERENCES transactions(id) ON DELETE CASCADE,
    tag_id INT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (transaction_id, tag_id)
);

-- 9. Теги позиции чека
CREATE TABLE transaction_item_tags (
    transaction_item_id INT REFERENCES transaction_items(id) ON DELETE CASCADE,
    tag_id INT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (transaction_item_id, tag_id)
);

-- 10. Постоянные теги магазина (наследуются новыми транзакциями)
CREATE TABLE store_tags (
    store_id INT REFERENCES stores(id) ON DELETE CASCADE,
    tag_id INT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (store_id, tag_id)
);
