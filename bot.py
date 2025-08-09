#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import sys
import time
import signal
import aiohttp
from datetime import datetime
from typing import Dict, Optional
from collections import defaultdict

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import Conflict, NetworkError, TimedOut

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN", "8276621692:AAHo3hKkfTISwuzzVRJfWVFi3sSPMiINSo4")
MINECRAFT_API_URL = os.getenv("MINECRAFT_API_URL", "http://localhost:8080/api")
MINECRAFT_API_KEY = os.getenv("MINECRAFT_API_KEY", "default-secret-key")


class MinecraftApiClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def verify_code(self, code: str, telegram_id: int) -> dict:
        """Верифицирует код привязки через Minecraft API"""
        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "code": code,
                    "telegram_id": telegram_id
                }

                async with session.post(
                        f"{self.base_url}/verify",
                        headers=self.headers,
                        json=data,
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    result = await response.json()
                    return {
                        "success": response.status == 200,
                        "data": result
                    }

        except Exception as e:
            logger.error(f"Ошибка API запроса: {e}")
            return {"success": False, "error": str(e)}

    async def get_linked_player(self, telegram_id: int) -> Optional[str]:
        """Получает информацию о привязанном игроке"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.base_url}/links?telegram_id={telegram_id}",
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("player_name")
                    return None

        except Exception as e:
            logger.error(f"Ошибка получения привязки: {e}")
            return None

    async def health_check(self) -> bool:
        """Проверка здоровья API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.base_url}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    return response.status == 200
        except:
            return False


class DataStorage:
    def __init__(self, data_file: str = "bot_data.json"):
        self.data_file = data_file
        self.links: Dict[int, str] = {}
        self.load_data()

    def load_data(self):
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.links = {int(k): v for k, v in data.get('links', {}).items()}
                logger.info(f"Загружено {len(self.links)} привязок")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")

    def save_data(self):
        """Сохранение данных в файл"""
        try:
            data = {'links': {str(k): v for k, v in self.links.items()}}

            # Безопасные места для сохранения
            save_locations = [
                self.data_file,
                os.path.expanduser(f"~/{self.data_file}"),
                f"/tmp/{self.data_file}"
            ]

            for location in save_locations:
                try:
                    temp_file = f"{location}.tmp"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(temp_file, location)

                    if location != self.data_file:
                        logger.info(f"Данные сохранены в: {location}")
                        self.data_file = location
                    break
                except OSError:
                    continue
            else:
                logger.error("Не удалось сохранить данные")

        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")


# Инициализация
storage = DataStorage()
minecraft_api = MinecraftApiClient(MINECRAFT_API_URL, MINECRAFT_API_KEY)


# Rate limiting
class RateLimiter:
    def __init__(self, max_requests=10, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = defaultdict(list)

    def is_allowed(self, user_id):
        now = time.time()
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]

        if len(self.requests[user_id]) < self.max_requests:
            self.requests[user_id].append(now)
            return True
        return False


rate_limiter = RateLimiter()


