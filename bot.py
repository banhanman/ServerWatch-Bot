import asyncio
import logging
import socket
import time
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import config
import threading

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=config.TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Конфигурация сервера
SERVER_IP = "192.168.1.100"  # Замените на IP вашего сервера
SERVER_PORT = 22  # Порт для проверки (SSH по умолчанию)
CHECK_INTERVAL = 900  # 15 минут в секундах

# Состояние сервера
server_online = True
last_notification_time = 0
notification_cooldown = 3600  # 1 час между уведомлениями

def check_server():
    """Проверяет доступность сервера"""
    try:
        # Создаем сокет с таймаутом 10 секунд
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        # Пытаемся подключиться
        result = sock.connect_ex((SERVER_IP, SERVER_PORT))
        sock.close()
        
        return result == 0
    except Exception as e:
        logger.error(f"Ошибка проверки сервера: {e}")
        return False

async def send_notification(message: str):
    """Отправляет уведомление в Telegram"""
    for chat_id in config.ADMIN_CHAT_IDS:
        try:
            await bot.send_message(chat_id, message)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")

async def server_monitor():
    """Фоновая задача для мониторинга сервера"""
    global server_online, last_notification_time
    
    while True:
        current_status = check_server()
        logger.info(f"Проверка сервера. Статус: {'Online' if current_status else 'Offline'}")
        
        # Если статус изменился на Offline
        if not current_status and server_online:
            server_online = False
            current_time = time.time()
            
            # Проверяем, можно ли отправлять уведомление
            if current_time - last_notification_time > notification_cooldown:
                await send_notification(f"⚠️ Сервер недоступен!\n\n"
                                       f"IP: {SERVER_IP}\n"
                                       f"Порт: {SERVER_PORT}\n"
                                       f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                last_notification_time = current_time
        
        # Если сервер снова онлайн
        elif current_status and not server_online:
            server_online = True
            await send_notification(f"✅ Сервер снова доступен!\n\n"
                                   f"IP: {SERVER_IP}\n"
                                   f"Время восстановления: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Ожидаем перед следующей проверкой
        await asyncio.sleep(CHECK_INTERVAL)

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Проверить сервер", callback_data="check_server"))
    keyboard.add(InlineKeyboardButton("⚙️ Настройки", callback_data="settings"))
    
    await message.answer(
        f"🖥️ Мониторинг сервера {SERVER_IP}\n\n"
        "Я постоянно проверяю доступность вашего сервера и уведомлю вас, если он станет недоступен.\n\n"
        "Текущий статус: " + ("🟢 Online" if server_online else "🔴 Offline"),
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data == 'check_server')
async def manual_check(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    user_id = callback_query.from_user.id
    
    if user_id not in config.ADMIN_CHAT_IDS:
        await bot.send_message(user_id, "❌ У вас нет прав для управления мониторингом.")
        return
    
    await bot.send_message(user_id, "⏳ Проверяю состояние сервера...")
    
    # Выполняем проверку
    is_online = check_server()
    status = "🟢 Online" if is_online else "🔴 Offline"
    last_check = time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Формируем сообщение с подробной информацией
    message = (
        f"🖥️ Результат проверки сервера:\n\n"
        f"• IP: {SERVER_IP}\n"
        f"• Порт: {SERVER_PORT}\n"
        f"• Статус: {status}\n"
        f"• Время проверки: {last_check}\n\n"
    )
    
    # Добавляем сетевую диагностику
    if not is_online:
        message += "🔍 Диагностика:\n"
        try:
            # Попытка пингования
            response = os.system(f"ping -c 1 {SERVER_IP} > /dev/null 2>&1")
            message += f"• Ping: {'Успешно' if response == 0 else 'Неудачно'}\n"
            
            # Проверка маршрута
            message += "• Traceroute: Запущен...\n"
            trace = os.popen(f"traceroute -m 5 {SERVER_IP}").read()
            message += f"<pre>{trace[:500]}</pre>\n\n"  # Ограничиваем вывод
            
        except Exception as e:
            message += f"⚠️ Ошибка диагностики: {str(e)}\n"
    
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔄 Проверить снова", callback_data="check_server"))
    
    await bot.send_message(
        user_id,
        message,
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data == 'settings')
async def show_settings(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    if user_id not in config.ADMIN_CHAT_IDS:
        await bot.answer_callback_query(callback_query.id, "❌ Доступ запрещен")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("✏️ Изменить IP", callback_data="change_ip"),
        InlineKeyboardButton("🔧 Изменить порт", callback_data="change_port"),
        InlineKeyboardButton("⏱ Изменить интервал", callback_data="change_interval"),
        InlineKeyboardButton("👥 Управление админами", callback_data="manage_admins"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    ]
    keyboard.add(*buttons)
    
    await bot.send_message(
        user_id,
        f"⚙️ Настройки мониторинга:\n\n"
        f"• Сервер: {SERVER_IP}\n"
        f"• Порт: {SERVER_PORT}\n"
        f"• Интервал проверки: {CHECK_INTERVAL // 60} минут\n"
        f"• Администраторы: {len(config.ADMIN_CHAT_IDS)}",
        reply_markup=keyboard
    )

async def on_startup(dp):
    """Запуск при старте бота"""
    # Создаем фоновую задачу мониторинга
    asyncio.create_task(server_monitor())
    
    # Отправляем уведомление администраторам
    for chat_id in config.ADMIN_CHAT_IDS:
        try:
            await bot.send_message(
                chat_id,
                f"🟢 Мониторинг сервера запущен!\n\n"
                f"Сервер: {SERVER_IP}:{SERVER_PORT}\n"
                f"Проверка каждые {CHECK_INTERVAL // 60} минут"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки стартового сообщения: {e}")

if __name__ == '__main__':
    # Создаем папку для логов, если нужно
    import os
    os.makedirs('logs', exist_ok=True)
    
    # Запускаем бота
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
