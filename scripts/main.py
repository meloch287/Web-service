import time
import os
import json
import numpy as np
from .db_config import initialize_db, close_db_pool
from .user_generator import generate_users
from .transaction_generator import generate_transactions, generate_anomaly_times
from .transaction_sender import send_transactions_parallel, send_transactions_with_timing
from .visualization import plot_expected_load, plot_actual_load
import logging

# Настройка логирования
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Параметры
NUM_USERS = 100
NUM_TRANSACTIONS = 1000

def main():
    """Основной скрипт для генерации и отправки транзакций."""
    try:

        initialize_db()

        users = generate_users(NUM_USERS)

        send_hours, send_times, anomaly_windows, combined_density, hours = generate_anomaly_times(NUM_TRANSACTIONS)

        payloads, bad_transaction_hours, good_transaction_hours, bad_transaction_count = generate_transactions(users, NUM_TRANSACTIONS, send_hours, anomaly_windows)


        plot_expected_load(hours, combined_density, anomaly_windows)

        print("Начало отправки транзакций с учетом временных меток...")
        logging.info("Начало отправки транзакций с учетом временных меток")
        start_time = time.time()
        
        # Используем новую функцию отправки с учетом временных меток вместо параллельной отправки
        successful, failed = send_transactions_with_timing(payloads, send_times)
        
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
                epoch_number = payload['data'][0]['Data']['EpochNumber']
                print(f"Транзакция {n:06d}: IsBad = {is_bad}, EpochNumber = {epoch_number}")

    except Exception as e:
        logging.error(f"Ошибка в главном скрипте: {str(e)}")
        print(f"Ошибка в главном скрипте: {e}")
    finally:
        close_db_pool()

if __name__ == "__main__":
    main()
    logging.info("Скрипт завершил работу")
    print("Скрипт завершил работу.")
