import os
import json
import random
import time
from datetime import datetime
import requests
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import SimpleConnectionPool
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
from faker import Faker
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from tenacity import retry, stop_after_attempt, wait_fixed

# Настройка логирования
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- Настройки базы данных ---
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

# --- Параметры генерации ---
NUM_USERS = 100
NUM_TRANSACTIONS = 30000
OUTPUT_DIR = 'generated_transactions'
TEMPLATE_FILE = 'payload_template.json'
SENDER_URL = "http://localhost:5000/send"
MAX_RETRIES = 3
RETRY_DELAY = 2

# Реестр BIC-кодов
BIC_CODES = [
    '044525225', '044525226', '044525227', '044525228',
    '044525229', '044525230', '044525231', '044525232',
    '044525233', '044525234'
]

# SQL схема
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
    "is_bad" BOOLEAN DEFAULT FALSE,
    "epoch_number" BIGINT DEFAULT 1,
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

# --- Пул соединений с базой данных ---
db_pool = SimpleConnectionPool(1, 20, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)

# --- Функция для получения соединения из пула --
def get_db_connection():
    try:
        return db_pool.getconn()
    except psycopg2.OperationalError as e:
        logging.error(f"Ошибка получения соединения из пула: {str(e)}")
        raise

# --- Функция для возврата соединения в пул ---
def release_db_connection(conn):
    db_pool.putconn(conn)

# --- Повторные попытки подключения к базе данных ---
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def connect_to_db():
    try:
        conn = get_db_connection()
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Ошибка подключения к БД: {str(e)}")
        raise

# --- Проверка целостности данных пользователя ---
def validate_user(user: dict) -> bool:
    required_fields = ["ClientId", "PAM", "FullName", "Account", "Address", "PayerBIC"]
    return all(field in user for field in required_fields)

# --- Проверка целостности данных транзакции ---
def validate_transaction(data_payload: dict) -> bool:
    required_fields = ["TrnId", "TrnType", "PayerData", "BeneficiaryData", "Amount", "Currency"]
    return all(field in data_payload for field in required_fields)

# --- Функция отправки транзакции ---
def send_transaction(payload: dict, max_retries: int = MAX_RETRIES, retry_delay: float = RETRY_DELAY) -> bool:
    try:
        if not validate_transaction(payload['data'][0]['Data']):
            logging.error(f"Некорректные данные транзакции: {payload['data'][0]['Data']['TrnId']}")
            return False

        trn_id = payload['data'][0]['Data']['TrnId']
        logging.info(f"Отправка транзакции: TrnId={trn_id}")
        
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    SENDER_URL,
                    json=payload,
                    timeout=15
                )
                resp.raise_for_status()
                logging.info(f"[{trn_id}] Успешная отправка (попытка {attempt}): {resp.status_code}: {resp.json()}")
                print(f"[{trn_id}] Отправлено → {resp.status_code}: {resp.json()}")
                return True
            except requests.exceptions.Timeout as e:
                logging.error(f"[{trn_id}] Таймаут отправки (попытка {attempt}): {str(e)}")
                print(f"[{trn_id}] Таймаут отправки (попытка {attempt}): {str(e)}")
            except requests.exceptions.HTTPError as e:
                logging.error(f"[{trn_id}] HTTP ошибка (попытка {attempt}): {str(e)}")
                print(f"[{trn_id}] HTTP ошибка (попытка {attempt}): {str(e)}")
            except requests.exceptions.RequestException as e:
                logging.error(f"[{trn_id}] Ошибка отправки (попытка {attempt}): {str(e)}")
                print(f"[{trn_id}] Ошибка отправки (попытка {attempt}): {str(e)}")
                
                if attempt < max_retries:
                    logging.info(f"[{trn_id}] Ожидание {retry_delay} секунд перед повторной попыткой...")
                    time.sleep(retry_delay)
                else:
                    logging.error(f"[{trn_id}] Все попытки отправки исчерпаны")
                    return False
    except Exception as e:
        logging.error(f"Общая ошибка при отправке транзакции: {str(e)}")
        logging.error(traceback.format_exc())
        print(f"Ошибка отправки: {e}")
        return False

# --- Параллельная отправка транзакций  ---
def send_transactions_parallel(payloads: list, max_workers: int = 10) -> tuple:
    successful = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(send_transaction, payload) for payload in payloads]
        for future in as_completed(futures):
            if future.result():
                successful += 1
            else:
                failed += 1
    logging.info(f"Успешно отправлено: {successful}, Не удалось отправить: {failed}")
    print(f"Успешно отправлено: {successful}, Не удалось отправить: {failed}")
    return successful, failed

