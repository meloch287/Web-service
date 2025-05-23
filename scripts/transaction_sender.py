import requests
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from .validation import validate_transaction

# Настройка логирования
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Параметры отправки
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
                    time.sleep(retry_delay)
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