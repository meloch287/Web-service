import os
import json
import random
import time
from datetime import datetime
import requests
import psycopg2
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm, gaussian_kde
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

# SQL схема отправителя (таблицы users и transactions) с новыми столбцами

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
    "is_bad" BOOLEAN DEFAULT FALSE, -- Флаг хорошая/плохая
    "epoch_number" BIGINT DEFAULT 1, -- Номер эпохи
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

# Создание директории и подключение к базе данных

os.makedirs(OUTPUT_DIR, exist_ok=True)
conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
conn.autocommit = True
cur = conn.cursor()
cur.execute(SCHEMA_SQL)
cur.execute("DELETE FROM transactions")  # Очистка transactions перед clients
cur.execute("DELETE FROM users")
cur.execute("DELETE FROM clients")
cur.execute("DELETE FROM transaction_types")
cur.execute("DELETE FROM banks")
cur.execute("DELETE FROM transaction_status")
cur.execute("DELETE FROM bank_account")  # Очистка bank_account для полноты

# --- Генерация пользователей ---

fake = Faker('ru_RU')
users = []
for i in range(1, NUM_USERS + 1):
    client_id = f"{i:08d}"
    name = fake.name()
    pam = name[:100]
    account = '40817' + ''.join(random.choice('0123456789') for _ in range(16))
    address = fake.address().replace('\n', ', ')
    bic = random.choice(BIC_CODES)

    # Вставка в таблицу clients
    cur.execute("""
        INSERT INTO clients (name, comment)
        VALUES (%s, %s) RETURNING id
    """, (name, f"Клиент {client_id}"))
    client_db_id = cur.fetchone()[0]

    # Вставка в таблицу users
    cur.execute("""
        INSERT INTO users(client_id, pam, full_name, account, address, direction, bic)
        VALUES (%s, %s, %s, %s, %s, 'Out', %s)
        ON CONFLICT (client_id) DO NOTHING
    """, (client_id, pam, name, account, address, bic))

    users.append({
        "ClientId": client_id,
        "PAM": pam,
        "FullName": name,
        "Account": account,
        "Address": address,
        "Direction": "Out",
        "PayerBIC": bic,
        "db_id": client_db_id  # Добавляем ID из clients для использования в transactions
    })

conn.commit()
print(f"Вставлено {len(users)} пользователей в базу данных.")

# --- Загрузка шаблона транзакции ---

if not os.path.exists(TEMPLATE_FILE):
    raise FileNotFoundError(f"Файл: '{TEMPLATE_FILE}' не найден.")
with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    template = json.load(f)
base_data = template['data'][0]['Data']

# --- Параметры для генерации времени ---

TOTAL_HOURS = 24
A = NUM_TRANSACTIONS
mu_main = 12.0
sigma_main = 4.0
hours = np.linspace(0, 24, NUM_TRANSACTIONS)

# Основной трафик

base_traffic = (A / (sigma_main * np.sqrt(2 * np.pi))) * \
               np.exp(-((hours - mu_main)**2) / (2 * sigma_main**2))

# Функции распределений аномалий

def normal_anomaly(hours, mu, sigma, amp):
    A_anom = A * amp
    return (A_anom / (sigma * np.sqrt(2 * np.pi))) * \
           np.exp(-((hours - mu)**2) / (2 * sigma**2))

def exponential_anomaly(hours, mu, sigma, amp, lam):
    A_anom = A * amp
    exp_part = lam * np.exp(-lam * (hours - mu))
    exp_part[hours < mu] = 0
    return exp_part * A_anom

def poisson_anomaly(hours, mu, sigma, amp, lam):
    A_anom = A * amp
    return (A_anom / (sigma * np.sqrt(2 * np.pi))) * \
           np.exp(-((hours - mu)**2)/(2 * sigma**2)) + lam

def pareto_anomaly(hours, mu, sigma, amp, alpha, t_min, t_max):
    B = A * amp
    norm = (alpha * t_min**alpha) / (1 - (t_min/t_max)**alpha)
    pdf = np.zeros_like(hours)
    mask = (hours >= t_min + mu) & (hours <= t_max + mu)
    pdf[mask] = B * norm * (hours[mask] - mu)**(-alpha - 1)
    return pdf

