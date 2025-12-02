# Security Testing Platform

Платформа для тестирования эффективности защиты сетевой инфраструктуры (pfSense + Nemesida WAF + IDS/IPS) от DDoS-атак и веб-уязвимостей.

## Архитектура системы

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│     SENDER      │      │    pfSense 1    │      │    pfSense 2    │      │    RECEIVER     │
│  192.168.10.2   │─────▶│  Nemesida WAF   │─────▶│    Firewall     │─────▶│  192.168.20.2   │
│   Port: 5000    │      │   IDS/IPS       │      │   Rate Limit    │      │   Port: 5001    │
│                 │      │                 │      │                 │      │                 │
│ Traffic Gen     │      │ Attack Filter   │      │ DDoS Mitigation │      │ Target Service  │
└─────────────────┘      └─────────────────┘      └─────────────────┘      └─────────────────┘
        │                                                                          │
        └──────────────────────── Metrics Collection ─────────────────────────────┘
```

## Назначение компонентов

### Sender (Генератор трафика)
Формирует и отправляет сетевой трафик на защищаемый стенд:
- Легитимные запросы (имитация банковских транзакций)
- Вредоносные запросы (SQL Injection, XSS, Path Traversal и др.)
- DDoS-нагрузка (flood, burst, slowloris)

### Receiver (Защищаемый сервис)
Принимает трафик после прохождения через защитные механизмы:
- Фиксирует доставленные и заблокированные запросы
- Измеряет latency, throughput, packet loss
- Оценивает эффективность защиты

## Режимы генерации трафика

| Режим | Описание | Применение |
|-------|----------|------------|
| `normal` | Равномерный поток с заданным RPS | Baseline тестирование |
| `flood` | Максимальная скорость без задержек | Стресс-тест, DDoS |
| `burst` | Пачки запросов с паузами | Пиковые нагрузки |
| `slowloris` | Медленные запросы | Исчерпание соединений |
| `gradual` | Постепенное наращивание | Определение порога |
| `mixed` | Комбинация режимов | Комплексное тестирование |

## Типы атак

| Тип | Сигнатуры | Цель |
|-----|-----------|------|
| `sql_injection` | UNION, DROP, SELECT, OR '1'='1 | База данных |
| `xss` | \<script\>, javascript:, onerror= | Браузер клиента |
| `path_traversal` | ../, %2e%2e, /etc/passwd | Файловая система |
| `cmd_injection` | ; ls, \| cat, $(cmd) | Командная оболочка |
| `xxe` | \<!DOCTYPE\>, \<!ENTITY\> | XML-парсер |
| `ssrf` | localhost, 169.254.169.254 | Внутренние сервисы |

## Установка

```bash
git clone <repository>
cd security-testing-platform
pip install -r requirements.txt
cp .env.example .env
```

Настройка `.env`:
```
RECEIVER_URL=http://192.168.20.2:5001
SENDER_CALLBACK_URL=http://192.168.10.2:5000
```

## Запуск

### Receiver (на защищаемой машине 192.168.20.2)
```bash
python run_receiver.py
```

### Sender (на атакующей машине 192.168.10.2)
```bash
python run_sender.py
```

### Запуск теста

CLI:
```bash
# Базовый тест
python run_simulation.py normal 1000 100 0.1 "sql_injection,xss"

# DDoS flood
python run_simulation.py flood 10000 0 0.2 "sql_injection,xss,path_traversal"

# Burst-атака
python run_simulation.py burst 5000 500 0.15 "sql_injection,cmd_injection"
```

API:
```bash
# Запуск теста
curl -X POST "http://192.168.10.2:5000/start?mode=flood&total_requests=5000&malicious_ratio=0.2"

# Статус
curl "http://192.168.10.2:5000/status/{session_id}"

# Отчет
curl "http://192.168.10.2:5000/report/{session_id}"
```

## API Endpoints

### Sender (port 5000)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/` | Health check |
| POST | `/start` | Запуск теста |
| GET | `/status/{session_id}` | Статус сессии |
| GET | `/timeline/{session_id}` | Timeline метрик |
| GET | `/report/{session_id}` | Полный отчет |
| POST | `/stop/{session_id}` | Остановка теста |
| GET | `/sessions` | Список сессий |

### Receiver (port 5001)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/` | Health check |
| POST | `/receive` | Прием трафика |
| GET | `/stats/{session_id}` | Статистика |
| GET | `/events/{session_id}` | События защиты |

## Метрики

### Latency
- `avg_ms` — среднее время ответа
- `p50_ms` — медиана
- `p95_ms` — 95-й перцентиль
- `p99_ms` — 99-й перцентиль

### Protection Effectiveness
- `detection_rate` — % обнаруженных атак
- `false_positive_rate` — % ложных срабатываний
- `blocked_by` — источник блокировки (WAF/Firewall/IDS)

### Throughput
- `requests_per_second` — пропускная способность
- `total_sent/received/blocked` — счетчики запросов

## Пример вывода

```
======================================================================
TEST RESULTS
======================================================================

Duration: 45.23s
Throughput: 221.4 req/s

--- Traffic Stats ---
Total sent: 10000
Total received: 9847
Total blocked: 1523
Block rate: 15.5%

--- Latency (ms) ---
Avg: 12.34 | Min: 2.10 | Max: 234.56
P50: 8.45 | P95: 45.67 | P99: 89.12

--- Protection Effectiveness ---
Malicious sent: 1000
Malicious blocked: 892
Malicious passed: 108
Detection rate: 89.2%
False positive rate: 2.1%

--- Blocked By ---
  nemesida_waf: 1245
  pfsense: 278

WARNING: 108 malicious requests passed through
```

## Структура проекта

```
├── app/
│   ├── attacks/
│   │   ├── patterns.py      # Сигнатуры атак
│   │   └── generator.py     # Генератор трафика
│   ├── services/
│   │   └── metrics.py       # Сбор метрик
│   ├── config.py            # Конфигурация
│   ├── database.py          # SQLAlchemy async
│   ├── models.py            # ORM модели
│   ├── schemas.py           # Pydantic схемы
│   ├── sender.py            # Sender API
│   ├── receiver.py          # Receiver API
│   └── main.py              # CLI runner
├── run_sender.py
├── run_receiver.py
├── run_simulation.py
├── requirements.txt
└── .env.example
```

## Требования

- Python 3.10+
- PostgreSQL 14+
- Сетевая связность между Sender и Receiver через pfSense

## Лицензия

MIT
