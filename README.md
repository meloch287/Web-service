
# Описание веб-сервисов

Код состоит из трёх основных компонентов, реализованных с использованием Flask

## Компоненты проекта

### 1. Receiver (приёмник) – `receiver.py`
- **Запуск сервера:** Поднимает Flask-сервер на `localhost:5001`.
- **Приём данных:** Получает входящие данные в формате JSON или XML.
- **Логирование:** Записывает всю входящую информацию в файл `receiver.log`.
- **Сохранение данных:** Сохраняет полученные сообщения в базу данных PostgreSQL:
  - База данных: `receiver_db`.
  - Таблица: `received_message`.
- **Ответ:** Отправляет ответ с полями `trn_id`, `timestamp` и `trn_status` (Ok/Error).
- **Консольный вывод:** Выводит в консоль полученные данные и результат записи в базу данных.
  
**Новый функционал:**
- Обработка как одиночных, так и пачек сообщений.
- Логирование всех запросов с деталями об ответах.
- Отправка ответных данных с полями транзакции для каждого сообщения.

### 2. Sender (отправитель) – `sender.py`
- **Запуск сервера:** Поднимает Flask-сервер на `localhost:5000`.
- **Получение данных:** Принимает данные от клиента (запускается через `main.py`) в формате JSON или XML.
- **Пересылка данных:** Пересылает полученные данные на сервис приёмника (`receiver.py`).
- **Логирование:** Записывает переданные данные и ответ сервиса приёмника в файл `sender.log`.
- **Сохранение ответа:** Сохраняет ответ от `receiver.py` в базу данных PostgreSQL:
  - База данных: `sender_db`.
  - Таблица: `response_log`.
- **Консольный вывод:** Выводит в консоль отправленные данные, статус ответа от `receiver.py` и результат записи в базу данных.

**Новый функционал:**
- Поддержка отправки данных пачками.
- Логирование ответа от получателя в базе данных и в логах.
- Поддержка как формата JSON, так и XML.

### 3. Тестовый клиент – `main.py`
- **Отправка тестовых данных:** Формирует и отправляет тестовые данные (JSON или XML) в `sender.py`.
- **Проверка сохранения:** Производит проверку того, что данные корректно записаны в базу данных `receiver_db`.
- **Консольный вывод:** Выводит в консоль ответ от `sender.py` и содержимое базы данных для верификации.

### 4. Скрипт - `script.py`
- Скрипт для создания схемы БД на контуре отправителя, генерации пользователей и генерации JSON-файлов транзакций.
- Структура payload читается из шаблона `payload_template.json`.

**Новый функционал:**
- Отправка пачек сообщений с проверкой всех ответов от получателя.
  
## Логирование
- **receiver.log:** Файл для логирования всех входящих сообщений, полученных `receiver.py`.
- **sender.log:** Файл для логирования данных, отправленных `sender.py`, а также ответов, полученных от `receiver.py`.

## Хранение данных в PostgreSQL
- **receiver_db.received_message:** Таблица для хранения всех полученных данных сервисом `receiver.py`.
- **sender_db.response_log:** Таблица для хранения ответов, полученных от `receiver.py`, сервисом `sender.py`.


## Как запустить проект

1. **Запуск сервиса Receiver (бд создается при запуске программы):**  
   Выполните команду:  
   ```bash
   python receiver.py
   ```
   Сервер доступен на `http://localhost:5001`.

2. **Запуск сервиса Sender:**  
   Выполните команду:  
   ```bash
   python sender.py
   ```
   Сервер доступен на `http://localhost:5000`.

3. **Запуск тестового клиента:**  
   Выполните команду:  
   ```bash
   python main.py
   ```
   Клиент отправит тестовые данные в `sender.py`, после чего увидите ответ сервиса и содержимое баз данных.
