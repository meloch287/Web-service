import psycopg2
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from anomaly_detection import analyze_transaction
import xmltodict
import json
import logging
from datetime import datetime,timezone
import traceback
import sys

logging.basicConfig(
    filename="receiver.log", 
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s"
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(message)s")
console_handler.setFormatter(console_formatter)
logging.getLogger().addHandler(console_handler)

DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"


def create_database():
    """
    Создает базу данных PostgreSQL, если она ещё не существует.
    Использует соединение к системной базе postgres.
    """
    try:
        conn = psycopg2.connect(dbname="vtsk_db", user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {DB_NAME}")
        cursor.close()
        conn.close()
        logging.info(f"База данных {DB_NAME} проверена/создана успешно")
    except Exception as e:
        logging.error(f"Ошибка при создании/проверке базы данных: {str(e)}")
        raise
    
create_database()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class ReceivedMessage(db.Model):
    """
    SQLAlchemy модель для хранения входящих сообщений.
    """
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    trn_id = db.Column(db.String(50), index=True) 
    received_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    processed = db.Column(db.Boolean, default=False) 

with app.app_context():
    db.create_all()
    conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
    conn.autocommit = True
    cur = conn.cursor()
    
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'transactions')")
    if not cur.fetchone()[0]:
        logging.warning("Таблица transactions не найдена. Создаем...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS "transactions" (
            "id" BIGSERIAL NOT NULL UNIQUE,
            "client_id" BIGINT,
            "dst_id" BIGINT,
            "value" NUMERIC,
            "type_id" BIGINT,
            "bnk_src_id" BIGINT,
            "bnk_dst_id" BIGINT,
            "timestamp" TIMESTAMP,
            "comment" TEXT,
            "status_id" BIGINT,
            "is_bad" INTEGER DEFAULT 0,
            "epoch_number" BIGINT DEFAULT 1,
            PRIMARY KEY("id")
        )
        """)
    else:
        #проверка, что поле is_bad имеет тип INTEGER
        cur.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'transactions' AND column_name = 'is_bad'
        """)
        is_bad_type = cur.fetchone()
        
        #если тип не integer, изменяем его
        if is_bad_type and is_bad_type[0] != 'integer':
            try:
                # Сначала удаляем значение по умолчанию
                cur.execute("ALTER TABLE transactions ALTER COLUMN is_bad DROP DEFAULT")
                logging.info("Значение по умолчанию для поля is_bad удалено")
                
                # Затем изменяем тип
                cur.execute("ALTER TABLE transactions ALTER COLUMN is_bad TYPE integer USING CASE WHEN is_bad THEN 1 ELSE 0 END")
                logging.info("Тип поля is_bad изменен на integer")
                
                # Устанавливаем новое значение по умолчанию
                cur.execute("ALTER TABLE transactions ALTER COLUMN is_bad SET DEFAULT 0")
                logging.info("Установлено новое значение по умолчанию для поля is_bad: 0")
            except Exception as e:
                logging.error(f"Ошибка при изменении типа поля is_bad: {str(e)}")
                logging.error(traceback.format_exc())
        
        #проверяем наличие колонки client_id и src_id
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'transactions' AND column_name IN ('client_id', 'src_id')
        """)
        columns = [row[0] for row in cur.fetchall()]
        
        # если есть src_id, но нет client_id, переименовываем колонку
        if 'src_id' in columns and 'client_id' not in columns:
            cur.execute("ALTER TABLE transactions RENAME COLUMN src_id TO client_id")
            logging.info("Колонка src_id переименована в client_id")
    
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'clients')")
    if not cur.fetchone()[0]:
        logging.warning("Таблица clients не найдена. Создаем...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS "clients" (
            "id" BIGSERIAL NOT NULL UNIQUE,
            "name" TEXT,
            "comment" TEXT,
            PRIMARY KEY("id")
        )
        """)

    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'transaction_types')")
    if not cur.fetchone()[0]:
        logging.warning("Таблица transaction_types не найдена. Создаем...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS "transaction_types" (
            "id" BIGSERIAL NOT NULL UNIQUE,
            "type" TEXT,
            PRIMARY KEY("id")
        )
        """)
        cur.execute("INSERT INTO transaction_types (type) VALUES ('C2C') ON CONFLICT DO NOTHING")
    
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'banks')")
    if not cur.fetchone()[0]:
        logging.warning("Таблица banks не найдена. Создаем...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS "banks" (
            "id" BIGSERIAL NOT NULL UNIQUE,
            "bank_name" TEXT,
            PRIMARY KEY("id")
        )
        """)
        cur.execute("INSERT INTO banks (bank_name) VALUES ('Default Bank') ON CONFLICT DO NOTHING")
    
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'transaction_status')")
    if not cur.fetchone()[0]:
        logging.warning("Таблица transaction_status не найдена. Создаем...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS "transaction_status" (
            "id" BIGSERIAL NOT NULL UNIQUE,
            "status" TEXT,
            PRIMARY KEY("id")
        )
        """)
        cur.execute("INSERT INTO transaction_status (status) VALUES ('Pending') ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO transaction_status (status) VALUES ('Completed') ON CONFLICT DO NOTHING")
    
    cur.close()
    conn.close()
    logging.info("Проверка и создание необходимых таблиц завершены")

def get_or_create_client(conn, client_data):
    """
    Получает или создает запись клиента в таблице clients.
    
    Args:
        conn: Соединение с базой данных
        client_data: Словарь с данными клиента
    
    Returns:
        int: ID клиента в таблице clients
    """
    cursor = conn.cursor()
    
    client_id = client_data.get('ClientId')
    if not client_id:
        full_name = client_data.get('FullName', 'Unknown')
        cursor.execute(
            "SELECT id FROM clients WHERE name = %s LIMIT 1",
            (full_name,)
        )
    else:
        cursor.execute(
            "SELECT id FROM clients WHERE comment LIKE %s LIMIT 1",
            (f'%{client_id}%',)
        )
    
    result = cursor.fetchone()
    
    if result:
        client_db_id = result[0]
    else:
        full_name = client_data.get('FullName', 'Unknown')
        comment = f"Клиент {client_id}" if client_id else "Автоматически созданный клиент"
        
        cursor.execute(
            "INSERT INTO clients (name, comment) VALUES (%s, %s) RETURNING id",
            (full_name, comment)
        )
        client_db_id = cursor.fetchone()[0]
    
    cursor.close()
    return client_db_id

def get_type_id(conn, trn_type='C2C'):
    """Получает ID типа транзакции, создает если не существует"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM transaction_types WHERE type = %s",
        (trn_type,)
    )
    result = cursor.fetchone()
    
    if result:
        type_id = result[0]
    else:
        cursor.execute(
            "INSERT INTO transaction_types (type) VALUES (%s) RETURNING id",
            (trn_type,)
        )
        type_id = cursor.fetchone()[0]
    
    cursor.close()
    return type_id

