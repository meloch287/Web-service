

import requests

url = "http://localhost:5000/send"
headers = {"Content-Type": "application/json"}

data = {
    "data": {
            "message": "привет!",
        "id": 456
    },
    "format": "json"
}

response = requests.post(url, json=data, headers=headers)
print(response.status_code, response.json())

'''

import requests
import psycopg2
import xml.etree.ElementTree as ET
import json

RECEIVER_URL = "http://localhost:5001/receive"
DB_CONFIG = {
    "dbname": "vtsk_db",
    "user": "vtsk",
    "password": "1234",
    "host": "localhost",
    "port": "5432"
}

def send_xml():
    headers = {"Content-Type": "application/xml"}
    data = """<data>
        <message>Тестовое сообщение</message>
        <id>123</id>
        <format>xml</format>
    </data>"""
    response = requests.post(RECEIVER_URL, data=data, headers=headers)
    print(f"Response: {response.status_code}, {response.text}")

def check_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM received_message ORDER BY id DESC LIMIT 1;")
        record = cursor.fetchone()
        if record:
            print("Last record in DB:", record[0])
            try:
                parsed_data = json.loads(record[0])
                print("Parsed JSON:", json.dumps(parsed_data, indent=4, ensure_ascii=False))
            except json.JSONDecodeError:
                print("Failed to decode JSON")
        else:
            print("No records found in DB")
        cursor.close()
        conn.close()
    except Exception as e:
        print("DB Error:", e)

if __name__ == "__main__":
    send_xml()
    # check_db()
'''
