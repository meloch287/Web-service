import psycopg2
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests
from dicttoxml import dicttoxml
import json
import logging

# Логи
logging.basicConfig(filename="sender.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Данные для подключения к PostgreSQL
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"


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


class ResponseLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status_code = db.Column(db.Integer, nullable=False)
    response_body = db.Column(db.Text)


with app.app_context():
    db.create_all()


@app.route('/')
def home():
    return {'status' : 'OK'}, 200

@app.route('/send', methods=['POST'])
def send_message():
    try:
        content = request.get_json()
        data = content.get('data')
        fmt = content.get('format', 'json').lower()

        headers = {}
        payload = None
        if fmt == 'json':
            headers['Content-Type'] = 'application/json'
            payload = json.dumps(data)
        elif fmt == 'xml':
            headers['Content-Type'] = 'application/xml'
            payload = dicttoxml(data, custom_root='root', attr_type=False).decode()
        else:
            return jsonify({'error': 'Unsupported format'}), 400

        receiver_url = 'http://192.168.10.2:5001/receive'
        resp = requests.post(receiver_url, data=payload, headers=headers)

        log_msg = f"Sent data: {data}, Format: {fmt}, Response: {resp.status_code} - {resp.text}"
        logging.info(log_msg)
        print(log_msg)

        log = ResponseLog(status_code=resp.status_code, response_body=resp.text)
        db.session.add(log)
        db.session.commit()

        return jsonify({'sent': True, 'receiver_status': resp.status_code, 'receiver_response': resp.json()}), resp.status_code
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error: {e}")
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    print("Server is starting...")
    app.run(host='0.0.0.0', port=5000, debug=True) 
