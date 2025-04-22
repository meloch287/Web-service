import os
import json
import random
from datetime import datetime
import requests
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
CREATE TABLE IF NOT EXISTS "transactions" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "src_id" BIGINT,
    "dst_id" BIGINT,
    "value" NUMERIC,
    "type_id" BIGINT,
    "bnk_src_id" BIGINT,
    "bnk_dst_id" BIGINT,
    "timestamp" TIMESTAMP,
    "comment" TEXT,
    "status_id" BIGINT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "clients" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "name" TEXT,
    "comment" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "bank_account" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "client_id" BIGINT,
    "sum" DOUBLE PRECISION,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "transaction_types" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "type" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "transaction_status" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "status" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "banks" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "bank_name" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "users" (
    "client_id" TEXT UNIQUE,
    "pam" TEXT,
    "full_name" TEXT,
    "account" TEXT,
    "address" TEXT,
    "direction" TEXT,
    "bic" TEXT
);

ALTER TABLE "transactions"
ADD FOREIGN KEY("src_id") REFERENCES "clients"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("dst_id") REFERENCES "clients"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "bank_account"
ADD FOREIGN KEY("client_id") REFERENCES "clients"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("type_id") REFERENCES "transaction_types"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("bnk_src_id") REFERENCES "banks"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("bnk_dst_id") REFERENCES "banks"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("status_id") REFERENCES "transaction_status"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;
"""

SENDER_URL = "http://localhost:5000/send"

# ----- Подготовка директории -----
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----- Подключение к БД и создание схемы -----
conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)
conn.autocommit = True
cur = conn.cursor()
cur.execute(SCHEMA_SQL)
cur.execute("DELETE FROM users")

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
        ON CONFLICT (client_id) DO NOTHING
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

try:
    base_data = template['data'][0]['Data']
except (KeyError, IndexError, TypeError):
    raise KeyError("В шаблоне должен быть путь ['data'][0]['Data'].")

# ----- Генерация и сохранение файлов транзакций -----
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

# ----- Отправка каждого payload на Sender -----
for n in range(1, NUM_TRANSACTIONS + 1):
    file_path = os.path.join(OUTPUT_DIR, f"txn_{n:06d}.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    try:
        resp = requests.post(
            SENDER_URL,
            json={
                "data": payload["data"],
                "format": "json"
            },
            timeout=10
        )
        resp.raise_for_status()
        print(f"[{n:06d}] Sent → {resp.status_code}: {resp.json()}")
    except Exception as e:
        print(f"[{n:06d}] ERROR sending: {e}")

# ----- Закрытие соединения -----
cur.close()
conn.close()
