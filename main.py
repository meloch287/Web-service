import requests
import json

url = "http://localhost:5000/send"
headers = {"Content-Type": "application/json"}

data = {
    "data": [
        {
            "Data": {
                "CurrentTimestamp": "2025-04-01T11:00:00.846Z",
                "TrnId": "000001",
                "TrnType": "C2C",
                "PayerData": {
                    "ClientId": "00000000",
                    "PAM": "Иван Иванович И",
                    "FullName": "Иван Иванович Иванько",
                    "Account": "40817111111111111111",
                    "Address": "г. Мадрид, ул. Ленина, д. 1, кв. 20",
                    "Direction": "Out",
                    "PayerBIC": "044525225"
                },
                "BeneficiaryData": {
                    "PAM": "Степан Степанович С",
                    "FullName": "Степан Степанович Степанько",
                    "BeneficiaryBIC": "044525593"
                },
                "Amount": "100",
                "Currency": "RUB",
                "Narrative": "Перевод по СБП без комиссии"
            }
        },
        {
            "Data": {
                "CurrentTimestamp": "2025-04-01T12:00:00.000Z",
                "TrnId": "000002",
                "TrnType": "C2C",
                "PayerData": {
                    "ClientId": "11111111",
                    "PAM": "Пётр Петрович П",
                    "FullName": "Пётр Петрович Петров",
                    "Account": "40817222222222222222",
                    "Address": "г. Москва, ул. Победы, д. 5, кв. 10",
                    "Direction": "Out",
                    "PayerBIC": "044525226"
                },
                "BeneficiaryData": {
                    "PAM": "Сергей Сергеевич С",
                    "FullName": "Сергей Сергеевич Сергеев",
                    "BeneficiaryBIC": "044525594"
                },
                "Amount": "200",
                "Currency": "RUB",
                "Narrative": "Оплата услуг"
            }
        }
    ],
    "format": "json"
}

response = requests.post(url, json=data, headers=headers)
print(response.status_code, json.dumps(response.json(), indent=2, ensure_ascii=False))

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
