import requests
import logging
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from .validation import validate_transaction

logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

SENDER_URL = "http://localhost:5000/send"
MAX_RETRIES = 3
RETRY_DELAY = 2

def send_transaction(payload: dict, max_retries: int = MAX_RETRIES, retry_delay: float = RETRY_DELAY) -> bool:
    """Отправка одной транзакции."""
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
                    time_module.sleep(retry_delay)
                else:
                    logging.error(f"[{trn_id}] Все попытки отправки исчерпаны")
                    return False
    except Exception as e:
        logging.error(f"Общая ошибка при отправке транзакции: {str(e)}")
        print(f"Ошибка отправки: {e}")
        return False

def send_transactions_parallel(payloads: list, max_workers: int = 10) -> tuple:
    """Параллельная отправка транзакций."""
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

def send_transactions_with_timing(payloads: list, send_times: list) -> tuple:
    """Отправка транзакций с учетом временных меток.
    
    Args:
        payloads: Список транзакций для отправки
        send_times: Список временных меток (в секундах) для каждой транзакции
        
    Returns:
        tuple: (успешно отправлено, не удалось отправить)
    """
    if len(payloads) != len(send_times):
        logging.error(f"Количество транзакций ({len(payloads)}) не соответствует количеству временных меток ({len(send_times)})")
        return 0, 0
    
    # Сортируем транзакции по времени отправки
    sorted_data = sorted(zip(payloads, send_times), key=lambda x: x[1])
    
    successful = 0
    failed = 0
    start_time = time_module.time()
    
    print(f"Начало отправки транзакций с учетом временных меток. Общее время симуляции: {send_times[-1]:.2f} секунд")
    logging.info(f"Начало отправки транзакций с учетом временных меток. Общее время симуляции: {send_times[-1]:.2f} секунд")
    
    # Коэффициент ускорения для тестирования (можно настроить)
    # Например, speed_factor = 60 означает, что 1 час будет симулироваться за 1 минуту
    # Для полной 24-часовой симуляции установите speed_factor = 1
    speed_factor = 1
    
    for i, (payload, send_time) in enumerate(sorted_data):
        # Вычисляем, сколько времени должно пройти с начала симуляции до отправки текущей транзакции
        elapsed_target = send_time / speed_factor
        
        # Вычисляем, сколько времени фактически прошло
        elapsed_actual = time_module.time() - start_time
        
        # Если нужно - ждем до нужного момента времени
        if elapsed_actual < elapsed_target:
            wait_time = elapsed_target - elapsed_actual
            logging.info(f"Ожидание {wait_time:.2f} секунд перед отправкой транзакции {i+1}/{len(payloads)}")
            time_module.sleep(wait_time)
        
        # Отправляем транзакцию
        trn_id = payload['data'][0]['Data']['TrnId']
        current_time = time_module.time() - start_time
        logging.info(f"[{trn_id}] Отправка транзакции {i+1}/{len(payloads)} в момент времени {current_time:.2f} с (плановое время: {elapsed_target:.2f} с)")
        
        if send_transaction(payload):
            successful += 1
        else:
            failed += 1
            
        # Выводим прогресс каждые 10% транзакций
        if (i+1) % max(1, len(payloads)//10) == 0:
            progress = (i+1) / len(payloads) * 100
            elapsed = time_module.time() - start_time
            estimated_total = elapsed / progress * 100
            remaining = estimated_total - elapsed
            
            print(f"Прогресс: {progress:.1f}% ({i+1}/{len(payloads)}). Прошло: {elapsed:.2f} с. Осталось примерно: {remaining:.2f} с.")
            logging.info(f"Прогресс: {progress:.1f}% ({i+1}/{len(payloads)}). Прошло: {elapsed:.2f} с. Осталось примерно: {remaining:.2f} с.")
    
    total_time = time_module.time() - start_time
    logging.info(f"Отправка с учетом временных меток завершена. Успешно: {successful}, Не удалось: {failed}. Общее время: {total_time:.2f} с")
    print(f"Отправка с учетом временных меток завершена. Успешно: {successful}, Не удалось: {failed}. Общее время: {total_time:.2f} с")
    
    return successful, failed
