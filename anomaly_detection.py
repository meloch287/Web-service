"""
Модуль для обнаружения аномалий в транзакциях.

Этот модуль содержит функции для выявления различных типов аномалий в транзакциях,
включая подозрительную частоту транзакций, взвешенную вероятность аномалий
и анализ истории транзакций пользователя.
"""

import logging
import psycopg2
from datetime import datetime, timedelta
import json
from typing import Dict, List, Tuple, Any, Optional, Union

# Настройка логирования
logging.basicConfig(
    filename="anomaly_detection.log", 
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Константы для настройки параметров обнаружения аномалий
# Эти значения могут быть изменены в конфигурационном файле
FREQUENCY_TIME_WINDOW = 5  # минут
FREQUENCY_THRESHOLD = 10   # транзакций
AMOUNT_THRESHOLD = 100000  # RUB
STANDARD_DEVIATION_THRESHOLD = 2.0  # стандартных отклонений

# Весовые коэффициенты для разных типов аномалий
ANOMALY_WEIGHTS = {
    "normal": 0.5,        # Нормальная аномалия
    "exponential": 0.7,   # Экспоненциальная аномалия
    "poisson": 0.6,       # Пуассоновская аномалия
    "pareto": 0.8,        # Парето аномалия
    "high_amount": 0.9,   # Высокая сумма
    "suspicious_client": 0.7,  # Подозрительный клиент
    "unusual_direction": 0.6,  # Необычное направление
}

# Порог для определения аномальности транзакции
ANOMALY_SCORE_THRESHOLD = 1.5

# Данные для подключения к PostgreSQL
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

def get_db_connection():
    """
    Создает и возвращает соединение с базой данных.
    
    Returns:
        psycopg2.connection: Соединение с базой данных
    """
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        return conn
    except Exception as e:
        logging.error(f"Ошибка при подключении к базе данных: {str(e)}")
        raise

def check_transaction_frequency(src_id: int, time_window: int = FREQUENCY_TIME_WINDOW, 
                               threshold: int = FREQUENCY_THRESHOLD) -> Tuple[bool, int]:
    """
    Проверяет, превышает ли частота транзакций от одного клиента заданный порог
    за указанный временной интервал.
    
    Args:
        src_id: ID клиента-отправителя
        time_window: Временное окно в минутах (по умолчанию 5 минут)
        threshold: Пороговое количество транзакций (по умолчанию 10)
        
    Returns:
        Tuple[bool, int]: (Превышен ли порог, Количество транзакций в окне)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем количество транзакций от данного клиента за последние time_window минут
        time_limit = datetime.utcnow() - timedelta(minutes=time_window)
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM transactions 
            WHERE src_id = %s AND timestamp > %s
        """, (src_id, time_limit))
        
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Проверяем, превышен ли порог
        is_suspicious = count >= threshold
        
        if is_suspicious:
            logging.info(f"Обнаружена подозрительная частота транзакций для клиента {src_id}: {count} за {time_window} минут")
        
        return is_suspicious, count
        
    except Exception as e:
        logging.error(f"Ошибка при проверке частоты транзакций: {str(e)}")
        return False, 0

def calculate_anomaly_score(transaction_data: Dict[str, Any]) -> float:
    """
    Рассчитывает "скор аномальности" транзакции на основе различных факторов.
    
    Args:
        transaction_data: Словарь с данными транзакции
        
    Returns:
        float: Скор аномальности (чем выше, тем более подозрительна транзакция)
    """
    score = 0.0
    
    try:
        # Извлекаем данные из структуры сообщения
        data = transaction_data.get('Data', {})
        if not data:
            return score
        
        # Проверяем тип аномалии
        anomaly_type = data.get('AnomalyType', 'normal').lower()
        if anomaly_type in ANOMALY_WEIGHTS:
            score += ANOMALY_WEIGHTS[anomaly_type]
        
        # Проверяем сумму транзакции
        amount = data.get('Amount')
        if amount and isinstance(amount, str):
            try:
                amount = float(amount)
                if amount > AMOUNT_THRESHOLD:
                    score += ANOMALY_WEIGHTS["high_amount"]
            except ValueError:
                pass
        
        # Проверяем интенсивность аномалии (если указана)
        intensity = data.get('AnomalyIntensity', 0.0)
        if isinstance(intensity, (int, float)) and intensity > 0:
            # Нормализуем интенсивность к диапазону [0, 1]
            normalized_intensity = min(1.0, intensity / 10.0)
            # Добавляем к скору с учетом интенсивности
            score += normalized_intensity * 0.5
        
        return score
        
    except Exception as e:
        logging.error(f"Ошибка при расчете скора аномальности: {str(e)}")
        return 0.0