# Параметры распределений

anomaly_types = ['normal', 'exponential', 'poisson', 'pareto']
anomaly_params = {
    'normal': {'sigma': 2.0, 'amp': 0.5},
    'exponential': {'sigma': 2.0, 'amp': 0.1, 'lam': 1/10},
    'poisson': {'sigma': 2.0, 'amp': 0.5, 'lam': 1/5},
    'pareto': {'sigma': 1.5, 'amp': 0.2, 'alpha': 1.5, 't_min': 0.1, 't_max': 2.0}
}

# Генерация комбинированной плотности с тремя случайными аномалиями

combined_density = base_traffic.copy()
anomaly_windows = []
for _ in range(3):
    anomaly_time = np.random.uniform(0, 24)
    anomaly_type = random.choice(anomaly_types)
    if anomaly_type == 'normal':
        anomaly_density = normal_anomaly(hours, anomaly_time, anomaly_params['normal']['sigma'], anomaly_params['normal']['amp'])
        window = (max(0, anomaly_time - anomaly_params['normal']['sigma'] * 2), 
                 min(24, anomaly_time + anomaly_params['normal']['sigma'] * 2))
    elif anomaly_type == 'exponential':
        anomaly_density = exponential_anomaly(hours, anomaly_time, anomaly_params['exponential']['sigma'], 
                                             anomaly_params['exponential']['amp'], anomaly_params['exponential']['lam'])
        window = (max(0, anomaly_time), min(24, anomaly_time + 2))
    elif anomaly_type == 'poisson':
        anomaly_density = poisson_anomaly(hours, anomaly_time, anomaly_params['poisson']['sigma'], 
                                         anomaly_params['poisson']['amp'], anomaly_params['poisson']['lam'])
        window = (max(0, anomaly_time - anomaly_params['poisson']['sigma'] * 2), 
                 min(24, anomaly_time + anomaly_params['poisson']['sigma'] * 2))
    elif anomaly_type == 'pareto':
        anomaly_density = pareto_anomaly(hours, anomaly_time, anomaly_params['pareto']['sigma'], 
                                        anomaly_params['pareto']['amp'], anomaly_params['pareto']['alpha'], 
                                        anomaly_params['pareto']['t_min'], anomaly_params['pareto']['t_max'])
        window = (max(0, anomaly_time + anomaly_params['pareto']['t_min']), 
                 min(24, anomaly_time + anomaly_params['pareto']['t_max']))
    combined_density += anomaly_density
    anomaly_windows.append(window)

cdf = np.cumsum(combined_density)
cdf = cdf / cdf[-1]  # Нормировка
u = np.random.uniform(0, 1, NUM_TRANSACTIONS)
send_hours = np.interp(u, cdf, hours)

# Масштабирование к 60 секундам

total_sim_seconds = 30 * 2  # 60 секунд
scale_factor = total_sim_seconds / 24
send_times = send_hours * scale_factor

# Сортировка и вычисление задержек

send_times.sort()
delays = np.diff(send_times, prepend=0)

# --- Обновление таблицы transactions для добавления столбцов is_bad и epoch_number ---

try:
    cur.execute("""
        ALTER TABLE transactions
        ADD COLUMN IF NOT EXISTS is_bad BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS epoch_number BIGINT DEFAULT 1
    """)
    conn.commit()
    print("Столбцы is_bad и epoch_number добавлены или уже существуют в таблице transactions.")
except Exception as e:
    print(f"Ошибка при обновлении таблицы transactions: {e}")
    conn.rollback()

# --- Заполнение связанных таблиц для внешних ключей ---

# Вставка типа транзакции
cur.execute("""
    INSERT INTO transaction_types (type)
    VALUES ('C2C') ON CONFLICT DO NOTHING
    RETURNING id
""")
result = cur.fetchone()
if result:
    type_id = result[0]
else:
    cur.execute("SELECT id FROM transaction_types WHERE type = 'C2C'")
    type_id = cur.fetchone()[0]

