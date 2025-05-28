import time
import os
import json
import numpy as np
from .db_config import initialize_db, close_db_pool
from .user_generator import generate_users
from .transaction_generator import generate_transactions, generate_anomaly_times, ANOMALY_CODES, GOOD_TRANSACTION_CODE
from .transaction_sender import send_transactions_parallel, send_transactions_with_timing
from .visualization import plot_expected_load, plot_actual_load
import logging

# Логи
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

NUM_USERS = 100
NUM_TRANSACTIONS = 30000

def main():
    """Основной скрипт для генерации и отправки транзакций."""
    try:
        initialize_db()

        users = generate_users(NUM_USERS)
        send_hours, send_times, anomaly_windows, anomaly_types_windows, combined_density, hours = generate_anomaly_times(NUM_TRANSACTIONS)
        payloads, bad_transaction_hours, good_transaction_hours, bad_transaction_count, anomaly_counts = generate_transactions(
            users, NUM_TRANSACTIONS, send_hours, anomaly_windows, anomaly_types_windows
        )

        print("\nКоды аномалий:")
        print(f"Хорошие транзакции: {GOOD_TRANSACTION_CODE}")
        for anomaly_type, code in ANOMALY_CODES.items():
            print(f"Аномалия типа '{anomaly_type}': {code}")


        plot_expected_load(hours, combined_density, anomaly_windows)
        print("Начало отправки транзакций с учетом временных меток...")
        logging.info("Начало отправки транзакций с учетом временных меток")
        start_time = time.time()
        
        #коэффициент ускорения для симуляции
        #1440 = 24 часа за 1 минуту (60 секунд)
        speed_factor = 1440
        print(f"Установлен коэффициент ускорения: {speed_factor}x")
        logging.info(f"Установлен коэффициент ускорения: {speed_factor}x")
        successful, failed = send_transactions_with_timing(payloads, send_times, speed_factor)
        
        end_time = time.time()
        total_simulation_time = send_times[-1]
        logging.info(f"Отправка завершена. Время выполнения: {end_time - start_time:.2f} секунд")
        print(f"Отправка завершена. Время выполнения: {end_time - start_time:.2f} секунд")
        logging.info(f"Общее время симуляции: {total_simulation_time:.2f} секунд")
        print(f"Общее время симуляции: {total_simulation_time:.2f} секунд")
        plot_actual_load(send_times, total_simulation_time, bad_transaction_hours, good_transaction_hours, combined_density, hours, anomaly_windows)
        print("\nПроверка первых 5 JSON-файлов:")
        for n in range(1, min(6, NUM_TRANSACTIONS + 1)):
            file_path = os.path.join('generated_transactions', f'txn_{n:06d}.json')
            with open(file_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
                is_bad = payload['data'][0]['Data']['IsBad']
                anomaly_type = payload['data'][0]['Data'].get('AnomalyType', 'none')
                epoch_number = payload['data'][0]['Data']['EpochNumber']
                print(f"Транзакция {n:06d}: IsBad = {is_bad}, AnomalyType = {anomaly_type}, EpochNumber = {epoch_number}")

    except Exception as e:
        logging.error(f"Ошибка в главном скрипте: {str(e)}")
        print(f"Ошибка в главном скрипте: {e}")
    finally:
        close_db_pool()

if __name__ == "__main__":
    main()
    logging.info("Скрипт завершил работу")
    print("Скрипт завершил работу.")
