# 🚀 VPN Telegram Bot

Telegram бот для автоматической выдачи WireGuard VPN конфигураций через WGDashboard.

## 📋 Возможности

- 🎁 Пробный период на 5 дней
- 💰 Платная подписка (конструктор)
  - Выбор количества устройств (1-10)
  - Выбор срока (1-12 месяцев)
- 📦 Отправка ZIP архива с конфигурациями WireGuard
- 🗄️ Хранение подписок и устройств в SQLite

## 🛠 Установка

```bash
# Создай виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установи зависимости
pip install -r requirements.txt