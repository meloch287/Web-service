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
# Создание директории и подключение к базе данных
os.makedirs(OUTPUT_DIR, exist_ok=True)
conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
conn.autocommit = True
cur = conn.cursor()
cur.execute(SCHEMA_SQL)
cur.execute("DELETE FROM users")

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

    cur.execute("""
        INSERT INTO users(client_id, pam, full_name, account, address, direction, bic)
        VALUES (%s, %s, %s, %s, %s, 'Out', %s)
        ON CONFLICT (client_id) DO NOTHING
    """, (client_id, pam, name, account, address, bic))

    users.append({"client_id": client_id, "pam": pam, "full_name": name, "account": account,
                  "address": address, "direction": "Out", "bic": bic})

conn.commit()
print(f"Вставлено {len(users)} пользователей в базу данных.")

# --- Загрузка шаблона транзакции ---
if not os.path.exists(TEMPLATE_FILE):
    raise FileNotFoundError(f"Файл: '{TEMPLATE_FILE}' не найден.")
with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
    template = json.load(f)
base_data = template['data'][0]['Data']

# --- Генерация транзакций ---
for n in range(1, NUM_TRANSACTIONS + 1):
    trn_id = f"{n:06d}"
    payer = random.choice(users)
    beneficiary = random.choice(users)
    while beneficiary['client_id'] == payer['client_id']:
        beneficiary = random.choice(users)
    amount = round(random.uniform(1, 150000), 2)
    narrative = random.choice(['Перевод по СБП', 'Оплата услуг', 'Перевод другу', ''])

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

    file_path = os.path.join(OUTPUT_DIR, f'txn_{trn_id}.json')
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump({'data': data_payload}, f, ensure_ascii=False, indent=2)

    if n % 1000 == 0:
        print(f"Создано {n} транзакций...")

print("Создание транзакций завершено.")

# --- Параметры для генерации времени ---
TOTAL_HOURS = 24
A = NUM_TRANSACTIONS
mu_main = 12.0
sigma_main = 4.0
hours = np.linspace(0, 24, NUM_TRANSACTIONS)

# Основной трафик
base_traffic = (A / (sigma_main * np.sqrt(2 * np.pi))) * \
               np.exp(-((hours - mu_main)**2) / (2 * sigma_main**2))

# Функции распределений аномалий (без изменений)
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

# Параметры распределений (без изменений)
anomaly_types = ['normal', 'exponential', 'poisson', 'pareto']
anomaly_params = {
    'normal': {'sigma': 2.0, 'amp': 0.3},  
    'exponential': {'sigma': 2.0, 'amp': 0.05, 'lam': 1/3},
    'poisson': {'sigma': 2.0, 'amp': 0.3, 'lam': 5},  
    'pareto': {'sigma': 2.5, 'amp': 0.1, 'alpha': 2.5, 't_min': 0.1, 't_max': 2.0}
}

# Генерация комбинированной плотности с тремя случайными аномалиями
combined_density = base_traffic.copy()
for _ in range(3):
    anomaly_time = np.random.uniform(0, 24)
    anomaly_type = random.choice(anomaly_types)
    if anomaly_type == 'normal':
        anomaly_density = normal_anomaly(hours, anomaly_time, anomaly_params['normal']['sigma'], anomaly_params['normal']['amp'])
    elif anomaly_type == 'exponential':
        anomaly_density = exponential_anomaly(hours, anomaly_time, anomaly_params['exponential']['sigma'], anomaly_params['exponential']['amp'], anomaly_params['exponential']['lam'])
    elif anomaly_type == 'poisson':
        anomaly_density = poisson_anomaly(hours, anomaly_time, anomaly_params['poisson']['sigma'], anomaly_params['poisson']['amp'], anomaly_params['poisson']['lam'])
    elif anomaly_type == 'pareto':
        anomaly_density = pareto_anomaly(hours, anomaly_time, anomaly_params['pareto']['sigma'], anomaly_params['pareto']['amp'], anomaly_params['pareto']['alpha'], anomaly_params['pareto']['t_min'], anomaly_params['pareto']['t_max'])
    combined_density += anomaly_density

cdf = np.cumsum(combined_density)
cdf = cdf / cdf[-1]  # Нормировка
u = np.random.uniform(0, 1, NUM_TRANSACTIONS)
send_hours = np.interp(u, cdf, hours)

# Масштабирование к 30 минутам (1800 секунд)
total_sim_seconds = 30 * 2
scale_factor = total_sim_seconds / 24
send_times = send_hours * scale_factor

# Сортировка и вычисление задержек
send_times.sort()
delays = np.diff(send_times, prepend=0)

# Визуализация ожидаемой нагрузки
plt.plot(hours, combined_density / combined_density.sum() * 24, label='Ожидаемая нагрузка')
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
            json={"data": payload["data"], "format": "json"},
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

# --- Визуализация фактической и ожидаемой нагрузки ---
actual_hours = send_times / total_sim_seconds * 24  # Используем send_times вместо actual_timestamps

# Нормализация ожидаемой нагрузки
combined_density_normalized = combined_density / np.trapz(combined_density, hours)

# Создание гистограммы для фактической нагрузки
plt.hist(actual_hours, bins=50, density=True, alpha=0.7, label='Фактическая нагрузка (гистограмма)', color='green')

# Наложение ожидаемой нагрузки
plt.plot(hours, combined_density_normalized, label='Ожидаемая нагрузка', color='blue')

plt.title("Сравнение ожидаемой и фактической нагрузки")
plt.xlabel("Часы")
plt.ylabel("Плотность")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("comparison_load_with_anomaly.png")
plt.show()

# --- Закрытие соединения ---
cur.close()
conn.close()
