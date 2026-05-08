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

# Файл .env
BOT_TOKEN=your_telegram_bot_token

WG_API_URL=http://localhost:10086/api
WG_API_KEY=your_wgdashboard_api_key

WG_ENDPOINT_DE=your-server:51804
WG_ENDPOINT_EN=your-server:51805
WG_ENDPOINT_NL=your-server:51806

WG_DNS=9.9.9.9,1.1.1.1
TRIAL_DAYS=5

# Запуск
python src/bot.py
