import os
import json
import random
from datetime import datetime,timezone
import numpy as np
from copy import deepcopy
from psycopg2.extras import execute_values
from .db_config import get_db_connection, release_db_connection
import logging

logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

NUM_TRANSACTIONS = 30000
OUTPUT_DIR = 'generated_transactions'
TEMPLATE_FILE = 'scripts/payload_template.json'

# Коды для разных типов аномалий
ANOMALY_CODES = {
    'normal': 1,      # Нормальное распределение аномалий
    'exponential': 2, # Экспоненциальное распределение аномалий
    'poisson': 3,     # Распределение Пуассона
    'pareto': 4       # Распределение Парето
}

# Код для хороших транзакций
GOOD_TRANSACTION_CODE = 0

BIC_CODES = [
    '044525225', '044525226', '044525227', '044525228',
    '044525229', '044525230', '044525231', '044525232',
    '044525233', '044525234'
]

def load_template():
    """Загрузка шаблона транзакции."""
    try:
        if not os.path.exists(TEMPLATE_FILE):
            logging.error(f"Файл: '{TEMPLATE_FILE}' не найден")
            raise FileNotFoundError(f"Файл: '{TEMPLATE_FILE}' не найден.")
        with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            template = json.load(f)
        base_data = template['data'][0]['Data']
        logging.info(f"Шаблон транзакции загружен из {TEMPLATE_FILE}")
        return base_data
    except FileNotFoundError as e:
        logging.error(f"Ошибка при загрузке шаблона: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка декодирования JSON шаблона: {str(e)}")
        raise

def generate_anomaly_times(num_transactions: int) -> tuple:
    """Генерация временных меток транзакций с аномалиями."""
    TOTAL_HOURS = 24
    A = num_transactions
    mu_main = 12.0
    sigma_main = 4.0
    
    hours = np.linspace(0, 24, num_transactions)
    
    base_traffic = (A / (sigma_main * np.sqrt(2 * np.pi))) * \
                   np.exp(-((hours - mu_main)**2) / (2 * sigma_main**2))
    
    base_traffic += np.random.normal(0, A/1000, size=len(hours))
    base_traffic = np.maximum(base_traffic, 0)  

    anomaly_types = ['normal', 'exponential', 'poisson', 'pareto']
    
    anomaly_params = {
        'normal': {'sigma': 2.0, 'amp': 0.5},
        'exponential': {'sigma': 2.0, 'amp': 0.1, 'lam': 1/10},
        'poisson': {'sigma': 2.0, 'amp': 0.5, 'lam': 1/5},
        'pareto': {'sigma': 1.5, 'amp': 0.2, 'alpha': 1.5, 't_min': 0.1, 't_max': 2.0}
    }

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

    combined_density = base_traffic.copy()
    anomaly_windows = []
    anomaly_types_windows = []  
    
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
        anomaly_types_windows.append(anomaly_type)  # Сохраняем тип аномалии

    cdf = np.cumsum(combined_density)
    cdf = cdf / cdf[-1]
    u = np.random.uniform(0, 1, num_transactions)
    send_hours = np.interp(u, cdf, hours)
    total_sim_seconds = 24 * 60 * 60  # 24 часа в секундах (86400 секунд)
    scale_factor = total_sim_seconds / 24
    send_times = send_hours * scale_factor
    send_times.sort()
    return send_hours, send_times, anomaly_windows, anomaly_types_windows, combined_density, hours

def initialize_reference_tables():
    """Заполнение справочных таблиц."""
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
        return type_id, bank_id, status_id
    except Exception as e:
        logging.error(f"Ошибка при заполнении справочных таблиц: {str(e)}")
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)

