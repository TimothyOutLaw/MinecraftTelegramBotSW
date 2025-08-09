#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import time
from datetime import datetime
from typing import Dict

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8276621692:AAFiThRGFHypC6y9Rq-Q7roubH4iBZPb9Yk"  # Замените на ваш токен
MINECRAFT_SERVER_HOST = "5.83.140.93"  # IP вашего Minecraft сервера
MINECRAFT_SERVER_PORT = 25575  # RCON порт (опционально)


# Хранилище данных (в реальном проекте лучше использовать базу данных)
class DataStorage:
    def __init__(self, data_file: str = "bot_data.json"):
        self.data_file = data_file
        self.links: Dict[int, str] = {}  # telegram_id -> minecraft_uuid
        self.pending_codes: Dict[str, Dict] = {}  # code -> {telegram_id, expires_at, player_name}
        self.load_data()

    def load_data(self):
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.links = {int(k): v for k, v in data.get('links', {}).items()}
                    self.pending_codes = data.get('pending_codes', {})
                logger.info(f"Загружено {len(self.links)} привязок и {len(self.pending_codes)} кодов")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")

    def save_data(self):
        """Сохранение данных в файл"""
        try:
            data = {
                'links': {str(k): v for k, v in self.links.items()},
                'pending_codes': self.pending_codes
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")

    def cleanup_expired_codes(self):
        """Очистка истекших кодов"""
        current_time = time.time()
        expired_codes = [
            code for code, data in self.pending_codes.items()
            if data.get('expires_at', 0) < current_time
        ]

        for code in expired_codes:
            del self.pending_codes[code]

        if expired_codes:
            logger.info(f"Удалено {len(expired_codes)} истекших кодов")
            self.save_data()


# Инициализация хранилища
storage = DataStorage()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Неизвестно"

    # Очищаем истекшие коды
    storage.cleanup_expired_codes()

    if user_id in storage.links:
        player_name = storage.links[user_id]
        message = f"""👋 **Добро пожаловать, {username}!**

✅ Ваш аккаунт уже привязан к игроку: **{player_name}**

📋 **Доступные команды:**
/help - показать помощь
/status - проверить статус привязки
/unlink - отвязать аккаунт"""
    else:
        message = f"""👋 **Добро пожаловать в бота привязки аккаунтов!**

❌ Ваш Telegram не привязан к игровому аккаунту.

🎮 **Чтобы привязать аккаунт:**
1. Зайдите на сервер Minecraft
2. Получите код привязки (вас кикнет с кодом)
3. Отправьте команду: `/link ВАШ_КОД`

📋 **Доступные команды:**
/help - показать помощь
/status - проверить статус привязки"""

    await update.message.reply_text(message, parse_mode='Markdown')


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /link"""
    user_id = update.effective_user.id
    username = update.effective_user.username or "Неизвестно"

    if not context.args:
        await update.message.reply_text(
            "❌ **Неверный формат команды!**\n\nИспользуйте: `/link ВАШ_КОД`",
            parse_mode='Markdown'
        )
        return

    code = context.args[0].upper()

    # Очищаем истекшие коды
    storage.cleanup_expired_codes()

    # Проверяем не привязан ли уже аккаунт
    if user_id in storage.links:
        player_name = storage.links[user_id]
        await update.message.reply_text(
            f"⚠️ Ваш Telegram уже привязан к игроку: **{player_name}**",
            parse_mode='Markdown'
        )
        return

    # Проверяем код
    if code not in storage.pending_codes:
        await update.message.reply_text("""❌ **Неверный или истекший код!**

🔄 Попробуйте еще раз:
1. Зайдите на сервер
2. Получите новый код привязки
3. Отправьте: `/link НОВЫЙ_КОД`""", parse_mode='Markdown')
        return

    # Проверяем не истек ли код
    code_data = storage.pending_codes[code]
    if time.time() > code_data.get('expires_at', 0):
        del storage.pending_codes[code]
        storage.save_data()

        await update.message.reply_text("""⏰ **Код истек!**

🔄 Получите новый код:
1. Зайдите на сервер снова
2. Получите новый код привязки
3. Отправьте: `/link НОВЫЙ_КОД`""", parse_mode='Markdown')
        return

    # Выполняем привязку
    player_name = code_data.get('player_name', 'Неизвестно')
    player_uuid = code_data.get('player_uuid', '')

    # Удаляем старые привязки если есть
    old_user_id = None
    for tid, pname in storage.links.items():
        if pname == player_name:
            old_user_id = tid
            break

    if old_user_id:
        del storage.links[old_user_id]

    # Добавляем новую привязку
    storage.links[user_id] = player_name
    del storage.pending_codes[code]
    storage.save_data()

    await update.message.reply_text(f"""✅ **Привязка успешна!**

🎮 Ваш Telegram привязан к игроку: **{player_name}**

Теперь вы можете заходить на сервер!""", parse_mode='Markdown')

    logger.info(f"Пользователь {username} ({user_id}) привязал аккаунт игрока {player_name}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status"""
    user_id = update.effective_user.id

    # Очищаем истекшие коды
    storage.cleanup_expired_codes()

    if user_id in storage.links:
        player_name = storage.links[user_id]
        message = f"""✅ **Статус привязки: Активна**

🎮 Привязанный игрок: **{player_name}**
🕐 Привязано: {datetime.now().strftime('%d.%m.%Y')}"""
    else:
        message = """❌ **Статус привязки: Не привязан**

🎮 Ваш Telegram не привязан к игровому аккаунту.

Для привязки используйте команду /help"""

    await update.message.reply_text(message, parse_mode='Markdown')


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /unlink"""
    user_id = update.effective_user.id

    if user_id not in storage.links:
        await update.message.reply_text(
            "❌ **Ваш аккаунт не привязан к Telegram!**",
            parse_mode='Markdown'
        )
        return

    player_name = storage.links[user_id]
    del storage.links[user_id]
    storage.save_data()

    await update.message.reply_text(f"""✅ **Аккаунт успешно отвязан!**

🎮 Отвязан игрок: **{player_name}**

⚠️ При следующем входе на сервер потребуется заново привязать аккаунт.""", parse_mode='Markdown')

    logger.info(f"Пользователь отвязал аккаунт игрока {player_name}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    message = """🤖 **Помощь по боту привязки аккаунтов**

📋 **Доступные команды:**
/start - приветствие и информация
/link КОД - привязать аккаунт по коду
/help - показать эту помощь
/status - проверить статус привязки
/unlink - отвязать аккаунт

🎮 **Как привязать аккаунт:**
1. Попробуйте зайти на сервер
2. Вас кикнет с кодом привязки
3. Отправьте боту: `/link ВАШ_КОД`
4. Заходите на сервер!

⚠️ Коды действительны только 10 минут!"""

    await update.message.reply_text(message, parse_mode='Markdown')


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик неизвестных команд"""
    await update.message.reply_text("""❓ **Неизвестная команда!**

Используйте /help для просмотра доступных команд.""", parse_mode='Markdown')


def main() -> None:
    """Запуск бота"""


def main() -> None:
    """Запуск бота"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Пожалуйста, установите токен бота в переменной BOT_TOKEN")
        return

    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("link", link_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("unlink", unlink_command))
    application.add_handler(CommandHandler("help", help_command))

    # Запускаем бота
    logger.info("Запуск Telegram бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()