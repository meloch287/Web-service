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

# --- Генерация времени отправки с аномалиями ---
TOTAL_HOURS = 24
A = NUM_TRANSACTIONS  # Амплитуда основного распределения
mu = 12              # Среднее основного распределения (полдень)
sigma = 6            # Стандартное отклонение основного распределения

# Основная плотность (нормальное распределение)
hours = np.linspace(0, 24, NUM_TRANSACTIONS)
main_density = (A / (sigma * np.sqrt(2 * np.pi))) * np.exp(-((hours - mu) ** 2) / (2 * sigma ** 2))

# Типы аномалий и их параметры
anomaly_types = ['poisson', 'pareto', 'exponential']
anomaly_params = {
    'poisson': {'sigma': 0.5, 'amplitude_factor': 0.3},  # Малый разброс, высокая амплитуда
    'pareto': {'sigma': 1.5, 'amplitude_factor': 0.1},   # Средний разброс, средняя амплитуда
    'exponential': {'sigma': 2.0, 'amplitude_factor': 0.05}  # Большой разброс, малая амплитуда
}

# Генерация трех случайных точек для аномалий
anomaly_mus = np.random.uniform(0, 24, 3)

# Инициализация комбинированной плотности
combined_density = main_density.copy()

# Добавление трех аномалий
for anomaly_mu in anomaly_mus:
    if random.random() < 0.9:  # Вероятность 90% для добавления аномалии
        anomaly_type = random.choice(anomaly_types)
        params = anomaly_params[anomaly_type]
        sigma_anomaly = params['sigma']
        amplitude_anomaly = A * params['amplitude_factor']
        anomaly_density = (amplitude_anomaly / (sigma_anomaly * np.sqrt(2 * np.pi))) * np.exp(-((hours - anomaly_mu) ** 2) / (2 * sigma_anomaly ** 2))
        combined_density += anomaly_density

# Вычисление кумулятивной функции распределения (CDF)
cdf = np.cumsum(combined_density)
cdf = cdf / cdf[-1]  # Нормировка CDF

# Генерация времен отправки в часах (от 0 до 24)
u = np.random.uniform(0, 1, NUM_TRANSACTIONS)
send_hours = np.interp(u, cdf, hours)

# Масштабирование времени в секунды симуляции (24 часа → 30 минут)
total_sim_seconds = 30 * 60  # 30 минут в секундах
scale_factor = total_sim_seconds / 24  # Секунды на час
send_times = send_hours * scale_factor

# Сортировка времен и вычисление задержек
send_times.sort()
delays = np.diff(send_times, prepend=0)

# --- Визуализация ожидаемой нагрузки ---
plt.plot(hours, combined_density / combined_density.sum() * 24, label='Ожидаемая нагрузка')
plt.title('Ожидаемое распределение нагрузки с аномалиями')
plt.xlabel('Часы суток')
plt.ylabel('Плотность')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("combined_intensity_with_anomalies.png")
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
actual_hours = send_times / total_sim_seconds * 24

# Использование KDE для сглаживания фактического распределения
kde = gaussian_kde(actual_hours)
x = np.linspace(0, 24, 1000)
plt.plot(x, kde(x), label='Фактическая нагрузка (KDE)', color='green')
plt.plot(hours, combined_density / combined_density.sum() * 24, label='Ожидаемая нагрузка')
plt.title("Сравнение ожидаемой и фактической нагрузки")
plt.xlabel("Часы")
plt.ylabel("Плотность")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("comparison_load_with_anomalies.png")
plt.show()

# --- Закрытие соединения ---
cur.close()
conn.close()