# Вставка банка
cur.execute("""
    INSERT INTO banks (bank_name)
    VALUES ('Default Bank') ON CONFLICT DO NOTHING
    RETURNING id
""")
result = cur.fetchone()
if result:
    bank_id = result[0]
else:
    cur.execute("SELECT id FROM banks WHERE bank_name = 'Default Bank'")
    bank_id = cur.fetchone()[0]

# Вставка статуса транзакции
cur.execute("""
    INSERT INTO transaction_status (status)
    VALUES ('Pending') ON CONFLICT DO NOTHING
    RETURNING id
""")
result = cur.fetchone()
if result:
    status_id = result[0]
else:
    cur.execute("SELECT id FROM transaction_status WHERE status = 'Pending'")
    status_id = cur.fetchone()[0]

conn.commit()
print("Таблицы transaction_types, banks и transaction_status заполнены.")

# --- Генерация транзакций с флагами хорошая/плохая и сбором данных для проверки ---

bad_transaction_hours = []  # Для хранения времени "плохих" транзакций
good_transaction_hours = []  # Для хранения времени "хороших" транзакций
bad_transaction_count = 0  # Счётчик плохих транзакций

for n in range(1, NUM_TRANSACTIONS + 1):
    trn_id = f"{n:06d}"
    payer = random.choice(users)
    beneficiary = random.choice(users)
    while beneficiary['ClientId'] == payer['ClientId']:
        beneficiary = random.choice(users)
    amount = round(random.uniform(1, 150000), 2)
    narrative = random.choice(['Перевод по СБП', 'Оплата услуг', 'Перевод другу', ''])

    # Определение, является ли транзакция "плохой" на основе времени
    current_hour = send_hours[n-1]
    is_bad = False
    for window in anomaly_windows:
        if window[0] <= current_hour <= window[1]:
            is_bad = random.random() < 0.7  # 70% вероятность, что транзакция плохая
            break

    # Сбор данных для визуализации и проверки
    if is_bad:
        bad_transaction_hours.append(current_hour)
        bad_transaction_count += 1
    else:
        good_transaction_hours.append(current_hour)

    # Формирование данных получателя
    beneficiary_data = {
        "PAM": beneficiary["PAM"],
        "FullName": beneficiary["FullName"],
        "BeneficiaryBIC": random.choice(BIC_CODES)
    }

    data_payload = dict(base_data)
    data_payload.update({
        'CurrentTimestamp': datetime.utcnow().isoformat() + 'Z',
        'TrnId': trn_id,
        'TrnType': 'C2C',
        'PayerData': payer,
        'BeneficiaryData': beneficiary_data,
        'Amount': str(amount),
        'Currency': 'RUB',
        'Narrative': narrative,
        'IsBad': is_bad,
        'EpochNumber': 1
    })

    # Формирование структуры для сохранения
    file_payload = {
        "data": [{"Data": data_payload}],
        "format": "json"
    }

    file_path = os.path.join(OUTPUT_DIR, f'txn_{trn_id}.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(file_payload, f, ensure_ascii=False, indent=2)

    # Запись в таблицу transactions с учетом всех внешних ключей
    cur.execute("""
        INSERT INTO transactions (src_id, dst_id, type_id, bnk_src_id, bnk_dst_id, status_id, value, timestamp, comment, is_bad, epoch_number)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (payer['db_id'], beneficiary['db_id'], type_id, bank_id, bank_id, status_id, amount, datetime.utcnow(), narrative, is_bad, 1))

    if n % 1000 == 0:
        print(f"Создано {n} транзакций...")

conn.commit()
print("Создание транзакций завершено.")
print(f"Всего транзакций: {NUM_TRANSACTIONS}")
print(f"Плохих транзакций: {bad_transaction_count} ({bad_transaction_count / NUM_TRANSACTIONS * 100:.2f}%)")
print(f"Хороших транзакций: {NUM_TRANSACTIONS - bad_transaction_count} ({(NUM_TRANSACTIONS - bad_transaction_count) / NUM_TRANSACTIONS * 100:.2f}%)")

# --- Проверка содержимого JSON-файлов (первые 5 транзакций) ---

print("\nПроверка первых 5 JSON-файлов:")
for n in range(1, min(6, NUM_TRANSACTIONS + 1)):
    file_path = os.path.join(OUTPUT_DIR, f'txn_{n:06d}.json')
    with open(file_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)
        is_bad = payload['data'][0]['Data']['IsBad']
        epoch_number = payload['data'][0]['Data']['EpochNumber']
        print(f"Транзакция {n:06d}: IsBad = {is_bad}, EpochNumber = {epoch_number}")

# --- Визуализация ожидаемой нагрузки ---

plt.figure(figsize=(10, 6))
plt.plot(hours, combined_density / combined_density.sum() * 24, label='Ожидаемая нагрузка')
for window in anomaly_windows:
    plt.axvspan(window[0], window[1], color='yellow', alpha=0.2, label='Окно аномалии' if window == anomaly_windows[0] else "")
plt.title('Ожидаемое распределение нагрузки с аномалиями')
plt.xlabel('Часы суток')
plt.ylabel('Плотность')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("combined_intensity_with_anomaly.png")
plt.show()

# --- Отправка транзакций ---

print("Начало отправки транзакций...")
start_time = time.time()
actual_timestamps = []
for i, delay in enumerate(delays):
    time.sleep(delay)
    current_time = time.time() - start_time
    actual_timestamps.append(current_time)

    file_path = os.path.join(OUTPUT_DIR, f"txn_{i+1:06d}.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    try:
        resp = requests.post(
            SENDER_URL,
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        print(f"[{i+1:06d}] Отправлено → {resp.status_code}: {resp.json()}")
    except Exception as e:
        print(f"[{i+1:06d}] Ошибка отправки: {e}")

end_time = time.time()
print(f"Отправка завершена. Время выполнения: {end_time - start_time:.2f} секунд")

# Проверка общего времени симуляции

total_simulation_time = send_times[-1]
print(f"Общее время симуляции: {total_simulation_time:.2f} секунд")

# --- Визуализация фактической, ожидаемой нагрузки и плохих транзакций ---

actual_hours = send_times / total_sim_seconds * 24
bad_hours = np.array(bad_transaction_hours)  # Время плохих транзакций
good_hours = np.array(good_transaction_hours)  # Время хороших транзакций

# Нормализация ожидаемой нагрузки
combined_density_normalized = combined_density / np.trapezoid(combined_density, hours)

# Создание фигуры
plt.figure(figsize=(10, 6))

# Гистограмма для всех транзакций
plt.hist(actual_hours, bins=50, density=True, alpha=0.5, label='Фактическая нагрузка (все)', color='green')

# Гистограмма для плохих транзакций
if len(bad_hours) > 0:
    plt.hist(bad_hours, bins=50, density=True, alpha=0.7, label='Плохие транзакции', color='red')

# Наложение ожидаемой нагрузки
plt.plot(hours, combined_density_normalized, label='Ожидаемая нагрузка', color='blue', linewidth=2)

# Добавление окон аномалий
for window in anomaly_windows:
    plt.axvspan(window[0], window[1], color='yellow', alpha=0.2, label='Окно аномалии' if window == anomaly_windows[0] else "")

plt.title("Сравнение ожидаемой и фактической нагрузки с плохими транзакциями")
plt.xlabel("Часы")
plt.ylabel("Плотность")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("comparison_load_with_anomaly_and_bad.png")
plt.show()

# --- Проверка распределения плохих транзакций по окнам аномалий ---

print("\nАнализ плохих транзакций по окнам аномалий:")
for i, window in enumerate(anomaly_windows, 1):
    bad_in_window = sum(1 for h in bad_transaction_hours if window[0] <= h <= window[1])
    total_in_window = sum(1 for h in send_hours if window[0] <= h <= window[1])
    print(f"Окно {i} ({window[0]:.2f} - {window[1]:.2f} ч):")
    print(f"  Всего транзакций: {total_in_window}")
    print(f"  Плохих транзакций: {bad_in_window} ({bad_in_window / total_in_window * 100:.2f}% если всего > 0)")

# --- Закрытие соединения ---

cur.close()
conn.close()