# --- Инициализация базы данных  ---
try:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logging.info(f"Директория {OUTPUT_DIR} создана/проверена")
    
    conn = connect_to_db()
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    logging.info("Схема БД создана/обновлена")
except psycopg2.OperationalError as e:
    logging.error(f"Ошибка подключения к БД: {str(e)}")
    logging.error(traceback.format_exc())
    raise
except psycopg2.DatabaseError as e:
    logging.error(f"Ошибка базы данных: {str(e)}")
    logging.error(traceback.format_exc())
    raise
finally:
    if 'conn' in locals():
        release_db_connection(conn)

# --- Генерация пользователей с пакетной вставкой и игнорированием дубликатов  ---
fake = Faker('ru_RU')
users = []
try:
    conn = get_db_connection()
    with conn.cursor() as cur:
        client_data = []
        user_data = []
        for i in range(1, NUM_USERS + 1):
            client_id = f"{i:08d}"
            name = fake.name()
            account = '40817' + ''.join(random.choice('0123456789') for _ in range(16))
            address = fake.address().replace('\n', ', ')
            bic = random.choice(BIC_CODES)
            user = {
                "ClientId": client_id,
                "PAM": name[:100],
                "FullName": name,
                "Account": account,
                "Address": address,
                "Direction": "Out",
                "PayerBIC": bic
            }
            if not validate_user(user):
                logging.error(f"Некорректные данные пользователя: {client_id}")
                continue
            users.append(user)
            client_data.append((name, f"Клиент {client_id}"))
            user_data.append((client_id, name[:100], name, account, address, "Out", bic))

        # Пакетная вставка в clients
        execute_values(
            cur,
            "INSERT INTO clients (name, comment) VALUES %s RETURNING id",
            client_data,
            page_size=1000
        )
        client_ids = cur.fetchall()

        # Пакетная вставка в users с игнорированием дубликатов
        execute_values(
            cur,
            """
            INSERT INTO users (client_id, pam, full_name, account, address, direction, bic)
            VALUES %s
            ON CONFLICT (client_id) DO NOTHING
            """,
            user_data,
            page_size=1000
        )

        # Обновление users с db_id только для новых записей
        cur.execute("SELECT client_id FROM users")
        existing_client_ids = {row[0] for row in cur.fetchall()}
        filtered_users = []
        for u, client_id in zip(users, client_ids):
            if u["ClientId"] in existing_client_ids:
                u["db_id"] = client_id[0]
                filtered_users.append(u)
            else:
                logging.info(f"Пользователь с client_id {u['ClientId']} уже существует, пропущен")
        users = filtered_users

    conn.commit()
    logging.info(f"Вставлено или обновлено {len(users)} пользователей в базу данных")
    print(f"Вставлено или обновлено {len(users)} пользователей в базу данных.")
except psycopg2.DatabaseError as e:
    logging.error(f"Ошибка при генерации пользователей: {str(e)}")
    logging.error(traceback.format_exc())
    conn.rollback()
    raise
finally:
    release_db_connection(conn)

# --- Загрузка и кэширование шаблона транзакции ---
try:
    if not os.path.exists(TEMPLATE_FILE):
        logging.error(f"Файл: '{TEMPLATE_FILE}' не найден")
        raise FileNotFoundError(f"Файл: '{TEMPLATE_FILE}' не найден.")
    
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = json.load(f)
    base_data = template['data'][0]['Data']
    logging.info(f"Шаблон транзакции загружен из {TEMPLATE_FILE}")
except FileNotFoundError as e:
    logging.error(f"Ошибка при загрузке шаблона: {str(e)}")
    raise
except json.JSONDecodeError as e:
    logging.error(f"Ошибка декодирования JSON шаблона: {str(e)}")
    raise

# --- Параметры для генерации времени ---
TOTAL_HOURS = 24
A = NUM_TRANSACTIONS
mu_main = 12.0
sigma_main = 4.0
hours = np.linspace(0, 24, NUM_TRANSACTIONS)

base_traffic = (A / (sigma_main * np.sqrt(2 * np.pi))) * \
               np.exp(-((hours - mu_main)**2) / (2 * sigma_main**2))

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

anomaly_types = ['normal', 'exponential', 'poisson', 'pareto']
anomaly_params = {
    'normal': {'sigma': 2.0, 'amp': 0.5},
    'exponential': {'sigma': 2.0, 'amp': 0.1, 'lam': 1/10},
    'poisson': {'sigma': 2.0, 'amp': 0.5, 'lam': 1/5},
    'pareto': {'sigma': 1.5, 'amp': 0.2, 'alpha': 1.5, 't_min': 0.1, 't_max': 2.0}
}

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
cdf = cdf / cdf[-1]
u = np.random.uniform(0, 1, NUM_TRANSACTIONS)
send_hours = np.interp(u, cdf, hours)

