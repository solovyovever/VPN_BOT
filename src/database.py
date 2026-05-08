import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict
from enum import Enum

class TrialStatus(Enum):
    """Статусы пробного периода"""
    NOT_ACTIVATED = "not_activated"       # Не активирован
    ACTIVE = "active"                     # Активирован и действует
    EXPIRED = "expired"                   # Активирован, но закончился

class Database:
    def __init__(self, db_path="e95hw.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Создаём таблицы"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    trial_status TEXT DEFAULT 'not_activated',
                    trial_started_at TIMESTAMP,
                    trial_expires_at TIMESTAMP
                )
            ''')
            
            # Таблица подписок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    devices INTEGER DEFAULT 1,
                    months INTEGER DEFAULT 1,
                    price REAL,
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица конфигов (вместо user_devices)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subscription_id INTEGER,
                    device_number INTEGER,
                    region TEXT,
                    config_id TEXT,
                    config_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            conn.commit()
            print("✅ База данных инициализирована")
    
    def register_user(self, user_id: int):
        """ Регистрируем нового пользователя """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, trial_status)
                VALUES (?, ?)
            ''', (user_id, TrialStatus.NOT_ACTIVATED.value))
            conn.commit()
    
    def activate_trial(self, user_id: int, days: int = 5):
        """ Активируем пробный период """
        now = datetime.now()
        expires_at = now + timedelta(days=days)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET trial_status = ?, 
                    trial_started_at = ?, 
                    trial_expires_at = ?
                WHERE user_id = ?
            ''', (TrialStatus.ACTIVE.value, now, expires_at, user_id))
            conn.commit()
    
    def get_trial_status(self, user_id: int) -> Dict:
        """Получаем статус пробного периода пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT trial_status, trial_started_at, trial_expires_at 
                FROM users 
                WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            
            if not row:
                return {'status': TrialStatus.NOT_ACTIVATED, 'days_left': 0}
            
            status = row[0]
            expires_at = row[2]
            
            # Проверяем, не истёк ли активный период
            if status == TrialStatus.ACTIVE.value and expires_at:
                expires_date = datetime.strptime(expires_at, '%Y-%m-%d %H:%M:%S.%f')
                if datetime.now() > expires_date:
                    # Период истёк, обновляем статус
                    self.update_expired_status(user_id)
                    return {'status': TrialStatus.EXPIRED, 'days_left': 0}
                
                # Вычисляем сколько дней осталось
                days_left = (expires_date - datetime.now()).days
                return {'status': TrialStatus.ACTIVE, 'days_left': days_left, 'expires_at': expires_at}
            
            elif status == TrialStatus.EXPIRED.value:
                return {'status': TrialStatus.EXPIRED, 'days_left': 0}
            
            else:
                return {'status': TrialStatus.NOT_ACTIVATED, 'days_left': 0}
    
    def update_expired_status(self, user_id: int):
        """Обновляем статус на истёкший"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET trial_status = ?
                WHERE user_id = ? AND trial_status = ?
            ''', (TrialStatus.EXPIRED.value, user_id, TrialStatus.ACTIVE.value))
            conn.commit()
    
    def check_and_update_expired(self):
        """Проверяем всех пользователей и обновляем истёкшие подписки"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET trial_status = ?
                WHERE trial_status = ? 
                AND trial_expires_at <= ?
            ''', (TrialStatus.EXPIRED.value, TrialStatus.ACTIVE.value, datetime.now()))
            conn.commit()
    
    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Получаем полную информацию о пользователе"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'created_at': row[1],
                    'trial_status': row[2],
                    'trial_started_at': row[3],
                    'trial_expires_at': row[4]
                }
            return None
    
    def get_stats(self) -> Dict:
        """Получаем статистику по всем пользователям"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Общее количество пользователей
            cursor.execute('SELECT COUNT(*) FROM users')
            total = cursor.fetchone()[0]
            
            # По статусам
            cursor.execute('SELECT trial_status, COUNT(*) FROM users GROUP BY trial_status')
            status_stats = dict(cursor.fetchall())
            
            return {
                'total': total,
                'not_activated': status_stats.get('not_activated', 0),
                'active': status_stats.get('active', 0),
                'expired': status_stats.get('expired', 0)
            }
        
    def save_config(self, user_id: int, region: str, config_id: str, config_name: str, expires_at: datetime):
        """Сохраняем информацию о созданной конфигурации"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Создаём таблицу для конфигов, если её нет
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    region TEXT,
                    config_id TEXT,
                    config_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            cursor.execute('''
                INSERT INTO user_configs (user_id, region, config_id, config_name, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id, region, config_id, config_name, expires_at))
            conn.commit()

    def create_subscription(self, user_id: int, devices: int, months: int, price: float) -> int:
        """Создаём новую подписку"""
        start_date = datetime.now()
        end_date = start_date + timedelta(days=months * 30)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO subscriptions (user_id, devices, months, price, start_date, end_date, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            ''', (user_id, devices, months, price, start_date, end_date))
            conn.commit()
            return cursor.lastrowid

    def get_active_subscription(self, user_id: int):
        """Получаем активную подписку пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscriptions 
                WHERE user_id = ? AND status = 'active' AND end_date > CURRENT_TIMESTAMP
                ORDER BY id DESC LIMIT 1
            ''', (user_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'devices': row[2],
                    'months': row[3],
                    'price': row[4],
                    'start_date': row[5],
                    'end_date': row[6],
                    'status': row[7],
                    'created_at': row[8]
                }
            return None

    def save_config(self, user_id: int, subscription_id: int, device_number: int, config_id: str, config_name: str, region: str, expires_at: datetime):
        """Сохраняем конфиг (и для триала, и для подписки)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_configs (user_id, subscription_id, device_number, region, config_id, config_name, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ''', (user_id, subscription_id, device_number, region, config_id, config_name, expires_at))
            conn.commit()

    def get_configs_by_device(self, user_id: int, subscription_id: int, device_number: int):
        """Получаем конфиги для конкретного устройства"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_configs 
                WHERE user_id = ? AND subscription_id = ? AND device_number = ? AND is_active = 1
            ''', (user_id, subscription_id, device_number))
            
            rows = cursor.fetchall()
            
            configs = []
            for row in rows:
                configs.append({
                    'id': row[0],
                    'user_id': row[1],
                    'subscription_id': row[2],
                    'device_number': row[3],
                    'region': row[4],
                    'config_id': row[5],
                    'config_name': row[6],
                    'created_at': row[7],
                    'expires_at': row[8],
                    'is_active': row[9]
                })
            return configs

    def get_trial_configs(self, user_id: int):
        """Получаем конфиги триала"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM user_configs 
                WHERE user_id = ? AND subscription_id = 0 AND is_active = 1
            ''', (user_id,))
            
            rows = cursor.fetchall()
            
            configs = []
            for row in rows:
                configs.append({
                    'id': row[0],
                    'user_id': row[1],
                    'subscription_id': row[2],
                    'device_number': row[3],
                    'region': row[4],
                    'config_id': row[5],
                    'config_name': row[6],
                    'created_at': row[7],
                    'expires_at': row[8],
                    'is_active': row[9]
                })
            return configs