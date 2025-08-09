#!/bin/bash

# setup_and_run.sh - Скрипт установки и запуска системы привязки

set -e

echo "🔧 Установка системы привязки Telegram-Minecraft"

# Функция для проверки команд
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "❌ $1 не установлен. Пожалуйста, установите $1"
        exit 1
    fi
}

# Проверяем зависимости
echo "📋 Проверка зависимостей..."
check_command python3
check_command pip3

# Проверяем переменные окружения
if [ -z "$BOT_TOKEN" ]; then
    echo "⚠️  Переменная BOT_TOKEN не установлена"
    echo "📝 Установите её: export BOT_TOKEN='ваш_токен'"
    read -p "Введите токен бота: " token
    export BOT_TOKEN="$token"
fi

# Устанавливаем Python зависимости
echo "📦 Установка Python зависимостей..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt
else
    pip3 install python-telegram-bot==20.7 aiohttp==3.9.1
fi

# Настройки по умолчанию
export MINECRAFT_API_URL="${MINECRAFT_API_URL:-http://localhost:8080/api}"
export MINECRAFT_API_KEY="${MINECRAFT_API_KEY:-your-secret-api-key-here}"

echo "✅ Зависимости установлены"
echo ""
echo "⚙️  Конфигурация:"
echo "   BOT_TOKEN: ${BOT_TOKEN:0:10}..."
echo "   API_URL: $MINECRAFT_API_URL"
echo "   API_KEY: ${MINECRAFT_API_KEY:0:10}..."
echo ""

# Функции управления
start_bot() {
    echo "🚀 Запуск Telegram бота..."

    # Проверяем, не запущен ли уже
    if pgrep -f "python3.*bot.py" > /dev/null; then
        echo "⚠️  Бот уже запущен"
        return 1
    fi

    # Проверяем существование файла
    if [ ! -f "bot.py" ]; then
        echo "❌ Файл bot.py не найден"
        return 1
    fi

    # Запускаем
    nohup python3 bot.py > bot.log 2>&1 &
    BOT_PID=$!

    # Ждем 2 секунды и проверяем
    sleep 2
    if ps -p $BOT_PID > /dev/null 2>&1; then
        echo "✅ Бот запущен (PID: $BOT_PID)"
        echo "📄 Логи: tail -f bot.log"
    else
        echo "❌ Ошибка запуска бота"
        echo "📄 Проверьте логи: cat bot.log"
        return 1
    fi
}

stop_bot() {
    echo "🛑 Остановка Telegram бота..."

    PIDS=$(pgrep -f "python3.*bot.py" || true)
    if [ -z "$PIDS" ]; then
        echo "ℹ️  Бот не запущен"
        return 0
    fi

    for pid in $PIDS; do
        kill $pid
        echo "🔚 Остановлен процесс PID: $pid"
    done

    sleep 1
    echo "✅ Бот остановлен"
}

status_check() {
    echo "📊 Проверка статуса системы..."
    echo ""

    # Проверяем Python бота
    BOT_PIDS=$(pgrep -f "python3.*bot.py" || true)
    if [ -n "$BOT_PIDS" ]; then
        echo "🤖 Telegram бот: 🟢 РАБОТАЕТ (PID: $BOT_PIDS)"
    else
        echo "🤖 Telegram бот: 🔴 НЕ РАБОТАЕТ"
    fi

    # Проверяем API сервера
    if curl -s -f "$MINECRAFT_API_URL/health" > /dev/null 2>&1; then
        echo "🔗 Minecraft API: 🟢 ДОСТУПЕН"
    else
        echo "🔗 Minecraft API: 🔴 НЕДОСТУПЕН"
        echo "   URL: $MINECRAFT_API_URL/health"
    fi

    # Проверяем логи
    if [ -f "bot.log" ]; then
        echo "📄 Последние логи бота:"
        tail -n 5 bot.log | sed 's/^/   /'
    fi

    echo ""
}

show_help() {
    echo "🔧 Управление системой привязки:"
    echo ""
    echo "Команды:"
    echo "  start     - Запустить Telegram бота"
    echo "  stop      - Остановить Telegram бота"
    echo "  restart   - Перезапустить Telegram бота"
    echo "  status    - Показать статус системы"
    echo "  logs      - Показать логи бота"
    echo "  test      - Тестовая проверка API"
    echo "  setup     - Только установка зависимостей"
    echo ""
    echo "Переменные окружения:"
    echo "  BOT_TOKEN           - Токен Telegram бота"
    echo "  MINECRAFT_API_URL   - URL API сервера ($MINECRAFT_API_URL)"
    echo "  MINECRAFT_API_KEY   - API ключ сервера"
    echo ""
}

test_api() {
    echo "🧪 Тестирование API связи..."

    # Тест health check
    echo "📡 Проверка health endpoint..."
    if curl -s -f "$MINECRAFT_API_URL/health" > /dev/null; then
        echo "✅ Health check прошел"
        curl -s "$MINECRAFT_API_URL/health" | python3 -m json.tool
    else
        echo "❌ Health check не прошел"
        echo "🔧 Проверьте:"
        echo "   1. Запущен ли сервер Minecraft"
        echo "   2. Включен ли плагин"
        echo "   3. Правильный ли URL: $MINECRAFT_API_URL"
        return 1
    fi
    echo ""
}

# Основная логика
case "${1:-help}" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        stop_bot
        sleep 2
        start_bot
        ;;
    status)
        status_check
        ;;
    logs)
        if [ -f "bot.log" ]; then
            tail -f bot.log
        else
            echo "❌ Лог файл не найден"
        fi
        ;;
    test)
        test_api
        ;;
    setup)
        echo "✅ Установка завершена"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        show_help
        ;;
esac