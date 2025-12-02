# Security Testing Platform

Платформа для тестирования эффективности защиты сетевой инфраструктуры (pfSense + Nemesida WAF + IDS/IPS) от DDoS-атак и веб-уязвимостей с математическим моделированием и статистическим анализом.

## Архитектура

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│     SENDER      │      │    pfSense 1    │      │    pfSense 2    │      │    RECEIVER     │
│  192.168.10.2   │─────▶│  Nemesida WAF   │─────▶│    Firewall     │─────▶│  192.168.20.2   │
│   Port: 5000    │      │   IDS/IPS       │      │   Rate Limit    │      │   Port: 5001    │
└─────────────────┘      └─────────────────┘      └─────────────────┘      └─────────────────┘
        │                        │                        │                        │
        └────────────────────────┴────────────────────────┴────────────────────────┘
                                         │
                                    ┌────┴────┐
                                    │ Zabbix  │
                                    │ Monitor │
                                    └─────────┘
```

## Математическое моделирование

### Вероятностные модели трафика

Система использует следующие статистические модели:

**Пуассоновский процесс** для моделирования потока запросов:
```
P(N(t) = k) = (λt)^k * e^(-λt) / k!
```
где λ — интенсивность потока (requests/sec)

**Экспоненциальное распределение** для межпакетных интервалов:
```
f(x) = λ * e^(-λx), x ≥ 0
```

**Марковские цепи** для анализа состояний системы:
- States: {normal, suspicious, attack, blocked}
- Transition matrix P[i,j] = P(X_{n+1} = j | X_n = i)

### Статистические тесты

- **t-test** — сравнение средних baseline vs current
- **Mann-Whitney U** — непараметрический тест
- **Kolmogorov-Smirnov** — сравнение распределений
- **Z-score** — обнаружение выбросов

### Расчёт аномалий

Порог аномальности определяется методами:
- IQR (Interquartile Range): threshold = Q3 + 1.5 * IQR
- Z-score: threshold = μ + z_α * σ
- MAD (Median Absolute Deviation): threshold = median + 3 * 1.4826 * MAD

## SLA-анализ

### Целевые показатели (SLO)

| Метрика | Target | Warning | Critical |
|---------|--------|---------|----------|
| Availability | 99.9% | 99.5% | 99.0% |
| Latency P50 | 50ms | 100ms | 200ms |
| Latency P95 | 200ms | 500ms | 1000ms |
| Latency P99 | 500ms | 1000ms | 2000ms |
| Throughput | 1000 rps | 500 rps | 100 rps |

### Деградация качества

Система строит кривую деградации:
```
latency(intensity) = a*x² + b*x + c
```
и определяет точку срыва SLA (breaking point).

## Интеграция с Zabbix

Сбор метрик с защитной инфраструктуры:

**pfSense:**
- CPU/Memory utilization
- Network throughput (in/out)
- Firewall states count
- Blocked/Passed packets

**Nemesida WAF:**
- Total/Blocked requests
- Attack types (SQLi, XSS, RCE)
- Average latency
- WAF CPU usage

## Корреляционный анализ

### Сигнатуры атак

| Тип атаки | Признаки |
|-----------|----------|
| SYN Flood | request_rate_spike > 5x, connection_ratio < 0.1 |
| HTTP Flood | request_rate_spike > 3x, response_time_increase > 2x |
| Slowloris | connection_duration > 10x, incomplete_requests > 80% |
| Amplification | response/request ratio > 10x, UDP spike > 5x |

### Корреляция событий

Анализ связи между событиями разных уровней защиты:
- Pearson correlation для временных рядов
- Cross-correlation для определения задержки между событиями

## Реалистичные DDoS-сценарии

### Генерация ботнета

```python
botnet = generator.generate_botnet(
    size=10000,
    geo_distribution={"US": 0.25, "CN": 0.20, "RU": 0.15, ...}
)
```

### Типы атак

- **SYN Flood**: TCP SYN packets с различными window sizes
- **UDP Flood**: Large UDP packets на порты 53, 123, 161
- **DNS Amplification**: Запросы ANY/TXT с amplification 28-54x
- **NTP Amplification**: monlist с amplification 200-556x
- **Slowloris**: Partial HTTP requests с keep-alive

## Хранение данных

### Схема PostgreSQL

```
test_sessions          - Сессии тестирования
traffic_events         - Отдельные события (per-packet)
interval_metrics       - Агрегированные метрики по интервалам
statistical_models     - Параметры статистических моделей
sla_violations         - Нарушения SLA
attack_patterns        - Обнаруженные паттерны атак
```

### Индексы

- `idx_session_timestamp` — быстрый поиск по сессии и времени
- `idx_blocked` — фильтрация заблокированных запросов
- `idx_attack_type` — группировка по типам атак

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
```

