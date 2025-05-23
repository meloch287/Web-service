import random
from faker import Faker
import logging
from psycopg2.extras import execute_values
from .db_config import get_db_connection, release_db_connection

# Настройка логирования
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Реестр BIC-кодов
BIC_CODES = [
    '044525225', '044525226', '044525227', '044525228',
    '044525229', '044525230', '044525231', '044525232',
    '044525233', '044525234'
]

def generate_users(num_users: int) -> list:
    """Генерация пользователей и вставка в базу данных."""
    fake = Faker('ru_RU')
    users = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            client_data = []
            user_data = []
            for i in range(1, num_users + 1):
                client_id = f"{i:08d}"
                name = fake.name()
                account = '40817' + ''.join(random.choice('0123456789') for _ in range(16))
                address = fake.address().replace('\n', ', ')
                bic = random.choice(BIC_CODES)
                user = {
                    "ClientId": client_id,
                    "PAM": name[:100],
                    "FullName": name,
                    "Account": account,
                    "Address": address,
                    "Direction": "Out",
                    "PayerBIC": bic
                }
                users.append(user)
                client_data.append((name, f"Клиент {client_id}"))
                user_data.append((client_id, name[:100], name, account, address, "Out", bic))

            # Пакетная вставка в clients
            execute_values(
                cur,
                "INSERT INTO clients (name, comment) VALUES %s RETURNING id",
                client_data,
                page_size=1000
            )
            client_ids = cur.fetchall()

            # Пакетная вставка в users с игнорированием дубликатов
            execute_values(
                cur,
                """
                INSERT INTO users (client_id, pam, full_name, account, address, direction, bic)
                VALUES %s
                ON CONFLICT (client_id) DO NOTHING
                """,
                user_data,
                page_size=1000
            )

            # Обновление users с db_id
            cur.execute("SELECT client_id FROM users")
            existing_client_ids = {row[0] for row in cur.fetchall()}
            filtered_users = []
            for u, client_id in zip(users, client_ids):
                if u["ClientId"] in existing_client_ids:
                    u["db_id"] = client_id[0]
                    filtered_users.append(u)
                else:
                    logging.info(f"Пользователь с client_id {u['ClientId']} уже существует, пропущен")
            users = filtered_users

        conn.commit()
        logging.info(f"Вставлено или обновлено {len(users)} пользователей в базу данных")
        print(f"Вставлено или обновлено {len(users)} пользователей в базу данных.")
        return users
    except Exception as e:
        logging.error(f"Ошибка при генерации пользователей: {str(e)}")
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)