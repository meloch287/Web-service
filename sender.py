import psycopg2
from flask import Flask, request, jsonify
import requests
import json
import logging
import traceback
from dicttoxml import dicttoxml
import time
import os
from datetime import datetime, timezone

log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "sender.log")

logging.basicConfig(
    filename=log_file, 
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    """
    Стартовая страница сервиса. Используется для проверки, работает ли сервер.
    """
    return jsonify({'status': 'Sender service is running'}), 200

def extract_trn_id(data_field):
    """
    Извлекает TrnId из структуры данных.
    
    Args:
        data_field: Список или словарь с данными
        
    Returns:
        str: TrnId или None, если не найден
    """
    try:
        if isinstance(data_field, list):
            for item in data_field:
                if isinstance(item, dict) and 'Data' in item:
                    return item['Data'].get('TrnId')
        elif isinstance(data_field, dict) and 'Data' in data_field:
            return data_field['Data'].get('TrnId')
    except Exception as e:
        logging.error(f"Ошибка при извлечении TrnId: {str(e)}")
    return None

def send_to_receiver(payload, fmt, max_retries=3, retry_delay=1):
    """
    Отправляет данные на сервер-получатель с поддержкой повторных попыток.
    
    Args:
        payload: Данные для отправки
        fmt: Формат данных ('json' или 'xml')
        max_retries: Максимальное количество попыток
        retry_delay: Задержка между попытками в секундах
        
    Returns:
        tuple: (успех, ответ, код_ответа)
    """
    headers = {}
    data_to_send = None
    
    if fmt == 'json':
        headers['Content-Type'] = 'application/json'
        data_to_send = payload
    elif fmt == 'xml':
        headers['Content-Type'] = 'application/xml'
        data_to_send = dicttoxml(payload, custom_root='root', attr_type=False).decode()
    else:
        logging.error(f"Неподдерживаемый формат: {fmt}")
        return False, {"error": "Unsupported format"}, 400
    
    receiver_url =  'http://192.168.10.2:5001/receive' #'http://localhost:5001/receive'

    data_field = payload.get('data')
    trn_id = extract_trn_id(data_field)
    
    log_msg = f"Отправка данных: TrnId={trn_id}, Format={fmt}"
    logging.info(log_msg)
    print(log_msg)
    
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                receiver_url, 
                data=data_to_send if fmt == 'xml' else json.dumps(data_to_send), 
                headers=headers,
                timeout=15  
            )
            
            if resp.status_code < 400:
                log_msg = f"Успешная отправка (попытка {attempt}): TrnId={trn_id}, Status={resp.status_code}"
                logging.info(log_msg)
                print(log_msg)
                
                try:
                    receiver_response = resp.json()
                except Exception:
                    receiver_response = resp.text
                
                response_log = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trn_id": trn_id,
                    "status_code": resp.status_code,
                    "response": receiver_response,
                    "attempt": attempt
                }
                logging.info(f"Response log: {json.dumps(response_log)}")
                
                return True, receiver_response, resp.status_code
            else:
                log_msg = f"Ошибка отправки (попытка {attempt}): TrnId={trn_id}, Status={resp.status_code}, Response={resp.text}"
                logging.error(log_msg)
                print(log_msg)
                
                if attempt < max_retries:
                    time.sleep(retry_delay)
        except Exception as e:
            log_msg = f"Исключение при отправке (попытка {attempt}): TrnId={trn_id}, Error={str(e)}"
            logging.error(log_msg)
            logging.error(traceback.format_exc())
            print(log_msg)
            
            if attempt < max_retries:
                time.sleep(retry_delay)
    
    return False, {"error": "Failed after max retries"}, 500

@app.route('/send', methods=['POST'])
def send_message():
    """
    Обрабатывает POST-запросы на /send.
    Принимает JSON с полями "data" и "format", преобразует данные в нужный формат
    и отправляет их на внешний URL получателя.
    """
    try:
        content = request.get_json()
        if content is None:
            logging.error("Получен невалидный JSON")
            return jsonify({'error': 'Invalid JSON payload'}), 400

        data_field = content.get('data')
        fmt = content.get('format', 'json').lower()

        if data_field is None:
            logging.error("Поле 'data' не предоставлено")
            return jsonify({'error': 'Поле "data" не предоставлено'}), 400

        trn_id = extract_trn_id(data_field)
        logging.info(f"Получен запрос на отправку: TrnId={trn_id}, Format={fmt}")

        success, receiver_response, status_code = send_to_receiver(content, fmt)

        if success:
            return jsonify({
                'sent': True,
                'receiver_status': status_code,
                'receiver_response': receiver_response
            }), 200
        else:
            return jsonify({
                'sent': False,
                'error': 'Failed to send to receiver',
                'receiver_response': receiver_response
            }), 500

    except Exception as e:
        error_msg = f"Error sending message: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        print(error_msg)
        return jsonify({'error': error_msg}), 400

if __name__ == '__main__':
    print("Sender service starting...")
    logging.info("Sender service starting...")
    app.run(host='0.0.0.0', port=5000, debug=True)
