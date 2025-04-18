"""
Скрипт для создания схемы БД на контуре отправителя, генерации пользователей и генерации JSON-файлов транзакций.
Теперь структура payload читается из шаблона `payload_template.json`.
"""
import os
import json
import random
from datetime import datetime

import psycopg2
from faker import Faker

# ----- Настройки БД -----
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

# ----- Параметры генерации -----
NUM_USERS = 100
NUM_TRANSACTIONS = 10000
OUTPUT_DIR = 'generated_transactions'
TEMPLATE_FILE = 'payload_template.json'

# Реестр BIC-кодов
BIC_CODES = [
    '044525225', '044525226', '044525227', '044525228',
    '044525229', '044525230', '044525231', '044525232',
    '044525233', '044525234'
]

# SQL схема отправителя (таблицы users и transactions)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(8) UNIQUE NOT NULL,
    pam VARCHAR(100) NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    account VARCHAR(32) NOT NULL,
    address TEXT NOT NULL,
    direction VARCHAR(10) DEFAULT 'Out' NOT NULL,
    bic VARCHAR(9) NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    trn_id VARCHAR(6) UNIQUE NOT NULL,
    client_id VARCHAR(8) REFERENCES users(client_id),
    beneficiary_bic VARCHAR(9) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency CHAR(3) DEFAULT 'RUB' NOT NULL,
    narrative TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

# ----- Подготовка директории -----
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----- Создание схемы БД -----
conn = psycopg2.connect(
    dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
    host=DB_HOST, port=DB_PORT
)
conn.autocommit = True
cur = conn.cursor()
cur.execute(SCHEMA_SQL)

# ----- Генерация пользователей -----
fake = Faker('ru_RU')
users = []
for i in range(1, NUM_USERS + 1):
    client_id = f"{i:08d}"
    name = fake.name()
    pam = name[:100]
    full_name = name
    account = '40817' + ''.join(random.choice('0123456789') for _ in range(16))
    address = fake.address().replace('\n', ', ')
    bic = random.choice(BIC_CODES)

    cur.execute(
        """
        INSERT INTO users(client_id, pam, full_name, account, address, direction, bic)
        VALUES (%s, %s, %s, %s, %s, 'Out', %s)
        ON CONFLICT (client_id) DO NOTHING;
        """,
        (client_id, pam, full_name, account, address, bic)
    )
    users.append({
        'client_id': client_id,
        'pam': pam,
        'full_name': full_name,
        'account': account,
        'address': address,
        'direction': 'Out',
        'bic': bic
    })
conn.commit()
print(f"Inserted {len(users)} users into DB.")

# ----- Чтение шаблона payload -----
if not os.path.exists(TEMPLATE_FILE):
    raise FileNotFoundError(f"Template file '{TEMPLATE_FILE}' not found.")
with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    template = json.load(f)

# Ожидается, что шаблон имеет ключ 'Data' внутри
base_data = template.get('Data')
if base_data is None:
    raise KeyError("В шаблоне должен быть ключ 'Data'.")

# ----- Генерация файлов транзакций на основе шаблона -----
for n in range(1, NUM_TRANSACTIONS + 1):
    trn_id = f"{n:06d}"
    payer = random.choice(users)
    beneficiary = random.choice(users)
    while beneficiary['client_id'] == payer['client_id']:
        beneficiary = random.choice(users)

    amount = round(random.uniform(1, 150000), 2)
    narrative = random.choice([
        'Перевод по СБП без комиссии',
        'Оплата услуг',
        'Перевод другу',
        ''
    ])

    # Создаём копию шаблона и заполняем поля
    data_payload = dict(base_data)
    data_payload.update({
        'CurrentTimestamp': datetime.utcnow().isoformat() + 'Z',
        'TrnId': trn_id,
        'TrnType': 'C2C',
        'PayerData': {
            'ClientId': payer['client_id'],
            'PAM': payer['pam'],
            'FullName': payer['full_name'],
            'Account': payer['account'],
            'Address': payer['address'],
            'Direction': payer['direction'],
            'PayerBIC': payer['bic'],
        },
        'BeneficiaryData': {
            'PAM': beneficiary['pam'],
            'FullName': beneficiary['full_name'],
            'BeneficiaryBIC': beneficiary['bic'],
        },
        'Amount': str(amount),
        'Currency': 'RUB',
        'Narrative': narrative
    })

    file_path = os.path.join(OUTPUT_DIR, f'txn_{trn_id}.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump({'data': data_payload}, f, ensure_ascii=False, indent=2)

    if n % 1000 == 0:
        print(f"Generated {n} transactions...")

print(f"All {NUM_TRANSACTIONS} transaction files created in '{OUTPUT_DIR}'.")

# ----- Закрытие соединения -----
cur.close()
conn.close()