def generate_transactions(users: list, num_transactions: int, send_hours: list, anomaly_windows: list, anomaly_types_windows: list) -> tuple:
    """Генерация транзакций и сохранение в файлы/базу."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    base_data = load_template()
    type_id, bank_id, status_id = initialize_reference_tables()
    payloads = []
    transaction_data = []
    bad_transaction_hours = []
    good_transaction_hours = []
    bad_transaction_count = 0
    
    # Счетчики для каждого типа аномалии
    anomaly_counts = {
        'normal': 0,
        'exponential': 0,
        'poisson': 0,
        'pareto': 0
    }

    try:
        conn = get_db_connection()
        for n in range(1, num_transactions + 1):
            trn_id = f"{n:06d}"
            payer = random.choice(users)
            beneficiary = random.choice(users)
            while beneficiary['ClientId'] == payer['ClientId']:
                beneficiary = random.choice(users)
            amount = round(random.uniform(1, 150000), 2)
            narrative = random.choice(['Перевод по СБП', 'Оплата услуг', 'Перевод другу', ''])

            current_hour = send_hours[n-1]
            anomaly_code = GOOD_TRANSACTION_CODE  # По умолчанию хорошая транзакция (0)
            
            # Проверяем, попадает ли транзакция в аномальное окно
            for i, window in enumerate(anomaly_windows):
                if window[0] <= current_hour <= window[1]:
                    # Если попадает в окно и случайное число меньше 0.7, помечаем как аномальную
                    if random.random() < 0.7:
                        anomaly_type = anomaly_types_windows[i]
                        anomaly_code = ANOMALY_CODES[anomaly_type]
                        anomaly_counts[anomaly_type] += 1
                        bad_transaction_count += 1
                        bad_transaction_hours.append(current_hour)
                    break

            if anomaly_code == GOOD_TRANSACTION_CODE:
                good_transaction_hours.append(current_hour)

            beneficiary_data = {
                "PAM": beneficiary["PAM"],
                "FullName": beneficiary["FullName"],
                "BeneficiaryBIC": random.choice(BIC_CODES)
            }

            data_payload = deepcopy(base_data)
            data_payload.update({
                'CurrentTimestamp': datetime.now(timezone.utc).isoformat() + 'Z',
                'TrnId': trn_id,
                'TrnType': 'C2C',
                'PayerData': payer,
                'BeneficiaryData': beneficiary_data,
                'Amount': str(amount),
                'Currency': 'RUB',
                'Narrative': narrative,
                'IsBad': anomaly_code,  # Только числовой код без текстового описания
                'EpochNumber': 1
            })

            file_payload = {
                "data": [{"Data": data_payload}],
                "format": "json"
            }
            payloads.append(file_payload)

            file_path = os.path.join(OUTPUT_DIR, f'txn_{trn_id}.json')
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(file_payload, f, ensure_ascii=False, indent=2)

            # Добавляем данные транзакции с client_id вместо src_id
            transaction_data.append((
                payer['db_id'], beneficiary['db_id'], type_id, bank_id, bank_id, status_id,
                amount, datetime.now(timezone.utc), narrative, anomaly_code, 1
            ))

            if n % 1000 == 0:
                logging.info(f"Создано {n} транзакций")
                print(f"Создано {n} транзакций...")

        with conn.cursor() as cur:
            # Проверяем, что поле is_bad в таблице transactions имеет тип integer
            cur.execute("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'transactions' AND column_name = 'is_bad'
            """)
            is_bad_type = cur.fetchone()
            
            # Если тип не integer, изменяем его
            if is_bad_type and is_bad_type[0] != 'integer':
                cur.execute("ALTER TABLE transactions ALTER COLUMN is_bad TYPE integer USING CASE WHEN is_bad THEN 1 ELSE 0 END")
                conn.commit()
                logging.info("Тип поля is_bad изменен на integer")
            
            # Проверяем наличие колонки client_id и src_id
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'transactions' AND column_name IN ('client_id', 'src_id')
            """)
            columns = [row[0] for row in cur.fetchall()]
            
            # Вставляем данные транзакций с учетом имени колонки (client_id или src_id)
            if 'client_id' in columns:
                execute_values(
                    cur,
                    "INSERT INTO transactions (client_id, dst_id, type_id, bnk_src_id, bnk_dst_id, status_id, value, timestamp, comment, is_bad, epoch_number) VALUES %s",
                    transaction_data,
                    page_size=1000
                )
                logging.info("Транзакции созданы с использованием поля client_id")
            elif 'src_id' in columns:
                execute_values(
                    cur,
                    "INSERT INTO transactions (src_id, dst_id, type_id, bnk_src_id, bnk_dst_id, status_id, value, timestamp, comment, is_bad, epoch_number) VALUES %s",
                    transaction_data,
                    page_size=1000
                )
                logging.info("Транзакции созданы с использованием поля src_id (будет переименовано в client_id)")
            else:
                logging.error("Не найдены колонки client_id или src_id в таблице transactions")
                raise ValueError("Не найдены колонки client_id или src_id в таблице transactions")
                
        conn.commit()
        logging.info("Создание транзакций завершено")
        print(f"Всего транзакций: {num_transactions}")
        print(f"Плохих транзакций: {bad_transaction_count} ({bad_transaction_count / num_transactions * 100:.2f}%)")
        
        # Выводим статистику по типам аномалий
        for anomaly_type, count in anomaly_counts.items():
            print(f"Аномалии типа '{anomaly_type}' (код {ANOMALY_CODES[anomaly_type]}): {count} транзакций")
            
        return payloads, bad_transaction_hours, good_transaction_hours, bad_transaction_count, anomaly_counts
    except Exception as e:
        logging.error(f"Ошибка при генерации транзакций: {str(e)}")
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)
