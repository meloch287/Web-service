import os
import json
import random
import time
from datetime import datetime
import requests
import psycopg2
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
from faker import Faker

# --- Настройки базы данных ---
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

# --- Параметры генерации ---
NUM_USERS = 100          # Количество пользователей
NUM_TRANSACTIONS = 30000 # Количество транзакций
OUTPUT_DIR = 'generated_transactions' # Директория для сохранения транзакций
TEMPLATE_FILE = 'payload_template.json' # Шаблон транзакции
SENDER_URL = "http://localhost:5000/send" # URL сервера

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
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Подключение к базе данных PostgreSQL
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
cur.execute("DELETE FROM users")  # Очистка таблицы перед генерацией

# Генерация пользователей
fake = Faker('ru_RU')
users = []
for i in range(1, NUM_USERS + 1):
    client_id = f"{i:08d}"  # Уникальный ID клиента
    name = fake.name()
    pam = name[:100]  # Ограничение длины для поля pam
    account = '40817' + ''.join(random.choice('0123456789') for _ in range(16))  # Генерация номера счета
    address = fake.address().replace('\n', ', ')
    bic = random.choice(BIC_CODES)

    # Вставка пользователя в базу данных
    cur.execute(
        """
        INSERT INTO users(client_id, pam, full_name, account, address, direction, bic)
        VALUES (%s, %s, %s, %s, %s, 'Out', %s)
        ON CONFLICT (client_id) DO NOTHING
        """,
        (client_id, pam, name, account, address, bic)
    )

    # Сохранение данных пользователя в список
    users.append({
        'client_id': client_id,
        'pam': pam,
        'full_name': name,
        'account': account,
        'address': address,
        'direction': 'Out',
        'bic': bic
    })

conn.commit()
print(f"Вставлено {len(users)} пользователей в базу данных.")

# Чтение шаблона транзакции
if not os.path.exists(TEMPLATE_FILE):
    raise FileNotFoundError(f"Файл: '{TEMPLATE_FILE}' не найден.")
with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    template = json.load(f)
base_data = template['data'][0]['Data']

# Генерация транзакций
for n in range(1, NUM_TRANSACTIONS + 1):
    trn_id = f"{n:06d}"  # Уникальный ID транзакции
    payer = random.choice(users)  # Выбор плательщика
    beneficiary = random.choice(users)  # Выбор получателя
    while beneficiary['client_id'] == payer['client_id']:  # Проверка, чтобы плательщик и получатель не совпадали
        beneficiary = random.choice(users)

    amount = round(random.uniform(1, 150000), 2)  # Сумма транзакции
    narrative = random.choice(['Перевод по СБП', 'Оплата услуг', 'Перевод другу', ''])  # Описание

    # Формирование данных транзакции
    data_payload = dict(base_data)
    data_payload.update({
        'CurrentTimestamp': datetime.utcnow().isoformat() + 'Z',
        'TrnId': trn_id,
        'TrnType': 'C2C',
        'PayerData': payer,
        'BeneficiaryData': beneficiary,
        'Amount': str(amount),
        'Currency': 'RUB',
        'Narrative': narrative
    })

    # Сохранение транзакции в JSON-файл
    file_path = os.path.join(OUTPUT_DIR, f'txn_{trn_id}.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump({'data': data_payload}, f, ensure_ascii=False, indent=2)

    if n % 1000 == 0:
        print(f"Создано {n} транзакций...")

print("Создание транзакций завершено.")

# Параметры Гауссова распределения
TOTAL_HOURS = 24
TOTAL_SECONDS = TOTAL_HOURS * 3600  # 24 часа в секундах
mu = TOTAL_SECONDS / 2  # Среднее значение (12 часов = 43,200 секунд)
sigma = TOTAL_SECONDS / 6  # Стандартное отклонение (4 часа = 14,400 секунд)

# Функция масштабирования времени
def scale_time(timestamps, target_duration_minutes):
    """
    Масштабирует временные метки, чтобы уложиться в target_duration_minutes минут.
    timestamps: массив временных меток в секундах (0–86,400)
    target_duration_minutes: желаемая длительность в минутах
    Возвращает масштабированные временные метки.
    """
    target_duration_seconds = target_duration_minutes * 60
    scale_factor = target_duration_seconds / TOTAL_SECONDS
    return timestamps * scale_factor

# Генерация временных меток
timestamps = np.random.normal(mu, sigma, NUM_TRANSACTIONS)
timestamps = np.clip(timestamps, 0, TOTAL_SECONDS)  # Ограничение диапазона
timestamps.sort()

# Визуализация ожидаемого распределения транзакций
plt.hist(timestamps / 3600, bins=100, density=True, color='blue', alpha=0.7)
plt.xlabel('Время (часы)')
plt.ylabel('Плотность транзакций')
plt.title('Ожидаемое распределение 30,000 транзакций за 24 часа')
plt.grid(True)
plt.show()

# Масштабирование времени (например, 24 часа в 30 минут)
SIMULATION_DURATION_MINUTES = 30  # Длительность симуляции в минутах
scaled_timestamps = scale_time(timestamps, SIMULATION_DURATION_MINUTES)
scaled_timestamps.sort()

# Вычисление интервалов между транзакциями
intervals = np.diff(scaled_timestamps, prepend=0)

# Отправка транзакций на сервер и сохранение фактических временных меток
actual_timestamps = []  # Для хранения фактического времени отправки
print("Начало отправки транзакций...")
start_time = time.time()
for i, interval in enumerate(intervals):
    time.sleep(interval)  # Задержка перед отправкой
    current_time = time.time() - start_time  # Текущее время с начала симуляции
    actual_timestamps.append(current_time)  # Сохранение фактической метки времени

    file_path = os.path.join(OUTPUT_DIR, f"txn_{i+1:06d}.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    try:
        resp = requests.post(
            SENDER_URL,
            json={"data": payload["data"], "format": "json"},
            timeout=10
        )
        resp.raise_for_status()
        print(f"[{i+1:06d}] Отправлено → {resp.status_code}: {resp.json()}")
    except Exception as e:
        print(f"[{i+1:06d}] Ошибка отправки: {e}")

    if i % 1000 == 0:
        print(f"Отправлено {i+1} транзакций")

end_time = time.time()
print(f"Отправка завершена. Время выполнения: {(end_time - start_time):.2f} секунд")

# Обратное масштабирование фактических временных меток для отображения в 24-часовом формате
actual_timestamps = np.array(actual_timestamps)
scale_factor = (SIMULATION_DURATION_MINUTES * 60) / TOTAL_SECONDS
actual_timestamps_rescaled = actual_timestamps / scale_factor

# Визуализация фактического распределения
plt.hist(actual_timestamps_rescaled / 3600, bins=100, density=True, color='green', alpha=0.7)
plt.xlabel('Время (часы)')
plt.ylabel('Плотность транзакций')
plt.title('Фактическое распределение 30,000 транзакций за 24 часа')
plt.grid(True)
plt.show()

# Закрытие соединения с базой данных
cur.close()
conn.close()