total_sim_seconds = 30 * 2
scale_factor = total_sim_seconds / 24
send_times = send_hours * scale_factor
send_times.sort()
delays = np.diff(send_times, prepend=0)

# --- Обновление таблицы transactions  ---
try:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE transactions
            ADD COLUMN IF NOT EXISTS is_bad BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS epoch_number BIGINT DEFAULT 1
        """)
    conn.commit()
    logging.info("Столбцы is_bad и epoch_number добавлены или уже существуют")
except psycopg2.DatabaseError as e:
    logging.error(f"Ошибка при обновлении таблицы transactions: {str(e)}")
    logging.error(traceback.format_exc())
    conn.rollback()
    print(f"Ошибка при обновлении таблицы transactions: {e}")
finally:
    release_db_connection(conn)

# --- Заполнение связанных таблиц  ---
try:
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO transaction_types (type)
            VALUES ('C2C') ON CONFLICT DO NOTHING
            RETURNING id
        """)
        result = cur.fetchone()
        type_id = result[0] if result else cur.execute("SELECT id FROM transaction_types WHERE type = 'C2C'").fetchone()[0]

        cur.execute("""
            INSERT INTO banks (bank_name)
            VALUES ('Default Bank') ON CONFLICT DO NOTHING
            RETURNING id
        """)
        result = cur.fetchone()
        bank_id = result[0] if result else cur.execute("SELECT id FROM banks WHERE bank_name = 'Default Bank'").fetchone()[0]

        cur.execute("""
            INSERT INTO transaction_status (status)
            VALUES ('Pending') ON CONFLICT DO NOTHING
            RETURNING id
        """)
        result = cur.fetchone()
        status_id = result[0] if result else cur.execute("SELECT id FROM transaction_status WHERE status = 'Pending'").fetchone()[0]

    conn.commit()
    logging.info("Таблицы transaction_types, banks и transaction_status заполнены")
except psycopg2.DatabaseError as e:
    logging.error(f"Ошибка при заполнении связанных таблиц: {str(e)}")
    logging.error(traceback.format_exc())
    conn.rollback()
    print(f"Ошибка при заполнении связанных таблиц: {e}")
finally:
    release_db_connection(conn)

# --- Генерация транзакций с пакетной вставкой ---
bad_transaction_hours = []
good_transaction_hours = []
bad_transaction_count = 0
payloads = []

try:
    conn = get_db_connection()
    transaction_data = []
    for n in range(1, NUM_TRANSACTIONS + 1):
        trn_id = f"{n:06d}"
        payer = random.choice(users)
        beneficiary = random.choice(users)
        while beneficiary['ClientId'] == payer['ClientId']:
            beneficiary = random.choice(users)
        amount = round(random.uniform(1, 150000), 2)
        narrative = random.choice(['Перевод по СБП', 'Оплата услуг', 'Перевод другу', ''])

        current_hour = send_hours[n-1]
        is_bad = False
        for window in anomaly_windows:
            if window[0] <= current_hour <= window[1]:
                is_bad = random.random() < 0.7
                break

        if is_bad:
            bad_transaction_hours.append(current_hour)
            bad_transaction_count += 1
        else:
            good_transaction_hours.append(current_hour)

        beneficiary_data = {
            "PAM": beneficiary["PAM"],
            "FullName": beneficiary["FullName"],
            "BeneficiaryBIC": random.choice(BIC_CODES)
        }

        data_payload = deepcopy(base_data)  # Кэширование шаблона 
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

        file_payload = {
            "data": [{"Data": data_payload}],
            "format": "json"
        }
        payloads.append(file_payload)

        # Сохранение в файл (2.3, опционально)
        file_path = os.path.join(OUTPUT_DIR, f'txn_{trn_id}.json')
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(file_payload, f, ensure_ascii=False, indent=2)

        transaction_data.append((
            payer['db_id'], beneficiary['db_id'], type_id, bank_id, bank_id, status_id,
            amount, datetime.utcnow(), narrative, is_bad, 1
        ))

        if n % 1000 == 0:
            logging.info(f"Создано {n} транзакций")
            print(f"Создано {n} транзакций...")

    # Пакетная вставка транзакций
    with conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO transactions (src_id, dst_id, type_id, bnk_src_id, bnk_dst_id, status_id, value, timestamp, comment, is_bad, epoch_number) VALUES %s",
            transaction_data,
            page_size=1000
        )
    conn.commit()
    logging.info("Создание транзакций завершено")
    print(f"Всего транзакций: {NUM_TRANSACTIONS}")
    print(f"Плохих транзакций: {bad_transaction_count} ({bad_transaction_count / NUM_TRANSACTIONS * 100:.2f}%)")
