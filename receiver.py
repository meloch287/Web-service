import psycopg2
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import xmltodict
import json
import logging

# Логи
logging.basicConfig(filename="receiver.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Данные для подключения к PostgreSQL
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

# Создание базы данных, если её нет
def create_database():
    conn = psycopg2.connect(dbname="postgres", user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)
    conn.autocommit = True
    cursor = conn.cursor()
    cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
    if not cursor.fetchone():
        cursor.execute(f"CREATE DATABASE {DB_NAME}")
    cursor.close()
    conn.close()

create_database()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class ReceivedMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return {'status' : 'OK'}, 200 

@app.route('/receive', methods=['POST'])
def receive_message():
    try:
        if request.content_type == 'application/json':
            data = request.get_json()
        elif request.content_type in ['application/xml', 'text/xml']:
            data = xmltodict.parse(request.data)
        else:
            return jsonify({'error': 'Unsupported Content-Type'}), 400

        msg = ReceivedMessage(content=json.dumps(data, ensure_ascii=False))
        db.session.add(msg)
        db.session.commit()

        log_msg = f"Received data: {data}"
        logging.info(log_msg)
        print(log_msg)

        return jsonify({'status': 'Data received'}), 200
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error: {e}")
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    print("Server is starting...")
    app.run(host='0.0.0.0', port=5001, debug=True)
