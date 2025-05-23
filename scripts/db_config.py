import psycopg2
from psycopg2.pool import SimpleConnectionPool
import logging
from tenacity import retry, stop_after_attempt, wait_fixed

# Настройка логирования
logging.basicConfig(
    filename="script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Настройки базы данных
DB_USER = "vtsk"
DB_PASSWORD = "1234"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "vtsk_db"

# SQL схема
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS "transactions" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "src_id" BIGINT,
    "dst_id" BIGINT,
    "value" NUMERIC,
    "type_id" BIGINT,
    "bnk_src_id" BIGINT,
    "bnk_dst_id" BIGINT,
    "timestamp" TIMESTAMP,
    "comment" TEXT,
    "status_id" BIGINT,
    "is_bad" BOOLEAN DEFAULT FALSE,
    "epoch_number" BIGINT DEFAULT 1,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "clients" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "name" TEXT,
    "comment" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "bank_account" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "client_id" BIGINT,
    "sum" DOUBLE PRECISION,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "transaction_types" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "type" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "transaction_status" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "status" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "banks" (
    "id" BIGSERIAL NOT NULL UNIQUE,
    "bank_name" TEXT,
    PRIMARY KEY("id")
);

CREATE TABLE IF NOT EXISTS "users" (
    "client_id" TEXT UNIQUE,
    "pam" TEXT,
    "full_name" TEXT,
    "account" TEXT,
    "address" TEXT,
    "direction" TEXT,
    "bic" TEXT
);

ALTER TABLE "transactions"
ADD FOREIGN KEY("src_id") REFERENCES "clients"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("dst_id") REFERENCES "clients"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "bank_account"
ADD FOREIGN KEY("client_id") REFERENCES "clients"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("type_id") REFERENCES "transaction_types"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("bnk_src_id") REFERENCES "banks"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("bnk_dst_id") REFERENCES "banks"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;

ALTER TABLE "transactions"
ADD FOREIGN KEY("status_id") REFERENCES "transaction_status"("id")
ON UPDATE NO ACTION ON DELETE NO ACTION;
"""

# Пул соединений с базой данных
db_pool = SimpleConnectionPool(1, 20, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT)

def get_db_connection():
    """Получение соединения из пула."""
    try:
        return db_pool.getconn()
    except psycopg2.OperationalError as e:
        logging.error(f"Ошибка получения соединения из пула: {str(e)}")
        raise

def release_db_connection(conn):
    """Возврат соединения в пул."""
    db_pool.putconn(conn)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def connect_to_db():
    """Подключение к базе данных с повторными попытками."""
    try:
        conn = get_db_connection()
        conn.autocommit = True
        return conn
    except psycopg2.OperationalError as e:
        logging.error(f"Ошибка подключения к БД: {str(e)}")
        raise

def initialize_db():
    """Инициализация схемы базы данных."""
    try:
        conn = connect_to_db()
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        logging.info("Схема БД создана/обновлена")
    except psycopg2.OperationalError as e:
        logging.error(f"Ошибка подключения к БД: {str(e)}")
        raise
    except psycopg2.DatabaseError as e:
        logging.error(f"Ошибка базы данных: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
            release_db_connection(conn)

def close_db_pool():
    """Закрытие пула соединений."""
    try:
        db_pool.closeall()
        logging.info("Пул соединений с БД закрыт")
    except Exception as e:
        logging.error(f"Ошибка при закрытии пула соединений: {str(e)}")