# Платформа моделирования Системы Быстрых Платежей (СБП)

Платформа для имитационного моделирования платежной системы с применением теории массового обслуживания (G/G/c/K). Система реализует математическое моделирование потока транзакций, анализ устойчивости платежной инфраструктуры и оценку соответствия SLA.

## Содержание

1. [Обзор системы](#обзор-системы)
2. [Теория массового обслуживания G/G/c/K](#теория-массового-обслуживания-ggck)
3. [Формализация потоков N_bg(t) и N_anom(t)](#формализация-потоков)
4. [Симуляция СБП](#симуляция-сбп)
5. [Симуляция банковских транзакций](#симуляция-банковских-транзакций)
6. [Математическое моделирование](#математическое-моделирование)
7. [Статистический анализ](#статистический-анализ)
8. [SLA-анализ](#sla-анализ)
9. [Архитектура](#архитектура)
10. [Хранение данных](#хранение-данных)
11. [Установка и настройка](#установка-и-настройка)
12. [API Reference](#api-reference)
13. [Примеры использования](#примеры-использования)

---

## Обзор системы

### Назначение

Платформа предназначена для:
- Имитационного моделирования **Системы Быстрых Платежей (СБП)**
- Анализа устойчивости платежной инфраструктуры с применением **теории массового обслуживания**
- Расчёта метрик **G/G/c/K модели**: коэффициент загрузки ρ(t), вероятность блокировки P_block, доля потерь D_loss
- Применения **формулы Полячека-Хинчина** для расчёта времени ожидания
- Моделирования **платежных аномалий**: микротранзакции, высокие суммы, всплески частоты
- Оценки SLA платежной системы и определения точек отказа

### Компоненты

| Компонент | Описание |
|-----------|----------|
| **SBP Simulator** | Симулятор платежной системы с очередью G/G/c/K |
| **Queuing Analyzer** | Расчёт метрик теории массового обслуживания |
| **Markov Model** | Марковская модель состояний транзакций |
| **PostgreSQL** | Хранение результатов симуляции |

---

## Теория массового обслуживания G/G/c/K

### Модель системы

Платежная система моделируется как система массового обслуживания **G/G/c/K**:
- **G** — произвольное распределение входящего потока
- **G** — произвольное распределение времени обслуживания  
- **c** — количество серверов (параллельных обработчиков)
- **K** — ёмкость очереди

### Коэффициент загрузки

```
ρ(t) = λ(t) / (c × μ)
```

где:
- `λ(t)` — интенсивность входящего потока транзакций
- `c` — количество серверов
- `μ` — скорость обслуживания одного сервера

### Формула Полячека-Хинчина

Среднее время ожидания в очереди:

```
E[W] = (ρ / (1 - ρ)) × ((1 + C_s²) / 2) × (1 / μ)
```

где `C_s²` — квадрат коэффициента вариации времени обслуживания.

### Вероятность блокировки (Erlang C)

```
P_wait = (a^c / c!) × (c / (c - a)) / [Σ(a^n/n!) + (a^c/c!) × (c/(c-a))]
```

где `a = λ/μ` — предложенная нагрузка.

### Доля потерянных транзакций

```
D_loss = ∫P_block(t) × n_tot(t) dt / ∫n_tot(t) dt
```

### Ожидаемое время до первого отказа

```
E[T_fail] = 1 / λ_margin
```

где `λ_margin = (ρ_threshold - ρ) × c × μ`

---

## Формализация потоков

### Суперпозиция потоков N(t) = N_bg(t) + N_anom(t)

Общий поток транзакций разделяется на два компонента:

**Фоновый поток N_bg(t)** — легитимный трафик по гауссовой формуле:
```
N_bg(t) = A × exp(-(t - t_m)² / (2σ²))
```

где:
- `A` — амплитуда пика (макс. транзакций/сек)
- `t_m` — время достижения максимума
- `σ` — стандартное отклонение (ширина пика)

**Аномальный поток N_anom(t)** — атакующий трафик с выбираемым распределением:
- Normal (Gaussian)
- Exponential
- Poisson
- Pareto (heavy-tail)

### Использование

```python
from app.models import TrafficFlowConfig, BackgroundTrafficParams, AnomalousTrafficParams, DistributionParams, DistributionType
from app.traffic import TrafficFlowGenerator

config = TrafficFlowConfig(
    background=BackgroundTrafficParams(A=1000, t_m=12.0, sigma=4.0),
    anomalous=AnomalousTrafficParams(
        distribution=DistributionType.EXPONENTIAL,
        total_volume=5000,
        start_time=10.0,
        duration=5.0,
        params=DistributionParams(rate=2.0)
    )
)

generator = TrafficFlowGenerator(config)
time_series = generator.generate_time_series(0, 24, dt=0.1)

print(f"Background: {time_series.background_count}")
print(f"Anomalous: {time_series.anomalous_count}")
```

### GGcKQueueingSystem

```python
from app.models import QueueingSystemConfig
from app.analysis import GGcKQueueingSystem

config = QueueingSystemConfig(c=10, K=1000, mu=100.0, sla_epsilon=0.01, sla_delta=0.05)
system = GGcKQueueingSystem(config)

analysis = system.analyze(time_series)
report = system.generate_report(analysis)

print(f"ρ avg: {analysis.utilization.avg_utilization:.2f}")
print(f"D_loss: {analysis.d_loss.d_loss:.4f}")
print(f"E[T_fail]: {analysis.e_t_fail:.2f}s")
print(f"SLA compliant: {report.overall_compliant}")
```

### Маркировка транзакций

Каждая транзакция маркируется для ML-разметки:
```python
{
    "traffic_type": "background" | "anomalous",
    "distribution": "gaussian" | "exponential" | "poisson" | "pareto"
}
```

### Спецификация

Полная спецификация доступна в `.kiro/specs/traffic-flow-formalization/`:
- `requirements.md` — требования EARS/INCOSE
- `design.md` — архитектура и correctness properties
- `tasks.md` — план реализации
from app.analysis import GGcKQueueingSystem

config = QueueingSystemConfig(c=10, K=1000, mu=100.0, sla_epsilon=0.01, sla_delta=0.05)
system = GGcKQueueingSystem(config)

analysis = system.analyze(time_series)
report = system.generate_report(analysis)

print(f"D_loss: {report.d_loss}")
print(f"SLA Compliant: {report.overall_compliant}")
```

### Маркировка транзакций

Каждая транзакция маркируется для ML-разметки:
```python
{
    "traffic_type": "background" | "anomalous",
    "distribution": "gaussian" | "exponential" | "poisson" | "pareto"
}
```

---

## Формализация потоков

### Суперпозиция потоков N(t) = N_bg(t) + N_anom(t)

Общий поток транзакций разделяется на два компонента:

**Фоновый поток N_bg(t)** — легитимный трафик по гауссовой формуле:
```
N_bg(t) = A × exp(-(t - t_m)² / (2σ²))
```

где:
- `A` — амплитуда пика (макс. транзакций/сек)
- `t_m` — время достижения максимума
- `σ` — стандартное отклонение (ширина пика)

**Аномальный поток N_anom(t)** — атакующий трафик с выбираемым распределением:
- Normal (Gaussian)
- Exponential
- Poisson
- Pareto (heavy-tail)

### Маркировка транзакций

Каждая транзакция маркируется для ML-разметки:
```python
{
    "traffic_type": "background" | "anomalous",
    "distribution": "gaussian" | "exponential" | "poisson" | "pareto"
}
```

### Спецификация

Полная спецификация доступна в `.kiro/specs/traffic-flow-formalization/`:
- `requirements.md` — требования EARS/INCOSE
- `design.md` — архитектура и correctness properties
- `tasks.md` — план реализации

---

## Быстрый старт

### Основной поток работы

```bash
# 1. Генерация транзакций в JSON
python generate_transactions.py --transactions 10000 --anomaly-ratio 0.15

# 2. Запуск receiver (в отдельном терминале)
python run_receiver.py

# 3. Запуск симуляции
python run_bank_simulation.py --rps 100
```

### Структура проекта

```
📁 корень проекта
├── generate_transactions.py    ← Предгенерация транзакций в JSON
├── run_bank_simulation.py      ← Отправка транзакций на receiver
├── run_sender.py               ← Запуск sender API (порт 8000)
├── run_receiver.py             ← Запуск receiver API (порт 8001)
├── setup_db.py                 ← Настройка БД
│
├── 📁 app/                     ← Основной код приложения
│   ├── sender.py               ← FastAPI sender
│   ├── receiver.py             ← FastAPI receiver
│   ├── 📁 analysis/            ← Анализ и метрики
│   ├── 📁 attacks/             ← Генераторы атак
│   ├── 📁 models/              ← Pydantic модели
│   └── 📁 traffic/             ← Генераторы трафика
│
├── 📁 tools/                   ← Вспомогательные скрипты
│   ├── test_traffic_flow.py    ← Тесты модулей
│   ├── run_sbp_simulation.py   ← Автономный симулятор СБП
│   └── run_simulation.py       ← CLI обёртка
│
├── 📁 data/transactions/       ← JSON файлы с транзакциями
└── 📁 reports/                 ← Графики результатов
```

---

## Симуляция банковских транзакций

### Шаг 1: Генерация транзакций

```bash
python generate_transactions.py --users 100 --transactions 30000 --anomaly-ratio 0.15
```

Создаёт JSON файл в `data/transactions/` с:
- Метаданными сессии
- Статистикой по распределениям
- Списком пользователей
- Транзакциями с маркировкой `is_malicious`, `attack_type`, `distribution`

### Шаг 2: Запуск симуляции

```bash
# Запустить receiver
python run_receiver.py

# В другом терминале - симуляция
python run_bank_simulation.py --input data/transactions/transactions_XXX.json --rps 100
```

### Параметры generate_transactions.py

| Параметр | Default | Описание |
|----------|---------|----------|
| --users | 100 | Количество пользователей |
| --transactions | 30000 | Количество транзакций |
| --anomaly-ratio | 0.15 | Доля аномалий (0-1) |
| --output | data/transactions | Директория для сохранения |

### Типы платежных аномалий

| Код | Тип | Описание |
|-----|-----|----------|
| 0 | NORMAL | Нормальная транзакция |
| 1 | MICRO_TRANSACTION | Микротранзакция (1-100 руб) |
| 2 | HIGH_AMOUNT | Высокая сумма (500k-5M руб) |
| 3 | UNUSUAL_TIME | Необычное время |
| 4 | GEO_ANOMALY | Гео-аномалия |
| 5 | VELOCITY_SPIKE | Всплеск частоты |
| 6 | INTERRUPTED | Прерванный платёж |
| 7 | HIGH_VOLATILITY | Высокая волатильность суммы |

### Марковская модель состояний транзакции

```
States = {QUEUED, PROCESSING, COMPLETED, REJECTED, TIMEOUT}

Переходы:
QUEUED → PROCESSING (успешная постановка на обработку)
QUEUED → REJECTED (очередь полна / перегрузка)
PROCESSING → COMPLETED (успешная обработка)
PROCESSING → REJECTED (превышение лимита / rate limit)
PROCESSING → TIMEOUT (таймаут обработки)
```

### Визуализация

Графики сохраняются в `reports/sbp_*.png`:
1. **Распределение транзакций за 24 часа** — успешные vs отклонённые
2. **Коэффициент загрузки ρ(t)** — динамика загрузки системы
3. **Вероятность блокировки P_block(t)** — с расчётом D_loss
4. **Распределение времени обработки** — по формуле Полячека-Хинчина
5. **Успешность по типам транзакций** — анализ аномалий
6. **Длина очереди E[L_q](t)** — динамика очереди

---

## Архитектура

### Поток данных

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ПРЕДГЕНЕРАЦИЯ                                  │
│  ┌─────────────────────────┐                                                │
│  │ generate_transactions.py │  Генерация датасета:                          │
│  │                         │  • Легитимные транзакции (норм. распр.)        │
│  │  Transaction Generator  │  • Аномалии (Пуассон, Парето, Экспоненц.)      │
│  │                         │  • SQL Injection, XSS, Fraud                   │
│  └───────────┬─────────────┘                                                │
│              │                                                              │
│              ▼                                                              │
│  ┌─────────────────────────┐                                                │
│  │ data/transactions/      │  JSON файлы с транзакциями:                    │
│  │   transactions_XXX.json │  • metadata, statistics                        │
│  │                         │  • users[], transactions[]                     │
│  └───────────┬─────────────┘  • is_malicious, attack_type, distribution     │
│              │                                                              │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              СИМУЛЯЦИЯ                                      │
│  ┌─────────────────────────┐                                                │
│  │ run_bank_simulation.py  │  Отправка транзакций:                          │
│  │                         │  • Чтение JSON датасета                        │
│  │  Bank Simulator         │  • Async HTTP отправка                         │
│  │                         │  • Сбор метрик latency                         │
│  └───────────┬─────────────┘  • Генерация отчётов                           │
│              │                                                              │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ЗАЩИТНЫЙ ПЕРИМЕТР                                   │
│  ┌─────────────────┐      ┌─────────────────┐                               │
│  │   pfSense 1     │      │   pfSense 2     │                               │
│  │                 │      │                 │                               │
│  │ • Nemesida WAF  │─────▶│ • Firewall      │  Уровни защиты:               │
│  │ • IDS/IPS       │      │ • Rate Limiting │  1. WAF (L7)                  │
│  │ • Packet Filter │      │ • GeoIP Block   │  2. IDS/IPS (L3-L4)           │
│  │                 │      │                 │  3. Firewall (L3)             │
│  └────────┬────────┘      └────────┬────────┘  4. Rate Limiting             │
│           │                        │                                        │
│           └────────────┬───────────┘                                        │
│                        │                                                    │
│                        ▼                                                    │
│              ┌─────────────────┐                                            │
│              │     Zabbix      │  Мониторинг:                               │
│              │    Monitoring   │  • CPU/Memory pfSense                      │
│              │                 │  • Network throughput                      │
│              │                 │  • Blocked packets                         │
│              │                 │  • WAF events                              │
│              └─────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ЗАЩИЩАЕМЫЙ СЕГМЕНТ                                  │
│  ┌─────────────────────────┐                                                │
│  │    RECEIVER             │                                                │
│  │    run_receiver.py      │  Функции:                                      │
│  │    Port: 8001           │  • Приём трафика                               │
│  │                         │  • Детекция атак (сигнатуры)                   │
│  │    app/receiver.py      │  • Измерение latency                           │
│  │                         │  • Сохранение в SQLite                         │
│  └───────────┬─────────────┘  • Статистика защиты                           │
│              │                                                              │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              РЕЗУЛЬТАТЫ                                     │
│  ┌─────────────────────────┐                                                │
│  │ reports/                │  Выходные данные:                              │
│  │   simulation_XXX.png    │  • Графики распределений                       │
│  │                         │  • Метрики детекции                            │
│  │                         │  • Latency percentiles                         │
│  └─────────────────────────┘  • SLA compliance                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Компоненты системы

| Компонент | Файл | Порт | Описание |
|-----------|------|------|----------|
| **Generator** | `generate_transactions.py` | - | Предгенерация транзакций в JSON |
| **Simulator** | `run_bank_simulation.py` | - | Отправка транзакций из JSON |
| **Sender API** | `run_sender.py` | 8000 | FastAPI для управления тестами |
| **Receiver API** | `run_receiver.py` | 8001 | FastAPI для приёма трафика |

### Альтернативный поток (через Sender API)

```bash
# 1. Запуск receiver
python run_receiver.py

# 2. Запуск sender
python run_sender.py

# 3. Запуск теста через API
curl -X POST "http://127.0.0.1:8000/start?mode=normal&total_requests=1000&malicious_ratio=0.2"

# 4. Проверка статуса
curl http://127.0.0.1:8000/sessions
```

---

## Математическое моделирование

### Теоретическая основа

Система использует математический аппарат теории массового обслуживания и теории вероятностей для моделирования сетевого трафика.

### Пуассоновский процесс

Поток запросов моделируется как пуассоновский процесс с интенсивностью λ:

```
P(N(t) = k) = (λt)^k × e^(-λt) / k!
```

где:
- `N(t)` — количество запросов за время t
- `λ` — интенсивность потока (requests/second)
- `k` — конкретное число событий

**Оценка параметров:**
```python
λ_MLE = n / T  # Maximum Likelihood Estimation
Var(λ) = λ / T
CI = λ ± z_α/2 × √(λ/T)  # Доверительный интервал
```

### Экспоненциальное распределение

Межпакетные интервалы (IAT) следуют экспоненциальному распределению:

```
f(x) = λ × e^(-λx), x ≥ 0
E[X] = 1/λ
Var(X) = 1/λ²
```

### Марковские цепи

Состояния системы моделируются как Марковская цепь:

```
States = {normal, suspicious, attack, blocked}

Transition Matrix P:
              normal  suspicious  attack  blocked
normal        0.85    0.10        0.04    0.01
suspicious    0.30    0.50        0.15    0.05
attack        0.05    0.10        0.60    0.25
blocked       0.20    0.10        0.20    0.50
```

**Стационарное распределение:**
```
π = π × P, где Σπ_i = 1
```

**Среднее время до атаки:**
```
MTTA = Σ N[0,j], где N = (I - Q)^(-1)
```

### Реализация

```python
from app.analysis.statistical import StatisticalAnalyzer, MarkovChainAnalyzer

# Статистический анализ
analyzer = StatisticalAnalyzer(confidence_level=0.95)

# Параметры пуассоновского процесса
poisson_params = analyzer.calculate_poisson_parameters(
    arrivals=timestamps,
    time_window=3600  # 1 час
)
# Returns: {lambda: 150.5, variance: 150.5, confidence_interval: (145.2, 155.8)}

# Построение модели трафика
model = analyzer.build_traffic_model(timestamps, values)
# Returns: TrafficModel(lambda_intensity, variance, mean, std_dev, distribution, anomaly_threshold)

# Марковский анализ
markov = MarkovChainAnalyzer()
markov.update_transition("normal", "suspicious")
markov.update_transition("suspicious", "attack")

stationary = markov.get_stationary_distribution()
attack_prob = markov.get_attack_probability(steps=5)
mtta = markov.get_mean_time_to_attack()
```

---

## Статистический анализ

### Тесты гипотез

Для различения нормального и атакующего трафика используются статистические тесты:

| Тест | Назначение | H₀ | Статистика |
|------|------------|-----|------------|
| **t-test** | Сравнение средних | μ₁ = μ₂ | t = (x̄₁ - x̄₂) / SE |
| **Mann-Whitney U** | Непараметрическое сравнение | F₁ = F₂ | U = n₁n₂ + n₁(n₁+1)/2 - R₁ |
| **Kolmogorov-Smirnov** | Сравнение распределений | F₁ = F₂ | D = sup|F₁(x) - F₂(x)| |

### Обнаружение аномалий

**Метод IQR (Interquartile Range):**
```
Q1 = 25-й перцентиль
Q3 = 75-й перцентиль
IQR = Q3 - Q1
Threshold = Q3 + 1.5 × IQR
```

**Метод Z-score:**
```
z = (x - μ) / σ
Anomaly if |z| > z_critical (обычно 3)
```

**Метод MAD (Median Absolute Deviation):**
```
MAD = median(|x_i - median(x)|)
Threshold = median + 3 × 1.4826 × MAD
```

### Реализация

```python
from app.analysis.statistical import AnomalyDetector

detector = AnomalyDetector(window_size=100)

# Обучение на baseline
for value in baseline_traffic:
    detector.update_baseline(value)

# Детекция аномалий
result = detector.detect_anomaly(current_values)
# Returns:
# {
#     "is_anomaly": True,
#     "confidence": 0.95,
#     "z_score": 4.2,
#     "threshold": 1523.5,
#     "statistical_test": {...},
#     "markov_state": "attack",
#     "attack_probability": 0.78
# }
```

---

## SLA-анализ

### Service Level Objectives (SLO)

| Метрика | Target | Warning | Critical | Unit |
|---------|--------|---------|----------|------|
| **Availability** | 99.9% | 99.5% | 99.0% | % |
| **Latency P50** | 50 | 100 | 200 | ms |
| **Latency P95** | 200 | 500 | 1000 | ms |
| **Latency P99** | 500 | 1000 | 2000 | ms |
| **Throughput** | 1000 | 500 | 100 | req/s |
| **Error Rate** | 0.1% | 1.0% | 5.0% | % |
| **Packet Loss** | 0.01% | 0.1% | 1.0% | % |

### Расчёт Compliance

```python
Compliance% = (actual / target) × 100  # для "higher is better"
Compliance% = ((critical - actual) / (critical - target)) × 100  # для "lower is better"
```

### Кривая деградации

Зависимость latency от интенсивности атаки аппроксимируется полиномом:

```
latency(intensity) = a×x² + b×x + c
```

**Определение точки срыва SLA:**
```
Solve: a×x² + b×x + c = SLA_threshold
x_break = (-b + √(b² - 4a(c - threshold))) / 2a
```

### Реализация

```python
from app.analysis.sla import SLAAnalyzer

sla = SLAAnalyzer()

# Анализ доступности
availability = sla.analyze_availability(
    total_requests=10000,
    successful_requests=9950,
    time_window_seconds=3600
)
# Returns: SLAMetric(current_value=99.5, target=99.9, status=WARNING, compliance=99.6%)

# Анализ latency
latency_metrics = sla.analyze_latency(latencies=[12, 15, 45, 23, ...])
# Returns: {p50: SLAMetric, p95: SLAMetric, p99: SLAMetric}

# Кривая деградации
degradation = sla.calculate_degradation_curve(
    attack_intensities=[100, 500, 1000, 2000, 5000],
    response_times=[50, 120, 350, 890, 2100]
)
# Returns: {
#     polynomial_coefficients: [0.0001, 0.15, 35],
#     r_squared: 0.97,
#     sla_breach_intensity: 1847,  # req/s при котором нарушается SLA
#     degradation_rate: 0.15
# }

# Полный отчёт
report = sla.generate_sla_report(metrics)
# Returns: overall_compliance, violations, cost_impact, recommendations
```

---

## Интеграция с Zabbix

### Собираемые метрики

**pfSense:**
| Ключ Zabbix | Метрика | Описание |
|-------------|---------|----------|
| `system.cpu.util` | CPU Utilization | Загрузка процессора |
| `vm.memory.util` | Memory Utilization | Использование памяти |
| `net.if.in[em0]` | Network In | Входящий трафик |
| `net.if.out[em0]` | Network Out | Исходящий трафик |
| `pfsense.states.count` | Firewall States | Количество состояний |
| `pfsense.rules.blocked` | Blocked Packets | Заблокированные пакеты |
| `pfsense.rules.passed` | Passed Packets | Пропущенные пакеты |

**Nemesida WAF:**
| Ключ Zabbix | Метрика | Описание |
|-------------|---------|----------|
| `nemesida.requests.total` | Total Requests | Всего запросов |
| `nemesida.requests.blocked` | Blocked Requests | Заблокировано |
| `nemesida.attacks.sqli` | SQL Injection | Атаки SQLi |
| `nemesida.attacks.xss` | XSS Attacks | Атаки XSS |
| `nemesida.attacks.rce` | RCE Attacks | Атаки RCE |
| `nemesida.latency.avg` | Average Latency | Средняя задержка |

### Реализация

```python
from app.integrations.zabbix import ZabbixMetricsCollector

collector = ZabbixMetricsCollector(
    zabbix_url="http://zabbix.local/zabbix",
    user="Admin",
    password="zabbix"
)

await collector.initialize(
    pfsense_host="pfsense-main",
    waf_host="nemesida-waf"
)

# Сбор всех метрик
metrics = await collector.collect_all_metrics()
# Returns: {
#     timestamp: "2024-01-15T12:00:00Z",
#     pfsense: {cpu_utilization: 45.2, memory_utilization: 62.1, ...},
#     waf: {total_requests: 15000, blocked_requests: 234, ...},
#     network: {in_bps: 125000000, out_bps: 98000000, ...}
# }

# Корреляция нагрузки с атаками
correlation = await collector.get_protection_load_correlation()
# Returns: {
#     infrastructure_load: {pfsense_cpu: 45.2, waf_cpu: 38.5, ...},
#     protection_stats: {total_blocked: 234, block_rate: 1.56%},
#     attack_breakdown: {sql_injection: 89, xss: 45, rce: 12}
# }
```

---

## Корреляционный анализ

### Сигнатуры атак

| Тип атаки | Признаки | Пороги |
|-----------|----------|--------|
| **SYN Flood** | request_rate_spike, low connection_ratio, high source_diversity | spike > 5x, ratio < 0.1 |
| **HTTP Flood** | request_rate_spike, response_time_increase, error_rate_increase | spike > 3x, latency > 2x |
| **Slowloris** | connection_duration_increase, incomplete_requests, low_bandwidth | duration > 10x, incomplete > 80% |
| **Amplification** | response_to_request_ratio, UDP spike, specific ports | ratio > 10x, UDP > 5x |
| **Application Layer** | endpoint_targeting, malformed_requests, session_anomaly | targeting > 90%, malformed > 60% |

### Корреляция событий

Анализ связи между событиями разных уровней защиты:

```python
from app.analysis.correlation import CorrelationAnalyzer

analyzer = CorrelationAnalyzer()

# Добавление событий
analyzer.add_event({"source": "waf", "type": "block", "attack": "sqli"})
analyzer.add_event({"source": "firewall", "type": "rate_limit", "ip": "1.2.3.4"})

# Расчёт корреляции
correlation = analyzer.correlate_events(events)
# Returns: {
#     correlations: [
#         {source1: "waf", source2: "firewall", correlation: 0.85, p_value: 0.001}
#     ],
#     event_counts_by_source: {waf: 150, firewall: 89, ids: 45}
# }

# Детекция начала атаки
attack_start = analyzer.detect_attack_start(time_series)
# Returns: {
#     attack_start_time: "2024-01-15T12:05:23Z",
#     baseline_value: 100,
#     spike_value: 850,
#     z_score: 7.5,
#     confidence: 0.99
# }

# Классификация атаки
classification = analyzer.classify_unknown_attack(features)
# Returns: {
#     classification: "http_flood",
#     confidence: 0.87,
#     alternative_matches: [("syn_flood", 0.45), ("slowloris", 0.32)]
# }
```

---

## Реалистичные DDoS-сценарии

### Генерация ботнета

```python
from app.attacks.realistic import RealisticDDoSGenerator

generator = RealisticDDoSGenerator()

# Создание ботнета с географическим распределением
botnet = generator.generate_botnet(
    size=10000,
    geo_distribution={
        "US": 0.25,   # 25% из США
        "CN": 0.20,   # 20% из Китая
        "RU": 0.15,   # 15% из России
        "BR": 0.10,   # 10% из Бразилии
        "IN": 0.10,   # 10% из Индии
        "DE": 0.05,   # 5% из Германии
        "FR": 0.05,   # 5% из Франции
        "OTHER": 0.10 # 10% прочие
    }
)
```

### Типы атак

**SYN Flood:**
```python
packet = generator.generate_syn_flood_packet()
# Returns: {
#     type: "syn_flood",
#     source_ip: "45.123.67.89",  # Spoofed
#     tcp_flags: {SYN: True, ACK: False},
#     window_size: 29200,
#     packet_size: 44,
#     ttl: 64
# }
```

**UDP Flood:**
```python
packet = generator.generate_udp_flood_packet()
# Returns: {
#     type: "udp_flood",
#     source_ip: "89.234.12.45",
#     dest_port: 53,  # DNS
#     packet_size: 1024,
#     payload: "X" * 1024
# }
```

**DNS Amplification:**
```python
request = generator.generate_dns_amplification_request()
# Returns: {
#     type: "dns_amplification",
#     dns_server: "8.8.8.8",
#     query_type: "ANY",
#     request_size: 60,
#     response_size: 2160,  # 36x amplification
#     amplification_factor: 36
# }
```

**NTP Amplification:**
```python
request = generator.generate_ntp_amplification_request()
# Returns: {
#     type: "ntp_amplification",
#     command: "monlist",
#     request_size: 8,
#     response_size: 2400,  # 300x amplification
#     amplification_factor: 300
# }
```

### Потоковая генерация

```python
async for packet in generator.generate_realistic_attack_stream(
    attack_type="syn_flood",
    duration_seconds=300,
    intensity_pps=10000
):
    # Каждый пакет содержит:
    # - Реалистичный source IP из ботнета
    # - Географическую информацию
    # - Характеристики, соответствующие реальным атакам
    await send_packet(packet)
```

---

## Хранение данных

### Схема PostgreSQL

```sql
-- Сессии тестирования
CREATE TABLE test_sessions (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255),
    attack_type VARCHAR(50),
    config JSONB,
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',
    total_requests INTEGER DEFAULT 0,
    requests_sent INTEGER DEFAULT 0,
    requests_received INTEGER DEFAULT 0,
    requests_blocked INTEGER DEFAULT 0,
    summary_json JSONB
);

-- Per-packet события
CREATE TABLE traffic_events (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50) REFERENCES test_sessions(session_id),
    request_id VARCHAR(50) UNIQUE NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    source_ip VARCHAR(45),
    dest_ip VARCHAR(45),
    source_port INTEGER,
    dest_port INTEGER,
    protocol VARCHAR(10),
    packet_size INTEGER,
    response_time_ms FLOAT,
    status_code INTEGER,
    was_blocked BOOLEAN DEFAULT FALSE,
    blocked_by VARCHAR(50),
    attack_type VARCHAR(50),
    is_malicious BOOLEAN DEFAULT FALSE,
    payload_hash VARCHAR(64),
    headers_json JSONB,
    geo_location VARCHAR(10)
);

-- Индексы для быстрого поиска
CREATE INDEX idx_session_timestamp ON traffic_events(session_id, timestamp);
CREATE INDEX idx_blocked ON traffic_events(was_blocked, blocked_by);
CREATE INDEX idx_attack_type ON traffic_events(attack_type, is_malicious);

-- Агрегированные метрики по интервалам
CREATE TABLE interval_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50) REFERENCES test_sessions(session_id),
    interval_start TIMESTAMP NOT NULL,
    interval_seconds INTEGER DEFAULT 1,
    requests_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    malicious_count INTEGER DEFAULT 0,
    avg_latency_ms FLOAT,
    p50_latency_ms FLOAT,
    p95_latency_ms FLOAT,
    p99_latency_ms FLOAT,
    throughput_rps FLOAT,
    bytes_sent BIGINT DEFAULT 0,
    unique_sources INTEGER DEFAULT 0
);

-- Статистические модели
CREATE TABLE statistical_models (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50),
    model_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    parameters_json JSONB,
    lambda_intensity FLOAT,
    variance FLOAT,
    mean_value FLOAT,
    std_dev FLOAT,
    confidence_interval_lower FLOAT,
    confidence_interval_upper FLOAT,
    anomaly_threshold FLOAT,
    distribution_type VARCHAR(30)
);

-- Нарушения SLA
CREATE TABLE sla_violations (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50),
    metric_name VARCHAR(50),
    violation_start TIMESTAMP NOT NULL,
    violation_end TIMESTAMP,
    target_value FLOAT,
    actual_value FLOAT,
    severity VARCHAR(20),
    duration_seconds FLOAT,
    cost_impact FLOAT
);

-- Обнаруженные паттерны атак
CREATE TABLE attack_patterns (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(50),
    detected_at TIMESTAMP DEFAULT NOW(),
    attack_type VARCHAR(50),
    confidence FLOAT,
    signature_matched VARCHAR(100),
    features_json JSONB,
    source_ips JSONB,
    duration_seconds FLOAT,
    peak_intensity_rps FLOAT
);
```

### Экспорт для анализа

```python
from app.storage.database import DatabaseManager

db = DatabaseManager(database_url)

# Экспорт данных сессии
data = await db.export_for_analysis(session_id, format="dict")
# Returns: {
#     session_id: "...",
#     events: [...],  # Per-packet данные
#     interval_metrics: [...],  # Агрегированные метрики
#     aggregated_stats: {...}  # Общая статистика
# }

# Для анализа в Pandas
import pandas as pd
events_df = pd.DataFrame(data["events"])
metrics_df = pd.DataFrame(data["interval_metrics"])
```

---

## Установка и настройка

### Требования

- Python 3.10+
- PostgreSQL 14+
- Zabbix 6.0+ (опционально)
- pfSense 2.6+ с Nemesida WAF

### Установка

```bash
# Клонирование репозитория
git clone https://github.com/meloch287/Web-service.git
cd Web-service

# Установка зависимостей
pip install -r requirements.txt

# Настройка окружения
cp .env.example .env
```

### Конфигурация .env

```bash
# База данных
DB_USER=vtsk
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=security_test_db

# Sender (атакующая машина)
SENDER_HOST=0.0.0.0
SENDER_PORT=5000

# Receiver (защищаемая машина)
RECEIVER_HOST=0.0.0.0
RECEIVER_PORT=5001
RECEIVER_URL=http://192.168.20.2:5001
SENDER_CALLBACK_URL=http://192.168.10.2:5000

# Zabbix интеграция
ZABBIX_URL=http://zabbix.local/zabbix
ZABBIX_USER=Admin
ZABBIX_PASSWORD=zabbix
PFSENSE_HOST_NAME=pfsense-main
WAF_HOST_NAME=nemesida-waf

# SLA параметры
SLA_AVAILABILITY_TARGET=99.9
SLA_LATENCY_P95_TARGET=200.0
SLA_LATENCY_P99_TARGET=500.0
SLA_THROUGHPUT_TARGET=1000.0

# Статистический анализ
STATISTICAL_CONFIDENCE_LEVEL=0.95
ANOMALY_DETECTION_WINDOW=100
BASELINE_COLLECTION_PERIOD=300
```

### Инициализация базы данных

```bash
# Создание базы данных
psql -U postgres -c "CREATE DATABASE security_test_db;"

# Инициализация схемы (автоматически при первом запуске)
python -c "import asyncio; from app.storage.database import DatabaseManager; asyncio.run(DatabaseManager('postgresql+asyncpg://...').init_db())"
```

---

## API Reference

### Sender API (port 5000)

#### POST /start
Запуск тестовой сессии.

**Параметры:**
| Параметр | Тип | Default | Описание |
|----------|-----|---------|----------|
| mode | string | "normal" | Режим: normal, flood, burst, slowloris, gradual, mixed |
| total_requests | int | 1000 | Общее количество запросов |
| requests_per_second | int | 100 | Целевой RPS |
| malicious_ratio | float | 0.1 | Доля вредоносных запросов (0-1) |
| payload_size | int | 1024 | Размер payload в байтах |
| burst_size | int | 50 | Размер пачки для burst режима |
| attack_types | string | "sql_injection,xss" | Типы атак через запятую |

**Пример:**
```bash
curl -X POST "http://192.168.10.2:5000/start?mode=flood&total_requests=10000&malicious_ratio=0.2&attack_types=sql_injection,xss,path_traversal"
```

**Ответ:**
```json
{
    "session_id": "SESSION-20240115120000-abc123",
    "status": "started",
    "config": {
        "mode": "flood",
        "total_requests": 10000,
        "malicious_ratio": 0.2,
        "attack_types": ["sql_injection", "xss", "path_traversal"]
    },
    "timestamp": "2024-01-15T12:00:00Z"
}
```

#### GET /status/{session_id}
Получение статуса сессии с метриками.

**Ответ:**
```json
{
    "session_id": "SESSION-20240115120000-abc123",
    "status": "running",
    "started_at": "2024-01-15T12:00:00Z",
    "summary": {
        "duration_seconds": 45.2,
        "total_sent": 5000,
        "total_received": 4850,
        "total_blocked": 423,
        "block_rate": 8.72,
        "throughput_rps": 110.6,
        "latency": {
            "avg_ms": 23.4,
            "p50_ms": 18.2,
            "p95_ms": 67.8,
            "p99_ms": 145.3
        }
    },
    "protection_effectiveness": {
        "malicious_sent": 1000,
        "malicious_blocked": 892,
        "detection_rate_percent": 89.2,
        "false_positive_rate_percent": 2.1
    }
}
```

#### GET /report/{session_id}
Полный отчёт с SLA-анализом и рекомендациями.

**Ответ:**
```json
{
    "session_id": "SESSION-20240115120000-abc123",
    "name": "Test flood",
    "attack_type": "flood",
    "duration_seconds": 120.5,
    "summary": {...},
    "protection": {...},
    "sla_report": {
        "overall_compliance_percent": 94.5,
        "availability": {"value": 99.2, "target": 99.9, "status": "warning"},
        "latency": {...},
        "violations_count": 2,
        "total_cost_impact": 150.0
    },
    "statistical_model": {
        "lambda_intensity": 110.5,
        "variance": 125.3,
        "distribution": "poisson",
        "anomaly_threshold": 245.8
    },
    "recommendations": [
        "Detection rate is below 80%. Consider tuning WAF rules.",
        "108 malicious requests passed through. Update signatures."
    ]
}
```

#### GET /timeline/{session_id}
Timeline метрик по интервалам.

#### GET /sessions
Список всех сессий.

#### POST /stop/{session_id}
Остановка сессии.

---

### Receiver API (port 5001)

#### POST /receive
Приём трафика.

**Body:**
```json
{
    "batch_id": "BATCH-123",
    "session_id": "SESSION-123",
    "requests": [
        {
            "request_id": "REQ-001",
            "timestamp": "2024-01-15T12:00:00Z",
            "payload": {...},
            "headers": {...},
            "is_malicious": false,
            "attack_type": "normal"
        }
    ]
}
```

**Ответ:**
```json
{
    "batch_id": "BATCH-123",
    "total_requests": 10,
    "received_count": 10,
    "blocked_count": 2,
    "results": [
        {
            "request_id": "REQ-001",
            "received": true,
            "response_time_ms": 12.5,
            "was_blocked": false,
            "status_code": 200
        }
    ]
}
```

#### GET /stats/{session_id}
Статистика защиты.

#### GET /events/{session_id}
События блокировки.

---

## Примеры использования

### Базовый тест

```bash
# Запуск receiver на защищаемой машине
python run_receiver.py

# Запуск sender на атакующей машине
python run_sender.py

# Запуск теста через CLI
python run_simulation.py normal 1000 100 0.1 "sql_injection,xss"
```

### DDoS Flood тест

```bash
python run_simulation.py flood 50000 0 0.3 "sql_injection,xss,path_traversal,cmd_injection"
```

### Burst-атака

```bash
python run_simulation.py burst 10000 500 0.2 "sql_injection,xss"
```

### Slowloris

```bash
python run_simulation.py slowloris 1000 10 0.0 ""
```

### Программный запуск

```python
import asyncio
from app.main import run_test

asyncio.run(run_test(
    mode="flood",
    total_requests=10000,
    requests_per_second=0,  # Максимальная скорость
    malicious_ratio=0.25,
    attack_types="sql_injection,xss,path_traversal"
))
```

### Полный анализ с Zabbix

```python
import asyncio
from app.integrations.zabbix import ZabbixMetricsCollector
from app.analysis.statistical import StatisticalAnalyzer
from app.analysis.sla import SLAAnalyzer
from app.analysis.correlation import CorrelationAnalyzer

async def full_analysis():
    # Инициализация
    zabbix = ZabbixMetricsCollector(url, user, password)
    await zabbix.initialize("pfsense", "nemesida-waf")
    
    stats = StatisticalAnalyzer()
    sla = SLAAnalyzer()
    corr = CorrelationAnalyzer()
    
    # Сбор метрик во время теста
    while test_running:
        metrics = await zabbix.collect_all_metrics()
        
        # Статистический анализ
        model = stats.build_traffic_model(timestamps, values)
        anomaly = stats.detect_anomaly(current_values)
        
        # SLA анализ
        sla_report = sla.generate_sla_report(metrics)
        
        # Корреляция
        attack_info = corr.analyze_combined_attack(events, metrics)
        
        await asyncio.sleep(1)
    
    # Финальный отчёт
    return {
        "statistical_model": model,
        "sla_compliance": sla_report,
        "attack_analysis": attack_info
    }
```

---

## Структура проекта

```
Web-service/
├── app/
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── statistical.py    # Статистические модели, Марковские цепи
│   │   ├── sla.py            # SLA-анализ, деградация качества
│   │   └── correlation.py    # Корреляция событий, сигнатуры атак
│   ├── attacks/
│   │   ├── __init__.py
│   │   ├── patterns.py       # Паттерны веб-атак (SQLi, XSS, etc.)
│   │   ├── generator.py      # Генератор трафика
│   │   └── realistic.py      # Реалистичные DDoS-сценарии
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── zabbix.py         # Интеграция с Zabbix
│   ├── services/
│   │   ├── __init__.py
│   │   └── metrics.py        # Сбор и агрегация метрик
│   ├── storage/
│   │   ├── __init__.py
│   │   └── database.py       # PostgreSQL схема и операции
│   ├── __init__.py
│   ├── config.py             # Конфигурация
│   ├── database.py           # Базовое подключение к БД
│   ├── models.py             # SQLAlchemy модели
│   ├── schemas.py            # Pydantic схемы
│   ├── sender.py             # Sender FastAPI приложение
│   ├── receiver.py           # Receiver FastAPI приложение
│   └── main.py               # CLI runner
├── run_sender.py             # Запуск Sender
├── run_receiver.py           # Запуск Receiver
├── run_simulation.py         # Запуск симуляции
├── run_bank_simulation.py    # Симуляция банковских транзакций
├── setup_db.py               # Инициализация БД
├── requirements.txt          # Зависимости
├── .env.example              # Пример конфигурации
├── reports/                  # Графики результатов
└── README.md                 # Документация
```

---

## Симуляция банковских транзакций

### Описание

Модуль `run_bank_simulation.py` генерирует реалистичный поток банковских транзакций с аномалиями, используя математические модели распределений.

### Запуск

```bash
# Запустить receiver
python run_receiver.py

# В другом терминале — симуляция
python run_bank_simulation.py --users 100 --transactions 1000 --rps 50
```

### Параметры

| Параметр | Default | Описание |
|----------|---------|----------|
| --users | 100 | Количество пользователей |
| --transactions | 30000 | Количество транзакций |
| --rps | 100 | Requests per second |
| --target | http://127.0.0.1:5001/receive | URL receiver |

### Математические модели распределений

| Распределение | Применение | Формула |
|---------------|------------|---------|
| **Нормальное** | Легитимный трафик (пик 12:00-14:00) | f(x) = (1/σ√2π) × e^(-(x-μ)²/2σ²) |
| **Пуассоновское** | Случайные атаки (равномерно по времени) | P(k) = λ^k × e^(-λ) / k! |
| **Парето** | Кластеризация атак (80/20 правило) | f(x) = αx_m^α / x^(α+1) |
| **Экспоненциальное** | Затухающие атаки (больше в начале) | f(x) = λ × e^(-λx) |

### Коды аномалий (для БД)

| Код | Тип аномалии | Описание |
|-----|--------------|----------|
| 0 | NORMAL | Легитимная транзакция |
| 1 | SQL_INJECTION | SQL-инъекция |
| 2 | XSS | XSS-атака |
| 3 | FRAUD_VELOCITY | Частотная аномалия (много мелких транзакций) |
| 4 | FRAUD_AMOUNT | Аномалия суммы (необычно большая сумма) |
| 5 | FRAUD_GEO | Гео-аномалия (транзакция из необычной локации) |
| 6 | FRAUD_TIME | Временная аномалия |
| 7 | DDOS | DDoS-атака |
| 8 | BRUTE_FORCE | Брутфорс |

### Визуализация

Графики автоматически сохраняются в `reports/simulation_*.png`:

1. **Распределение транзакций за 24 часа** — stacked bar chart с 4 моделями:
   - 🟢 Легитимные (нормальное распределение)
   - 🔴 Аномалии Пуассона
   - 🟣 Аномалии Парето
   - 🟠 Аномалии экспоненциального распределения

2. **Детекция по типам аномалий** — сравнение sent vs blocked

3. **Ключевые метрики эффективности** — detection rate, false positive, throughput

4. **Распределение времени отклика** — гистограмма latency с P50/P95/P99

5. **Математические модели распределений** — теоретические кривые

6. **Детекция с кодами для БД** — horizontal bar chart с кодами аномалий

### Пример вывода

```
======================================================================
BANK TRANSACTION SIMULATION
======================================================================
Session: BANK-20251203010000
Target: http://127.0.0.1:5001/receive
Users: 100
Transactions: 1000
RPS: 50
======================================================================

--- Transaction Stats ---
Total sent: 1000
Total received: 1000
Total blocked: 54
Block rate: 5.4%

--- Attack Detection ---
Malicious sent: 150
Malicious blocked: 54
Detection rate: 36.0%
False positive rate: 0.0%

--- By Attack Type ---
sql_injection: sent=20, blocked=20 (100.0%)
xss: sent=34, blocked=34 (100.0%)
fraud_velocity: sent=34, blocked=0 (0.0%)
fraud_amount_anomaly: sent=27, blocked=0 (0.0%)
fraud_geo_anomaly: sent=35, blocked=0 (0.0%)
normal: sent=850, blocked=0 (0.0%)
```

---

## Лицензия

MIT License

## Авторы

meloch287