def get_bank_id(conn, bank_name='Default Bank'):
    """Получает ID банка, создает если не существует"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM banks WHERE bank_name = %s",
        (bank_name,)
    )
    result = cursor.fetchone()
    
    if result:
        bank_id = result[0]
    else:
        cursor.execute(
            "INSERT INTO banks (bank_name) VALUES (%s) RETURNING id",
            (bank_name,)
        )
        bank_id = cursor.fetchone()[0]
    
    cursor.close()
    return bank_id

def get_status_id(conn, status='Completed'):
    """Получает ID статуса транзакции, создает если не существует"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM transaction_status WHERE status = %s",
        (status,)
    )
    result = cursor.fetchone()
    
    if result:
        status_id = result[0]
    else:
        cursor.execute(
            "INSERT INTO transaction_status (status) VALUES (%s) RETURNING id",
            (status,)
        )
        status_id = cursor.fetchone()[0]
    
    cursor.close()
    return status_id

def save_transaction_to_db(transaction_data):
    """
    Сохраняет данные транзакции в таблицу transactions.
    
    Args:
        transaction_data: Словарь с данными транзакции
    
    Returns:
        bool: True если успешно, False в случае ошибки
    """
    try:
        data = transaction_data.get('Data', {})
        if not data:
            logging.error("Отсутствует поле Data в сообщении")
            return True  
        
        trn_id = data.get('TrnId')
        if not trn_id:
            logging.error("Отсутствует TrnId в сообщении")
            return True 
        
        payer_data = data.get('PayerData', {})
        beneficiary_data = data.get('BeneficiaryData', {})
        amount = data.get('Amount')
        if amount and isinstance(amount, str):
            try:
                amount = float(amount)
            except ValueError:
                logging.warning(f"Не удалось преобразовать Amount '{amount}' в число, используем 0")
                amount = 0
        
        narrative = data.get('Narrative', '')
        epoch_number = data.get('EpochNumber', 1)
        
        #получаем значение is_bad как целое число
        is_bad = data.get('IsBad', 0)
        if isinstance(is_bad, bool):
            is_bad = 1 if is_bad else 0

        conn = psycopg2.connect(dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
        conn.autocommit = False  
        
        try:
            client_id = get_or_create_client(conn, payer_data)
            dst_id = get_or_create_client(conn, beneficiary_data)
            type_id = get_type_id(conn, data.get('TrnType', 'C2C'))
            bank_id = get_bank_id(conn)
            status_id = get_status_id(conn, 'Completed')
            
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM transactions WHERE comment LIKE %s LIMIT 1",
                (f'%{trn_id}%',)
            )
            existing = cursor.fetchone()
            
            if existing:
                logging.info(f"Транзакция с TrnId={trn_id} уже существует, пропускаем")
                conn.commit()
                return True  
            
            cursor.execute("""
                INSERT INTO transactions 
                (client_id, dst_id, type_id, bnk_src_id, bnk_dst_id, status_id, value, timestamp, comment, is_bad, epoch_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                client_id, dst_id, type_id, bank_id, bank_id, status_id, 
                amount, datetime.utcnow(), f"{narrative} (TrnId: {trn_id})", 
                is_bad, epoch_number
            ))
            
            transaction_db_id = cursor.fetchone()[0]
            
            conn.commit()
            logging.info(f"Транзакция с TrnId={trn_id} успешно сохранена в БД с id={transaction_db_id}")
            return True
            
        except Exception as e:
            conn.rollback()
            logging.error(f"Ошибка при сохранении транзакции с TrnId={trn_id}: {str(e)}")
            logging.error(traceback.format_exc())
            return True  
        finally:
            conn.close()
            
    except Exception as e:
        logging.error(f"Общая ошибка при обработке транзакции: {str(e)}")
        logging.error(traceback.format_exc())
        return True 

@app.route('/', methods=['GET'])
def home():
    """
    Стартовая страница сервиса. Используется для проверки, работает ли сервер.
    """
    return jsonify({'status': 'Receiver service is running'}), 200

@app.route('/receive', methods=['POST'])
def receive_message():
    """
    Обрабатывает POST-запросы на /receive.
    Принимает JSON или XML, сохраняет каждое сообщение в базу данных,
    и возвращает список ответов с trn_id, timestamp и статусом (Ok/Error).
    """
    responses = []
    try:
        logging.info(f"Получен запрос: Content-Type={request.content_type}, Длина={len(request.data)}")
        
        if request.content_type == 'application/json':
            try:
                payload = request.get_json()
                logging.info(f"Получен JSON: {json.dumps(payload, ensure_ascii=False)[:200]}...")
            except Exception as e:
                logging.error(f"Ошибка при разборе JSON: {str(e)}")
                return jsonify({'error': 'Invalid JSON format'}), 400
        elif request.content_type in ['application/xml', 'text/xml']:
            try:
                payload = xmltodict.parse(request.data)
                logging.info(f"Получен XML, преобразован в: {json.dumps(payload, ensure_ascii=False)[:200]}...")
            except Exception as e:
                logging.error(f"Ошибка при разборе XML: {str(e)}")
                return jsonify({'error': 'Invalid XML format'}), 400
        else:
            logging.error(f"Неподдерживаемый Content-Type: {request.content_type}")
            return jsonify({'error': 'Unsupported Content-Type'}), 400

        data_field = payload.get('data')
        if data_field is None:
            logging.error("Поле 'data' отсутствует в запросе")
            return jsonify({'error': 'Поле "data" отсутствует'}), 400

        messages = data_field if isinstance(data_field, list) else [data_field]
        logging.info(f"Получено {len(messages)} сообщений для обработки")

        for message in messages:
            trn_id = None
            try:
                if isinstance(message, dict) and 'Data' in message:
                    trn_id = message['Data'].get('TrnId')
                else:
                    logging.warning(f"Нестандартная структура сообщения: {json.dumps(message, ensure_ascii=False)[:100]}...")
            except Exception as e:
                logging.error(f"Ошибка при извлечении TrnId: {str(e)}")

            message_json = json.dumps(message, ensure_ascii=False)
            
            try:
                # сохр сообщение в таблицу ReceivedMessage
                msg = ReceivedMessage(content=message_json, trn_id=trn_id)
                db.session.add(msg)
                db.session.commit()
                logging.info(f"Сообщение с trn_id={trn_id} сохранено в таблицу ReceivedMessage")
                
                # сохр транзакцию в таблицу transactions
                transaction_saved = save_transaction_to_db(message)
                
                status = "Ok"
                msg.processed = True
                db.session.commit()
                
                logging.info(f"Обработано сообщение: trn_id={trn_id} | Статус: {status}")
                print(f"Обработано сообщение: trn_id={trn_id} | Статус: {status}")
            except Exception as e:
                status = "Ok"  
                logging.error(f"Ошибка при обработке сообщения с trn_id={trn_id}: {str(e)}")
                logging.error(traceback.format_exc())

            responses.append({
                'timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
                'trn_id': trn_id,
                'trn_status': status
            })

        return jsonify({'responses': responses}), 200
        
    except Exception as e:
        logging.error(f"Общая ошибка при обработке запроса: {str(e)}")
        logging.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Receiver service starting...")
    logging.info("Receiver service starting...")
    app.run(host='0.0.0.0', port=5001, debug=True)