except psycopg2.DatabaseError as e:
    logging.error(f"Ошибка при генерации транзакций: {str(e)}")
    logging.error(traceback.format_exc())
    conn.rollback()
    print(f"Ошибка при генерации транзакций: {e}")
finally:
    release_db_connection(conn)

# --- Проверка JSON-файлов ---
try:
    print("\nПроверка первых 5 JSON-файлов:")
    for n in range(1, min(6, NUM_TRANSACTIONS + 1)):
        file_path = os.path.join(OUTPUT_DIR, f'txn_{n:06d}.json')
        with open(file_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
            is_bad = payload['data'][0]['Data']['IsBad']
            epoch_number = payload['data'][0]['Data']['EpochNumber']
            print(f"Транзакция {n:06d}: IsBad = {is_bad}, EpochNumber = {epoch_number}")
except FileNotFoundError as e:
    logging.error(f"Ошибка при проверке JSON-файлов: {str(e)}")
    print(f"Ошибка при проверке JSON-файлов: {e}")
except json.JSONDecodeError as e:
    logging.error(f"Ошибка декодирования JSON: {str(e)}")
    print(f"Ошибка декодирования JSON: {e}")

# --- Визуализация ожидаемой нагрузки ---
try:
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
    logging.info("График распределения нагрузки сохранен")
except Exception as e:
    logging.error(f"Ошибка при визуализации нагрузки: {str(e)}")
    print(f"Ошибка при визуализации нагрузки: {e}")

# --- Отправка транзакций (2.2) ---
print("Начало отправки транзакций...")
logging.info("Начало отправки транзакций")
start_time = time.time()
actual_timestamps = []
successful_transactions = 0
failed_transactions = 0

try:
    successful_transactions, failed_transactions = send_transactions_parallel(payloads, max_workers=10)
    end_time = time.time()
    logging.info(f"Отправка завершена. Время выполнения: {end_time - start_time:.2f} секунд")
    print(f"Отправка завершена. Время выполнения: {end_time - start_time:.2f} секунд")
    total_simulation_time = send_times[-1]
    logging.info(f"Общее время симуляции: {total_simulation_time:.2f} секунд")
    print(f"Общее время симуляции: {total_simulation_time:.2f} секунд")
except Exception as e:
    logging.error(f"Ошибка при отправке транзакций: {str(e)}")
    logging.error(traceback.format_exc())
    print(f"Ошибка при отправке транзакций: {e}")

# --- Визуализация фактической нагрузки ---
try:
    actual_hours = send_times / total_sim_seconds * 24
    bad_hours = np.array(bad_transaction_hours)
    good_hours = np.array(good_transaction_hours)
    combined_density_normalized = combined_density / np.trapezoid(combined_density, hours)

    plt.figure(figsize=(10, 6))
    plt.hist(actual_hours, bins=50, alpha=0.3, color='blue', density=True, label='Фактическое распределение')
    if len(bad_hours) > 0:
        plt.hist(bad_hours, bins=30, alpha=0.5, color='red', density=True, label='Плохие транзакции')
    plt.plot(hours, combined_density_normalized, 'k-', linewidth=2, label='Ожидаемая нагрузка')
    for window in anomaly_windows:
        plt.axvspan(window[0], window[1], color='yellow', alpha=0.2, label='Окно аномалии' if window == anomaly_windows[0] else "")
    plt.title('Распределение транзакций по времени')
    plt.xlabel('Часы суток')
    plt.ylabel('Плотность')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("transaction_distribution.png")
    plt.show()
    logging.info("График распределения транзакций сохранен")
except Exception as e:
    logging.error(f"Ошибка при визуализации распределения транзакций: {str(e)}")
    print(f"Ошибка при визуализации распределения транзакций: {e}")

# --- Закрытие пула соединений ---
try:
    db_pool.closeall()
    logging.info("Пул соединений с БД закрыт")
except Exception as e:
    logging.error(f"Ошибка при закрытии пула соединений: {str(e)}")
    print(f"Ошибка при закрытии пула соединений: {e}")

logging.info("Скрипт завершил работу")
print("Скрипт завершил работу.")
