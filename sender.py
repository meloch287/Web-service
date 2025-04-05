import psycopg2
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests
import json
import logging
from dicttoxml import dicttoxml

# Настройка логирования в файл sender.log
logging.basicConfig(filename="sender.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Данные для подключения к PostgreSQL
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

def create_database():
    """
    Создает базу данных PostgreSQL, если она ещё не существует.
    Используется соединение к системной базе postgres.
    """
    conn = psycopg2.connect(dbname="postgres", user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
    if not cursor.fetchone():
        cursor.execute(f"CREATE DATABASE {DB_NAME}")
    cursor.close()
    conn.close()

# Проверка и создание базы данных при запуске
create_database()

# Настройка Flask-приложения и SQLAlchemy
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class ResponseLog(db.Model):
    """
    SQLAlchemy модель для логирования ответов от сервера-получателя.
    """
    id = db.Column(db.Integer, primary_key=True)
    status_code = db.Column(db.Integer, nullable=False)
    response_body = db.Column(db.Text)

# Создание таблиц в БД, если они ещё не созданы
with app.app_context():
    db.create_all()

@app.route('/', methods=['GET'])
def home():
    """
    Стартовая страница сервиса. Используется для проверки, работает ли сервер.
    """
    return jsonify({'status': 'Sender service is running'}), 200

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
            return jsonify({'error': 'Invalid JSON payload'}), 400

        # Извлекаем данные и формат (json или xml)
        data_field = content.get('data')
        fmt = content.get('format', 'json').lower()

        if data_field is None:
            return jsonify({'error': 'Поле "data" не предоставлено'}), 400

        headers = {}
        payload = None

        # Подготовка тела запроса и заголовков
        if fmt == 'json':
            headers['Content-Type'] = 'application/json'
            payload = json.dumps({"data": data_field})
        elif fmt == 'xml':
            headers['Content-Type'] = 'application/xml'
            payload = dicttoxml({"data": data_field}, custom_root='root', attr_type=False).decode()
        else:
            return jsonify({'error': 'Unsupported format. Choose json or xml'}), 400

        # URL сервиса-получателя (можно изменить при необходимости)
        receiver_url = 'http://192.168.10.2:5001/receive'

        # Отправка данных
        resp = requests.post(receiver_url, data=payload, headers=headers)

        log_msg = f"Sent data: {json.dumps(data_field, ensure_ascii=False)}, Format: {fmt}, Response: {resp.status_code} - {resp.text}"
        logging.info(log_msg)
        print(log_msg)

        # Логирование ответа в БД
        log_entry = ResponseLog(status_code=resp.status_code, response_body=resp.text)
        db.session.add(log_entry)
        db.session.commit()

        try:
            receiver_response = resp.json()
        except Exception:
            receiver_response = resp.text

        return jsonify({
            'sent': True,
            'receiver_status': resp.status_code,
            'receiver_response': receiver_response
        }), resp.status_code

    except Exception as e:
        # Обработка ошибок отправки
        db.session.rollback()
        error_msg = f"Error sending message: {str(e)}"
        logging.error(error_msg)
        print(error_msg)
        return jsonify({'error': error_msg}), 400

if __name__ == '__main__':
    print("Sender service starting...")
    app.run(host='0.0.0.0', port=5000, debug=True)
