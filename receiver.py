import psycopg2
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import xmltodict
import json
import logging
from datetime import datetime

# Настройка логирования в файл receiver.log
logging.basicConfig(filename="receiver.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Данные для подключения к PostgreSQL
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

# def create_database():
#     """
#     Создает базу данных PostgreSQL, если она ещё не существует.
#     Использует соединение к системной базе postgres.
#     """
#     conn = psycopg2.connect(dbname="vtsk_db", user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
#     conn.autocommit = True
#     cursor = conn.cursor()
#     cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
#     if not cursor.fetchone():
#         cursor.execute(f"CREATE DATABASE {DB_NAME}")
#     cursor.close()
#     conn.close()

# # Проверка и создание базы данных при запуске
# create_database()

# Настройка Flask-приложения и SQLAlchemy
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

# Создание таблиц, если они ещё не созданы
with app.app_context():
    db.create_all()

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
        # Определяем формат входящего сообщения
        if request.content_type == 'application/json':
            payload = request.get_json()
        elif request.content_type in ['application/xml', 'text/xml']:
            payload = xmltodict.parse(request.data)
        else:
            return jsonify({'error': 'Unsupported Content-Type'}), 400

        # Проверка наличия поля "data" — основного контейнера сообщений
        data_field = payload.get('data')
        if data_field is None:
            return jsonify({'error': 'Поле "data" отсутствует'}), 400

        # Оборачиваем одиночное сообщение в список для унифицированной обработки
        messages = data_field if isinstance(data_field, list) else [data_field]

        for message in messages:
            # Извлекаем TrnId из вложенной структуры, если есть
            trn_id = None
            try:
                trn_id = message.get("Data", {}).get("TrnId")
            except Exception:
                pass  # если структура другая — просто оставляем trn_id пустым

            # Преобразуем сообщение в JSON-строку для сохранения
            message_json = json.dumps(message, ensure_ascii=False)
            try:
                # Сохраняем сообщение в БД
                msg = ReceivedMessage(content=message_json)
                db.session.add(msg)
                db.session.commit()
                status = "Ok"
            except Exception as e:
                db.session.rollback()
                status = "Error"
                logging.error(f"Ошибка сохранения сообщения с trn_id={trn_id}: {e}")

            # Формируем ответ по каждому сообщению
            response_entry = {
                "trn_id": trn_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "trn_status": status
            }
            responses.append(response_entry)

            # Логирование успешной обработки
            log_msg = f"Received message: {message_json} | Response: {response_entry}"
            logging.info(log_msg)
            print(log_msg)

        return jsonify({"responses": responses}), 200

    except Exception as e:
        # Обработка общей ошибки запроса
        error_msg = f"Ошибка обработки запроса: {str(e)}"
        logging.error(error_msg)
        print(error_msg)
        return jsonify({'error': error_msg}), 400

if __name__ == '__main__':
    print("Receiver service starting...")
    app.run(host='0.0.0.0', port=5001, debug=True)