def check_unusual_amount(src_id: int, amount: float) -> Tuple[bool, float, float]:
    """
    Проверяет, отличается ли сумма транзакции от исторического среднего
    для данного клиента более чем на заданное количество стандартных отклонений.
    
    Args:
        src_id: ID клиента-отправителя
        amount: Сумма текущей транзакции
        
    Returns:
        Tuple[bool, float, float]: (Является ли сумма необычной, Среднее значение, Стандартное отклонение)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем статистику по суммам транзакций клиента
        cursor.execute("""
            SELECT AVG(value), STDDEV(value)
            FROM transactions
            WHERE src_id = %s
        """, (src_id,))
        
        result = cursor.fetchone()
        avg_amount, stddev_amount = result
        
        # Если нет данных или стандартное отклонение равно 0, считаем сумму обычной
        if avg_amount is None or stddev_amount is None or stddev_amount == 0:
            cursor.close()
            conn.close()
            return False, 0, 0
        
        # Проверяем, отклоняется ли сумма от среднего более чем на STANDARD_DEVIATION_THRESHOLD стандартных отклонений
        deviation = abs(amount - avg_amount) / stddev_amount
        is_unusual = deviation > STANDARD_DEVIATION_THRESHOLD
        
        cursor.close()
        conn.close()
        
        if is_unusual:
            logging.info(f"Обнаружена необычная сумма транзакции для клиента {src_id}: {amount} (отклонение: {deviation:.2f}σ)")
        
        return is_unusual, avg_amount, stddev_amount
        
    except Exception as e:
        logging.error(f"Ошибка при проверке необычной суммы: {str(e)}")
        return False, 0, 0

def check_unusual_direction(src_id: int, dst_id: int) -> bool:
    """
    Проверяет, является ли направление транзакции (пара отправитель-получатель)
    необычным для данного клиента.
    
    Args:
        src_id: ID клиента-отправителя
        dst_id: ID клиента-получателя
        
    Returns:
        bool: True, если направление необычное, иначе False
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем, были ли ранее транзакции между этими клиентами
        cursor.execute("""
            SELECT COUNT(*)
            FROM transactions
            WHERE src_id = %s AND dst_id = %s
        """, (src_id, dst_id))
        
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        # Если это первая транзакция между клиентами, считаем направление необычным
        is_unusual = count == 0
        
        if is_unusual:
            logging.info(f"Обнаружено необычное направление транзакции: от клиента {src_id} к клиенту {dst_id}")
        
        return is_unusual
        
    except Exception as e:
        logging.error(f"Ошибка при проверке необычного направления: {str(e)}")
        return False