async def check_rate_limit(update: Update) -> bool:
    """Проверка rate limit"""
    user_id = update.effective_user.id
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text(
            "⚠️ **Слишком много запросов!**\n\nПодождите минуту перед следующей командой.",
            parse_mode='Markdown'
        )
        return False
    return True


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    if not await check_rate_limit(update):
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or "Неизвестно"

    # Проверяем привязку через API
    player_name = await minecraft_api.get_linked_player(user_id)

    if player_name:
        # Обновляем локальный кеш
        storage.links[user_id] = player_name
        storage.save_data()

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
    if not await check_rate_limit(update):
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or "Неизвестно"

    # Проверяем доступность API
    if not await minecraft_api.health_check():
        await update.message.reply_text(
            "❌ **Сервер недоступен!**\n\nПопробуйте позже или обратитесь к администратору.",
            parse_mode='Markdown'
        )
        return

    if not context.args:
        await update.message.reply_text(
            "❌ **Неверный формат команды!**\n\nИспользуйте: `/link ВАШ_КОД`",
            parse_mode='Markdown'
        )
        return

    code = context.args[0].upper().strip()

    # Валидация кода
    if not code.isalnum() or len(code) != 8:
        await update.message.reply_text(
            "❌ **Неверный формат кода!**\n\nКод должен содержать только буквы и цифры (8 символов).",
            parse_mode='Markdown'
        )
        return

    # Проверяем текущую привязку
    current_player = await minecraft_api.get_linked_player(user_id)
    if current_player:
        await update.message.reply_text(
            f"⚠️ Ваш Telegram уже привязан к игроку: **{current_player}**\n\n"
            "Используйте /unlink чтобы отвязать аккаунт.",
            parse_mode='Markdown'
        )
        return

    # Отправляем сообщение о проверке
    checking_msg = await update.message.reply_text("🔄 **Проверяю код...**", parse_mode='Markdown')

    try:
        # Верифицируем код через API
        result = await minecraft_api.verify_code(code, user_id)

        if result["success"]:
            player_name = result["data"].get("player_name", "Неизвестно")

            # Обновляем локальный кеш
            storage.links[user_id] = player_name
            storage.save_data()

            await checking_msg.edit_text(f"""✅ **Привязка успешна!**

🎮 Ваш Telegram привязан к игроку: **{player_name}**

Теперь вы можете заходить на сервер!""", parse_mode='Markdown')

            logger.info(f"Пользователь {username} ({user_id}) привязал аккаунт игрока {player_name}")

        else:
            error_msg = result.get("data", {}).get("error", "Неверный или истекший код")
            await checking_msg.edit_text(f"""❌ **{error_msg}**

🔄 Попробуйте еще раз:
1. Зайдите на сервер
2. Получите новый код привязки
3. Отправьте: `/link НОВЫЙ_КОД`""", parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка верификации: {e}")
        await checking_msg.edit_text(
            "❌ **Ошибка сервера!**\n\nПопробуйте позже или обратитесь к администратору.",
            parse_mode='Markdown'
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status"""
    if not await check_rate_limit(update):
        return

    user_id = update.effective_user.id

    # Получаем актуальную информацию через API
    player_name = await minecraft_api.get_linked_player(user_id)

    if player_name:
        # Обновляем локальный кеш
        storage.links[user_id] = player_name
        storage.save_data()

        message = f"""✅ **Статус привязки: Активна**

🎮 Привязанный игрок: **{player_name}**
🕐 Проверено: {datetime.now().strftime('%d.%m.%Y %H:%M')}
🔗 API: {'🟢 Доступен' if await minecraft_api.health_check() else '🔴 Недоступен'}"""
    else:
        message = """❌ **Статус привязки: Не привязан**

🎮 Ваш Telegram не привязан к игровому аккаунту.

Для привязки используйте команду /help"""

    await update.message.reply_text(message, parse_mode='Markdown')


async def unlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /unlink"""
    if not await check_rate_limit(update):
        return

    user_id = update.effective_user.id

    # Получаем актуальную информацию
    player_name = await minecraft_api.get_linked_player(user_id)

    if not player_name:
        await update.message.reply_text(
            "❌ **Ваш аккаунт не привязан к Telegram!**",
            parse_mode='Markdown'
        )
        return

    # Удаляем из локального кеша
    if user_id in storage.links:
        del storage.links[user_id]
        storage.save_data()

    await update.message.reply_text(f"""⚠️ **Внимание!**

🎮 Найдена привязка к игроку: **{player_name}**

❗ Отвязка происходит на сервере автоматически при следующем входе.
Локальный кеш бота очищен.

⚠️ При следующем входе на сервер потребуется заново привязать аккаунт.""", parse_mode='Markdown')

    logger.info(f"Пользователь запросил отвязку аккаунта игрока {player_name}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    api_status = "🟢 Доступен" if await minecraft_api.health_check() else "🔴 Недоступен"

    message = f"""🤖 **Помощь по боту привязки аккаунтов**

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

⚠️ Коды действительны только 10 минут!

🔗 **Статус сервера:** {api_status}"""

    await update.message.reply_text(message, parse_mode='Markdown')


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Exception while handling an update: {context.error}")

    if isinstance(context.error, Conflict):
        logger.error("Conflict error: другой экземпляр бота уже запущен!")
        sys.exit(1)

    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning(f"Network error: {context.error}. Продолжаем работу...")
        return


def signal_handler(signum, frame):
    """Обработчик сигналов"""
    logger.info(f"Получен сигнал {signum}, завершаем работу...")
    sys.exit(0)


def main() -> None:
    """Запуск бота"""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        logger.error("Установите переменную окружения BOT_TOKEN")
        sys.exit(1)

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("link", link_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("unlink", unlink_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_error_handler(error_handler)

        logger.info("🚀 Telegram бот запущен!")
        logger.info(f"🔗 Minecraft API: {MINECRAFT_API_URL}")
        logger.info(f"PID: {os.getpid()}")

        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )

    except Conflict as e:
        logger.error(f"Conflict error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Получено прерывание от клавиатуры")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()