## Запуск

```bash
# Receiver (192.168.20.2)
python run_receiver.py

# Sender (192.168.10.2)
python run_sender.py

# Тест
python run_simulation.py flood 10000 0 0.2 "sql_injection,xss"
```

## API

### Sender (port 5000)

| Endpoint | Описание |
|----------|----------|
| POST /start | Запуск теста |
| GET /status/{id} | Статус с метриками |
| GET /report/{id} | Полный отчёт с SLA |
| GET /statistical/{id} | Статистическая модель |

### Receiver (port 5001)

| Endpoint | Описание |
|----------|----------|
| POST /receive | Приём трафика |
| GET /stats/{id} | Статистика защиты |
| GET /events/{id} | События блокировки |

## Структура проекта

```
app/
├── analysis/
│   ├── statistical.py    # Статистические модели, Марковские цепи
│   ├── sla.py            # SLA-анализ, деградация
│   └── correlation.py    # Корреляция, сигнатуры атак
├── attacks/
│   ├── patterns.py       # Паттерны веб-атак
│   ├── generator.py      # Генератор трафика
│   └── realistic.py      # Реалистичные DDoS
├── integrations/
│   └── zabbix.py         # Интеграция с Zabbix
├── storage/
│   └── database.py       # PostgreSQL схема
├── services/
│   └── metrics.py        # Сбор метрик
├── sender.py
├── receiver.py
└── main.py
```

## Метрики эффективности

### ROC-анализ

- True Positive Rate (TPR) = TP / (TP + FN)
- False Positive Rate (FPR) = FP / (FP + TN)
- Detection Rate = blocked_malicious / total_malicious
- False Positive Rate = blocked_normal / total_normal

### Trade-off Security vs Availability

Система анализирует баланс между:
- Высокий detection rate → больше false positives
- Низкий FPR → пропуск атак

## Требования

- Python 3.10+
- PostgreSQL 14+
- Zabbix 6.0+ (опционально)
- scipy, numpy для статистики


## Симуляция банковских транзакций

### Запуск

```bash
# Запустить receiver
python run_receiver.py

# В другом терминале — симуляция
python run_bank_simulation.py --users 100 --transactions 1000 --rps 50
```

### Математические модели распределений

| Распределение | Применение | Формула |
|---------------|------------|---------|
| Нормальное | Легитимный трафик (пик 12:00-14:00) | f(x) = (1/σ√2π) * e^(-(x-μ)²/2σ²) |
| Пуассоновское | Случайные атаки | P(k) = λ^k * e^(-λ) / k! |
| Парето | Кластеризация атак (80/20) | f(x) = αx_m^α / x^(α+1) |
| Экспоненциальное | Затухающие атаки | f(x) = λ * e^(-λx) |

### Коды аномалий (для БД)

| Код | Тип аномалии |
|-----|--------------|
| 0 | Норма |
| 1 | SQL-инъекция |
| 2 | XSS-атака |
| 3 | Частотная аномалия |
| 4 | Аномалия суммы |
| 5 | Гео-аномалия |
| 6 | Временная аномалия |
| 7 | DDoS |
| 8 | Брутфорс |

### Визуализация

Графики сохраняются в `reports/simulation_*.png`:
- Распределение транзакций за 24 часа (4 модели)
- Детекция по типам аномалий
- Ключевые метрики эффективности
- Распределение времени отклика
- Математические модели распределений
- Детекция с кодами для БД