def check_client_history(client_id: int) -> float:
    """
    Проверяет историю клиента и возвращает коэффициент подозрительности
    на основе доли плохих транзакций в истории.
    
    Args:
        client_id: ID клиента
        
    Returns:
        float: Коэффициент подозрительности (0.0 - 1.0)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем общее количество транзакций клиента и количество плохих транзакций
        cursor.execute("""
            SELECT COUNT(*), SUM(CASE WHEN is_bad THEN 1 ELSE 0 END)
            FROM transactions
            WHERE src_id = %s
        """, (client_id,))
        
        result = cursor.fetchone()
        total_count, bad_count = result
        
        cursor.close()
        conn.close()
        
        # Если нет данных, возвращаем 0
        if total_count is None or total_count == 0 or bad_count is None:
            return 0.0
        
        # Рассчитываем долю плохих транзакций
        bad_ratio = bad_count / total_count
        
        return bad_ratio
        
    except Exception as e:
        logging.error(f"Ошибка при проверке истории клиента: {str(e)}")
        return 0.0

def analyze_transaction(transaction_data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    """
    Анализирует транзакцию на наличие различных аномалий и возвращает
    результат анализа и детали обнаруженных аномалий.
    
    Args:
        transaction_data: Словарь с данными транзакции
        
    Returns:
        Tuple[bool, Dict[str, Any]]: (Является ли транзакция подозрительной, Детали анализа)
    """
    analysis_details = {
        "anomaly_score": 0.0,
        "frequency_check": {"is_suspicious": False, "count": 0},
        "amount_check": {"is_unusual": False, "avg_amount": 0, "stddev_amount": 0},
        "direction_check": {"is_unusual": False},
        "client_history": {"suspicion_ratio": 0.0}
    }
    
    try:
        # Извлекаем данные из структуры сообщения
        data = transaction_data.get('Data', {})
        if not data:
            return False, analysis_details
        
        # Получаем ID клиентов
        payer_data = data.get('PayerData', {})
        beneficiary_data = data.get('BeneficiaryData', {})
        
        # Подключаемся к БД для получения ID клиентов
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем ID отправителя
        payer_client_id = payer_data.get('ClientId')
        if payer_client_id:
            cursor.execute(
                "SELECT id FROM clients WHERE comment LIKE %s LIMIT 1",
                (f'%{payer_client_id}%',)
            )
            result = cursor.fetchone()
            src_id = result[0] if result else None
        else:
            src_id = None
        
        # Получаем ID получателя
        beneficiary_client_id = beneficiary_data.get('ClientId')
        if beneficiary_client_id:
            cursor.execute(
                "SELECT id FROM clients WHERE comment LIKE %s LIMIT 1",
                (f'%{beneficiary_client_id}%',)
            )
            result = cursor.fetchone()
            dst_id = result[0] if result else None
        else:
            dst_id = None
        
        cursor.close()
        conn.close()
        
        # Если не удалось определить ID клиентов, прекращаем анализ
        if src_id is None or dst_id is None:
            return False, analysis_details
        
        # Получаем сумму транзакции
        amount = data.get('Amount')
        if amount and isinstance(amount, str):
            try:
                amount = float(amount)
            except ValueError:
                amount = 0
        else:
            amount = 0
        
        # Проверяем частоту транзакций
        is_frequency_suspicious, frequency_count = check_transaction_frequency(src_id)
        analysis_details["frequency_check"]["is_suspicious"] = is_frequency_suspicious
        analysis_details["frequency_check"]["count"] = frequency_count
        
        # Проверяем необычную сумму
        is_amount_unusual, avg_amount, stddev_amount = check_unusual_amount(src_id, amount)
        analysis_details["amount_check"]["is_unusual"] = is_amount_unusual
        analysis_details["amount_check"]["avg_amount"] = avg_amount
        analysis_details["amount_check"]["stddev_amount"] = stddev_amount
        
        # Проверяем необычное направление
        is_direction_unusual = check_unusual_direction(src_id, dst_id)
        analysis_details["direction_check"]["is_unusual"] = is_direction_unusual
        
        # Проверяем историю клиента
        client_suspicion_ratio = check_client_history(src_id)
        analysis_details["client_history"]["suspicion_ratio"] = client_suspicion_ratio
        
        # Рассчитываем скор аномальности
        base_score = calculate_anomaly_score(transaction_data)
        
        # Добавляем к скору результаты дополнительных проверок
        if is_frequency_suspicious:
            base_score += ANOMALY_WEIGHTS["suspicious_client"]
        
        if is_amount_unusual:
            base_score += ANOMALY_WEIGHTS["high_amount"]
        
        if is_direction_unusual:
            base_score += ANOMALY_WEIGHTS["unusual_direction"]
        
        # Учитываем историю клиента
        base_score += client_suspicion_ratio * ANOMALY_WEIGHTS["suspicious_client"]
        
        analysis_details["anomaly_score"] = base_score
        
        # Определяем, является ли транзакция подозрительной
        is_suspicious = base_score >= ANOMALY_SCORE_THRESHOLD
        
        if is_suspicious:
            logging.info(f"Транзакция определена как подозрительная. Скор аномальности: {base_score:.2f}")
        
        return is_suspicious, analysis_details
        
    except Exception as e:
        logging.error(f"Ошибка при анализе транзакции: {str(e)}")
        return False, analysis_details

def update_transaction_status(transaction_id: str, is_bad: bool, analysis_details: Dict[str, Any]) -> bool:
    """
    Обновляет статус транзакции в базе данных на основе результатов анализа.
    
    Args:
        transaction_id: ID транзакции (TrnId)
        is_bad: Флаг, указывающий, является ли транзакция плохой
        analysis_details: Детали анализа транзакции
        
    Returns:
        bool: True, если обновление прошло успешно, иначе False
    """
    try:
        conn = get_db_connection()
        conn.autocommit = False
        cursor = conn.cursor()
        
        # Преобразуем детали анализа в JSON
        analysis_json = json.dumps(analysis_details, ensure_ascii=False)
        
        # Обновляем статус транзакции
        cursor.execute("""
            UPDATE transactions
            SET is_bad = %s, comment = comment || ' | Analysis: ' || %s
            WHERE comment LIKE %s
            RETURNING id
        """, (is_bad, analysis_json, f'%{transaction_id}%'))
        
        result = cursor.fetchone()
        
        if result:
            conn.commit()
            cursor.close()
            conn.close()
            logging.info(f"Статус транзакции {transaction_id} успешно обновлен: is_bad={is_bad}")
            return True
        else:
            conn.rollback()
            cursor.close()
            conn.close()
            logging.warning(f"Транзакция с ID {transaction_id} не найдена")
            return False
        
    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        logging.error(f"Ошибка при обновлении статуса транзакции: {str(e)}")
        return False
