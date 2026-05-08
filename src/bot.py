#!/usr/bin/env python3
import asyncio
import os
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from config import Config
from database import Database, TrialStatus
from wg_manager import WireGuardManager
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()
wg_manager = WireGuardManager()
user_selections = {}

def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="🎁 Попробовать 5 дней")],
        [KeyboardButton(text="💰 Оформить подписку")],
        [KeyboardButton(text="📋 Мои подписки")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие 👇"
    )
    return keyboard


def calculate_price(devices: int, months: int) -> int:
    """Расчёт цены подписки"""
    base_price = 99  # цена за 1 устройство на 1 месяц
    
    # Скидка за количество устройств (от 5% до 30%)
    device_discount = min((devices - 1) * 0.05, 0.3)
    
    # Скидка за срок
    term_discount = {
        1: 0, 2: 0.05, 3: 0.10, 4: 0.12, 5: 0.14, 6: 0.15,
        7: 0.16, 8: 0.17, 9: 0.18, 10: 0.19, 11: 0.20, 12: 0.25
    }.get(months, 0)
    
    price = base_price * devices * months * (1 - device_discount) * (1 - term_discount)
    return int(price)

def get_devices_keyboard():
    """Клавиатура выбора количества устройств (1-10)"""
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"devices_{i}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_months_keyboard(devices: int):
    """Клавиатура выбора срока (1-12 месяцев)"""
    buttons = []
    row = []
    for i in range(1, 13):
        price = calculate_price(devices, i)
        button_text = f"{i} мес. - {price}₽"
        row.append(InlineKeyboardButton(text=button_text, callback_data=f"months_{devices}_{i}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_devices")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_keyboard(devices: int, months: int, price: float):
    """Клавиатура подтверждения оплаты"""
    keyboard = [
        [InlineKeyboardButton(text=f"💳 Оплатить {price}₽", callback_data=f"pay_{devices}_{months}_{price}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_months")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_devices_list_keyboard(devices_count: int, subscription_id: int):
    """Клавиатура для выбора устройства и получения конфига"""
    buttons = []
    for i in range(1, devices_count + 1):
        # Простой формат: get_config_{subscription_id}_{i}
        callback_data = f"get_config_{subscription_id}_{i}"
        logger.info(f"Создана кнопка: {callback_data}")
        buttons.append([InlineKeyboardButton(text=f"📱 Устройство {i}", callback_data=callback_data)])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    
    # Регистрируем пользователя
    db.register_user(
        user_id=user.id,
    )
    
    # Получаем статус пробного периода
    trial_info = db.get_trial_status(user.id)
    
    # Приветственное сообщение с учётом статуса
    welcome_text = f"Привет, {user.first_name}! 👋\n\n"
    welcome_text += "Я бот для выдачи VPN.\n\n"
    
    if trial_info['status'].value == TrialStatus.NOT_ACTIVATED.value:
        welcome_text += "🎁 У вас есть возможность получить 5 дней бесплатно!\n"
        welcome_text += "Нажмите кнопку 'Попробовать 5 дней' ниже."
    
    elif trial_info['status'].value == TrialStatus.ACTIVE.value:
        welcome_text += f"✅ У вас активен пробный период!\n"
        welcome_text += f"📅 Осталось дней: {trial_info['days_left']}\n"
        welcome_text += f"📅 Действует до: {trial_info['expires_at'][:10]}\n\n"
        welcome_text += "Наслаждайтесь быстрым и безопасным интернетом! 🚀"
    
    else:  # EXPIRED
        welcome_text += "⏰ Ваш пробный период закончился.\n"
        welcome_text += "Скоро будут доступны платные подписки! 🔜"
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🎁 Попробовать 5 дней")
async def trial_button(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    # Проверяем статус пробного периода
    trial_info = db.get_trial_status(user_id)
    
    if trial_info['status'].value == TrialStatus.NOT_ACTIVATED.value:
        status_msg = await message.answer(
            "🎁 Оформляем пробный период...\n\n"
            "⏳ Создаю конфигурации для 3 регионов:\n"
            "• 🇩🇪 Германия\n"
            "• 🇬🇧 Англия\n"
            "• 🇳🇱 Нидерланды\n\n"
            "Пожалуйста, подождите..."
        )
        
        # Проверяем подключение к API
        if not wg_manager.test_connection():
            await status_msg.edit_text("❌ Ошибка подключения к VPN серверу\nПожалуйста, попробуйте позже.")
            return
        
        # Создаём конфиги для пробного периода
        configs = wg_manager.create_all_regions_configs(user_id=user_id, days_valid=Config.TRIAL_DAYS, is_trial=True, device_number=None)
        
        if not configs or len(configs) == 0:
            await status_msg.edit_text("❌ Не удалось создать конфигурации\nПожалуйста, попробуйте позже.")
            return
        
        # Сохраняем конфигурации в БД
        for region_code, config_data in configs.items():
            db.save_config(
                user_id=user_id,
                subscription_id=0,  # триал
                device_number=0,     # номер устройства 0
                config_id=config_data['config_id'],
                config_name=config_data['config_name'],
                region=region_code,
                expires_at=config_data['expires_at']
            )
        
        # Активируем пробный период в БД
        expires_at = datetime.now() + timedelta(days=Config.TRIAL_DAYS)
        db.activate_trial(user_id, Config.TRIAL_DAYS)
        
        # Создаём ZIP архив
        zip_data = wg_manager.create_zip_archive(configs)
        
        # Получаем дату окончания
        expiry_date = (datetime.now() + timedelta(days=Config.TRIAL_DAYS)).strftime('%d.%m.%Y')
        
        # Удаляем сообщение о статусе
        await status_msg.delete()
        
        # Отправляем ZIP файл
        await message.reply_document(
            document=BufferedInputFile(zip_data, filename=f"wireguard_{user_name}_trial.zip"),
            caption=(
                f"✅ Пробный период активирован, {user_name}!\n\n"
                f"📅 Действует до: {expiry_date}\n"
                f"🌍 Доступные регионы: Германия, Англия, Нидерланды\n\n"
                f"📱 Конфигурации для всех устройств: 1 (пробный)\n\n"
                f"Приятного использования! 🚀"
            )
        )
        
        await message.answer(
            "📖 Получить конфигурации можно в разделе «Мои подписки»",
            reply_markup=get_main_keyboard()
        )
    
    elif trial_info['status'].value == TrialStatus.ACTIVE.value:
        days_left = trial_info['days_left']
        await message.answer(
            f"❌ У вас уже активирован пробный период!\n\n"
            f"📅 Осталось дней: {days_left}\n"
            f"Пробный период предоставляется только один раз."
        )
    else:
        await message.answer(
            "❌ Ваш пробный период уже закончился.\n\n"
            "Пробный период предоставляется только один раз.\n"
            "Скоро появятся платные подписки!"
        )

@dp.message(lambda message: message.text == "📋 Мои подписки")
async def subscriptions_button(message: types.Message):
    user_id = message.from_user.id
    trial_info = db.get_trial_status(user_id)
    

    if trial_info['status'].value == TrialStatus.NOT_ACTIVATED.value:
        await message.answer(
            "📋 У вас нет активных подписок\n\n"
            "🎁 Нажмите 'Попробовать 5 дней', чтобы получить бесплатный доступ!"
        )
    
    elif trial_info['status'].value == TrialStatus.ACTIVE.value:
        expires_at = trial_info.get('expires_at', '')
        await message.answer(
            f"📋 Ваши подписки:\n\n"
            f"🎁 Пробный период (активен)\n"
            f"📅 Действует до: {expires_at[:10] if expires_at else 'неизвестно'}\n"
            f"📊 Осталось дней: {trial_info['days_left']}\n\n"
            f"✅ Статус: АКТИВЕН"
        )
    
    else:  # EXPIRED
        await message.answer(
            f"📋 Ваши подписки:\n\n"
            f"🎁 Пробный период (закончился)\n"
            f"📊 Статус: НЕАКТИВЕН\n\n"
            f"⏰ Для получения доступа ожидайте запуска платных подписок."
        )

@dp.message(lambda message: message.text == "❓ Помощь")
async def help_button(message: types.Message):
    await message.answer(
        "❓ Помощь\n\n"
        "Как пользоваться ботом:\n"
        "1. Нажми 'Попробовать 5 дней'\n"
        "2. Получи пробный доступ\n"
        "3. Дождись конфигураций (скоро)\n"
        "4. Импортируй в WireGuard\n\n"
        "📋 Команды:\n"
        "/start - Главное меню\n"
        "/status - Проверить статус\n\n"
        "По вопросам: @"
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Отдельная команда для проверки статуса"""
    user_id = message.from_user.id
    trial_info = db.get_trial_status(user_id)
    user_info = db.get_user_info(user_id)
    
    status_text = f"📊 Статус пользователя:\n\n"
    status_text += f"🆔 ID: {user_id}\n"
    
    if user_info:
        status_text += f"📅 Зарегистрирован: {user_info['created_at'][:19]}\n"
    
    if trial_info['status'].value == TrialStatus.NOT_ACTIVATED.value:
        status_text += f"🎁 Пробный период: Не активирован"
    elif trial_info['status'].value == TrialStatus.ACTIVE.value:
        status_text += f"🎁 Пробный период: АКТИВЕН\n"
        status_text += f"📅 Осталось дней: {trial_info['days_left']}"
    else:
        status_text += f"🎁 Пробный период: ЗАКОНЧИЛСЯ"
    
    await message.answer(status_text)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика бота (только для админа)"""
    # Проверка на админа (добавь свои ID)
    ADMIN_IDS = [123456789]  # Замени на свой Telegram ID
    
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас нет доступа к этой команде")
        return
    
    stats = db.get_stats()
    
    stats_text = f"📊 Статистика бота:\n\n"
    stats_text += f"👥 Всего пользователей: {stats['total']}\n"
    stats_text += f"🎁 Не активировали пробный: {stats['not_activated']}\n"
    stats_text += f"✅ Активные подписки: {stats['active']}\n"
    stats_text += f"⏰ Закончился период: {stats['expired']}\n"
    
    await message.answer(stats_text)

@dp.message()
async def echo_all(message: types.Message):
    # Игнорируем команды и кнопки
    if message.text.startswith('/'):
        return
    if message.text in ["🎁 Попробовать 5 дней", "📋 Мои подписки", "❓ Помощь"]:
        return
    
    await message.answer(
        f"Я не понимаю эту команду.\n\n"
        f"Используй /start для главного меню"
    )

@dp.message(lambda message: message.text == "💰 Оформить подписку")
async def new_subscription(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, есть ли уже активная подписка
    subscription = db.get_active_subscription(user_id)
    if subscription:
        end_date = datetime.strptime(subscription['end_date'], '%Y-%m-%d %H:%M:%S.%f')
        await message.answer(
            f"❌ У вас уже есть активная подписка!\n\n"
            f"📱 Устройств: {subscription['devices']}\n"
            f"📅 Действует до: {end_date.strftime('%d.%m.%Y')}\n\n"
            f"Всю информацию можно получить в разделе «Мои подписки»"
        )
        return
    
    await message.answer(
        "💰 Конструктор подписки\n\n"
        "👇 Выберите количество устройств:",
        reply_markup=get_devices_keyboard()
    )

@dp.message(lambda message: message.text == "📋 Мои подписки")
async def my_subscriptions(message: types.Message):
    user_id = message.from_user.id
    
    subscription = db.get_active_subscription(user_id)
    if not subscription:
        await message.answer(
            "📋 У вас нет активных подписок\n\n"
            "💰 Нажмите «Оформить подписку»",
            reply_markup=get_main_keyboard()
        )
        return
    
    end_date = datetime.strptime(subscription['end_date'], '%Y-%m-%d %H:%M:%S.%f')
    days_left = (end_date - datetime.now()).days
    devices_count = subscription['devices']
    
    info_text = (
        f"📋 Ваша подписка\n\n"
        f"📱 Устройств: {devices_count}\n"
        f"📅 Действует до: {end_date.strftime('%d.%m.%Y')}\n"
        f"📊 Осталось дней: {days_left}\n"
        f"✅ Статус: АКТИВНА\n\n"
        f"👇 Нажмите на устройство, чтобы получить конфигурацию:"
    )
    
    await message.answer(
        info_text,
        reply_markup=get_devices_list_keyboard(devices_count, subscription['id'])
    )

@dp.callback_query(lambda c: c.data.startswith("devices_"))
async def select_devices(callback: types.CallbackQuery):
    """Выбор количества устройств"""
    devices = int(callback.data.split("_")[1])
    
    # Сохраняем выбор пользователя
    user_selections[callback.from_user.id] = {'devices': devices}
    
    await callback.message.edit_text(
        f"📱 Выбрано устройств: {devices}\n\n"
        f"👇 Выберите срок подписки:",
        reply_markup=get_months_keyboard(devices)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("months_"))
async def select_months(callback: types.CallbackQuery):
    """Выбор срока подписки"""
    _, devices, months = callback.data.split("_")
    devices = int(devices)
    months = int(months)
    price = calculate_price(devices, months)
    
    await callback.message.edit_text(
        f"✅ Вы выбрали:\n\n"
        f"📱 Устройств: {devices}\n"
        f"📅 Срок: {months} мес.\n"
        f"💰 Цена: {price}₽\n\n"
        f"👇 Нажмите «Оплатить» для оформления подписки",
        reply_markup=get_payment_keyboard(devices, months, price)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pay_"))
async def process_payment(callback: types.CallbackQuery):
    """Обработка оплаты (пока просто оформление подписки)"""
    _, devices, months, price = callback.data.split("_")
    devices = int(devices)
    months = int(months)
    price = float(price)
    user_id = callback.from_user.id
    
    # Создаём подписку в БД
    subscription_id = db.create_subscription(user_id, devices, months, price)
    
    # Для КАЖДОГО устройства создаём свои конфиги
    for device_num in range(1, devices + 1):
        for region_code, region_info in wg_manager.regions.items():
            # Формируем имя: user_123_sub_1_de
            peer_name = f"{user_id}-sub-{device_num}-{region_code}"
            
            expires_at = datetime.now() + timedelta(days=months * 30)
            
            payload = {
                "name": peer_name,
                "public_key": "",
                "private_key": "",
                "allowed_ips": [],
                "endpoint_allowed_ip": "0.0.0.0/0",
                "DNS": wg_manager.dns,
                "mtu": wg_manager.mtu,
                "keepalive": wg_manager.keepalive,
                "preshared_key": "",
                "notes": f"Subscription - Device {device_num} - Valid until {expires_at.strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            try:
                response = requests.post(
                    f"{wg_manager.api_url}/addPeers/{region_info['interface_name']}",
                    headers=wg_manager.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    if result.get('status') == True:
                        peer_data = result.get('data', {})
                        
                        if isinstance(peer_data, list) and len(peer_data) > 0:
                            peer_info = peer_data[0]
                        else:
                            peer_info = peer_data
                        
                        logger.info(f"✅ Created peer {peer_name}")
                        
                        # Получаем конфиг
                        config_text = wg_manager.get_peer_config(
                            region_info['interface_name'],
                            peer_info.get('id'),
                            region_info['endpoint']
                        )
                        
                        if config_text:
                            # Сохраняем конфиг в БД
                            db.save_config(
                                user_id=user_id,
                                subscription_id=subscription_id,
                                device_number=device_num,
                                config_id=peer_info.get('id'),
                                config_name=peer_name,
                                region=region_code
                            )
                        else:
                            logger.error(f"Failed to get config for {peer_name}")
                    else:
                        logger.error(f"API error: {result.get('message')}")
                else:
                    logger.error(f"HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error creating peer {peer_name}: {e}")
    
    await callback.message.edit_text(
        f"✅ Подписка успешно оформлена!\n\n"
        f"📱 Устройств: {devices}\n"
        f"📅 Срок: {months} мес.\n"
        f"💰 Оплачено: {price}₽\n\n"
        f"📋 Получить конфигурации можно в разделе «Мои подписки»"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("get_config_"))
async def get_device_config(callback: types.CallbackQuery):
    """Получение конфига для конкретного устройства"""
    try:
        data_part = callback.data.replace("get_config_", "")
        
        if "-" in data_part:
            parts = data_part.split("-")
        else:
            parts = data_part.split("_")
        
        logger.info(f"Получен callback: {callback.data}, parts: {parts}")
        
        if len(parts) >= 2:
            subscription_id = int(parts[0])
            device_num = int(parts[1])
        else:
            logger.error(f"Неверный формат callback: {callback.data}")
            await callback.message.answer("❌ Ошибка формата запроса")
            await callback.answer()
            return
        
        user_id = callback.from_user.id
        logger.info(f"User {user_id}, subscription {subscription_id}, device {device_num}")
        
        # Получаем подписку
        subscription = db.get_active_subscription(user_id)
        if not subscription or subscription['id'] != subscription_id:
            await callback.message.answer("❌ Подписка не найдена или истекла")
            await callback.answer()
            return
        
        # Получаем конфиги для этого устройства из user_configs
        configs_data = db.get_configs_by_device(user_id, subscription_id, device_num)
        
        if not configs_data:
            await callback.message.answer(f"❌ Конфигурация для устройства {device_num} не найдена")
            await callback.answer()
            return
        
        # Собираем конфиги в формат для ZIP
        configs = {}
        for cfg in configs_data:
            region_info = wg_manager.regions.get(cfg['region'])
            if region_info:
                config_text = wg_manager.get_peer_config(
                    region_info['interface_name'],
                    cfg['config_id'],
                    region_info['endpoint']
                )
                if config_text:
                    configs[cfg['region']] = {
                        'config_text': config_text,
                        'region_name': region_info['name'],
                        'region_flag': region_info['flag']
                    }
        
        if configs:
            zip_data = wg_manager.create_zip_archive(configs)
            end_date = datetime.strptime(subscription['end_date'], '%Y-%m-%d %H:%M:%S.%f')
            await callback.message.reply_document(
                document=BufferedInputFile(zip_data, filename=f"device_{device_num}_configs.zip"),
                caption=f"📱 Конфигурации для устройства {device_num}\n\n📅 Действуют до: {end_date.strftime('%d.%m.%Y')}"
            )
        else:
            await callback.message.answer(f"❌ Не удалось получить конфигурацию для устройства {device_num}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в get_device_config: {e}")
        import traceback
        traceback.print_exc()
        await callback.message.answer("❌ Произошла ошибка при получении конфигурации")
        await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_devices")
async def back_to_devices(callback: types.CallbackQuery):
    """Назад к выбору устройств"""
    await callback.message.edit_text(
        "💰 Конструктор подписки\n\n"
        "👇 Выберите количество устройств:",
        reply_markup=get_devices_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_months")
async def back_to_months(callback: types.CallbackQuery):
    """Назад к выбору срока"""
    user_id = callback.from_user.id
    devices = user_selections.get(user_id, {}).get('devices', 1)
    
    await callback.message.edit_text(
        f"📱 Выбрано устройств: {devices}\n\n"
        f"👇 Выберите срок подписки:",
        reply_markup=get_months_keyboard(devices)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    """Назад в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("devices_"))
async def select_devices(callback: types.CallbackQuery):
    """Выбор количества устройств"""
    devices = int(callback.data.split("_")[1])
    
    # Сохраняем выбор пользователя
    user_selections[callback.from_user.id] = {'devices': devices}
    
    await callback.message.edit_text(
        f"📱 Выбрано устройств: {devices}\n\n"
        f"👇 Выберите срок подписки:",
        reply_markup=get_months_keyboard(devices)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("months_"))
async def select_months(callback: types.CallbackQuery):
    """Выбор срока подписки"""
    _, devices, months = callback.data.split("_")
    devices = int(devices)
    months = int(months)
    price = calculate_price(devices, months)
    
    await callback.message.edit_text(
        f"✅ Вы выбрали:\n\n"
        f"📱 Устройств: {devices}\n"
        f"📅 Срок: {months} мес.\n"
        f"💰 Цена: {price}₽\n\n"
        f"👇 Нажмите «Оплатить» для оформления подписки",
        reply_markup=get_payment_keyboard(devices, months, price)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("pay_"))
@dp.callback_query(lambda c: c.data.startswith("pay_"))
async def process_payment(callback: types.CallbackQuery):
    """Обработка оплаты (пока просто оформление подписки)"""
    _, devices, months, price = callback.data.split("_")
    devices = int(devices)
    months = int(months)
    price = float(price)
    user_id = callback.from_user.id
    
    # Создаём подписку в БД
    subscription_id = db.create_subscription(user_id, devices, months, price)
    
    # Для КАЖДОГО устройства создаём свои конфиги
    for device_num in range(1, devices + 1):
        # Создаём конфиги для ВСЕХ регионов для этого устройства
        configs = wg_manager.create_all_regions_configs(user_id, months * 30, device_num)
        
        # Сохраняем конфиги для этого устройства
        for region_code, config_data in configs.items():
            db.save_config(
                user_id=user_id,
                subscription_id=subscription_id,
                device_number=device_num,
                config_id=config_data['config_id'],
                config_name=config_data['config_name'],
                region=region_code,
                expires_at=config_data['expires_at'])
    
    await callback.message.edit_text(
        f"✅ Подписка успешно оформлена!\n\n"
        f"📱 Устройств: {devices}\n"
        f"📅 Срок: {months} мес.\n"
        f"💰 Оплачено: {price}₽\n\n"
        f"📋 Получить конфигурации можно в разделе «Мои подписки»"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_devices")
async def back_to_devices(callback: types.CallbackQuery):
    """Назад к выбору устройств"""
    await callback.message.edit_text(
        "💰 Конструктор подписки\n\n"
        "👇 Выберите количество устройств:",
        reply_markup=get_devices_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_months")
async def back_to_months(callback: types.CallbackQuery):
    """Назад к выбору срока"""
    user_id = callback.from_user.id
    devices = user_selections.get(user_id, {}).get('devices', 1)
    
    await callback.message.edit_text(
        f"📱 Выбрано устройств: {devices}\n\n"
        f"👇 Выберите срок подписки:",
        reply_markup=get_months_keyboard(devices)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    """Назад в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "🏠 Главное меню",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()



# Обработчик ошибок
async def errors_handler(event: types.ErrorEvent):
    """Глобальный обработчик ошибок"""
    logger.error(f"❌ Ошибка: {event.exception}")
    return True

async def main():
    # Принудительное использование IPv4 через настройки aiogram
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Регистрируем обработчики команд
    dp.message(Command("start"))(cmd_start)
    
    # Регистрируем обработчики кнопок главного меню
    dp.message(lambda m: m.text == "💰 Оформить подписку")(new_subscription)
    dp.message(lambda m: m.text == "📋 Мои подписки")(my_subscriptions)
    dp.message(lambda m: m.text == "🎁 Попробовать 5 дней")(trial_button)
    dp.message(lambda m: m.text == "❓ Помощь")(help_button)
    
    # Регистрируем обработчики инлайн-кнопок конструктора
    dp.callback_query(lambda c: c.data.startswith("devices_"))(select_devices)
    dp.callback_query(lambda c: c.data.startswith("months_"))(select_months)
    dp.callback_query(lambda c: c.data.startswith("pay_"))(process_payment)
    dp.callback_query(lambda c: c.data.startswith("get_config_"))(get_device_config)
    dp.callback_query(lambda c: c.data == "back_to_devices")(back_to_devices)
    dp.callback_query(lambda c: c.data == "back_to_months")(back_to_months)
    dp.callback_query(lambda c: c.data == "back_to_main")(back_to_main)
    
    # Регистрируем обработчик ошибок
    dp.errors()(errors_handler)
    
    print("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())