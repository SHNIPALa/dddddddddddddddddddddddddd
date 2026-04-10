import os
import asyncio
import logging
import subprocess
import signal
import socket
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")

# Настройки IceCast
ICECAST_HOST = os.getenv("ICECAST_HOST", "icecast")
ICECAST_PORT = int(os.getenv("ICECAST_PORT", "8000"))
ICECAST_PASSWORD = os.getenv("ICECAST_PASSWORD", "hackme")
ICECAST_MOUNT = os.getenv("ICECAST_MOUNT", "/radio.mp3")

# Публичный адрес сервера
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost")
PUBLIC_PORT = os.getenv("PUBLIC_PORT", "8000")

# Источник аудио (папка с музыкой)
MUSIC_DIR = os.getenv("MUSIC_DIR", "/app/music")

# Глобальные переменные для управления процессами
icecast_process = None
ffmpeg_process = None
stream_active = False

# Формируем публичную ссылку
STREAM_URL = f"http://{PUBLIC_HOST}:{PUBLIC_PORT}{ICECAST_MOUNT}"

# Инициализация Pyrogram клиента
app = Client(
    "radio_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


def get_local_ip():
    """Получает локальный IP адрес контейнера."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def start_icecast():
    """Запускает IceCast сервер."""
    global icecast_process

    if icecast_process and icecast_process.poll() is None:
        logger.info("IceCast уже запущен")
        return True

    try:
        cmd = ["icecast2", "-c", "/etc/icecast2/icecast.xml"]
        icecast_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Даем время на запуск
        import time
        time.sleep(3)

        if icecast_process.poll() is None:
            logger.info("IceCast сервер успешно запущен")
            return True
        else:
            logger.error("IceCast не смог запуститься")
            return False

    except Exception as e:
        logger.error(f"Ошибка запуска IceCast: {e}")
        return False


def start_ffmpeg_stream():
    """Запускает FFmpeg для отправки потока в IceCast."""
    global ffmpeg_process, stream_active

    if stream_active:
        logger.info("Поток уже активен")
        return True

    # Проверяем наличие музыки
    if not os.path.exists(MUSIC_DIR):
        logger.error(f"Директория с музыкой не найдена: {MUSIC_DIR}")
        return False

    # Формируем FFmpeg команду
    cmd = [
        'ffmpeg',
        '-re',  # Читаем в реальном времени
        '-stream_loop', '-1',  # Бесконечный повтор
        '-i', f'concat:{MUSIC_DIR}/*.mp3',  # Конкатенация всех mp3 файлов
        '-c:a', 'libmp3lame',  # Кодек MP3
        '-b:a', '128k',  # Битрейт
        '-f', 'mp3',  # Формат
        '-content_type', 'audio/mpeg',  # MIME тип
        f'icecast://source:{ICECAST_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}'
    ]

    try:
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Проверяем, что процесс запустился
        import time
        time.sleep(2)

        if ffmpeg_process.poll() is None:
            stream_active = True
            logger.info("FFmpeg поток успешно запущен")
            return True
        else:
            logger.error("FFmpeg не смог запуститься")
            return False

    except Exception as e:
        logger.error(f"Ошибка запуска FFmpeg: {e}")
        return False


def stop_ffmpeg_stream():
    """Останавливает FFmpeg поток."""
    global ffmpeg_process, stream_active

    if ffmpeg_process:
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
        ffmpeg_process = None

    stream_active = False
    logger.info("FFmpeg поток остановлен")


def stop_icecast():
    """Останавливает IceCast сервер."""
    global icecast_process

    if icecast_process:
        try:
            icecast_process.terminate()
            icecast_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            icecast_process.kill()
        icecast_process = None

    logger.info("IceCast сервер остановлен")


@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Запускает радио и отправляет ссылку."""
    global stream_active

    if stream_active:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Открыть в браузере", url=STREAM_URL)],
            [InlineKeyboardButton("📋 Скопировать ссылку", callback_data="copy_url")]
        ])

        await message.reply_text(
            f"📻 **Радио уже работает!**\n\n"
            f"🔗 **Ссылка на поток:**\n`{STREAM_URL}`\n\n"
            f"Откройте в:\n"
            f"• VLC (Медиа → Открыть URL)\n"
            f"• Браузере\n"
            f"• AIMP / Winamp / iTunes",
            reply_markup=keyboard
        )
        return

    # Отправляем сообщение о запуске
    status_msg = await message.reply_text(
        "🚀 **Запускаю радио...**\n\n"
        "⏳ Старт IceCast сервера...\n"
        "⏳ Запуск аудио потока...\n"
        "⏳ Настройка FFmpeg..."
    )

    # Запускаем IceCast в отдельном потоке
    loop = asyncio.get_event_loop()

    # Шаг 1: Запуск IceCast
    icecast_started = await loop.run_in_executor(None, start_icecast)

    if not icecast_started:
        await status_msg.edit_text("❌ **Ошибка:** Не удалось запустить IceCast сервер")
        return

    await status_msg.edit_text(
        "🚀 **Запускаю радио...**\n\n"
        "✅ IceCast сервер запущен\n"
        "⏳ Запуск аудио потока...\n"
        "⏳ Настройка FFmpeg..."
    )

    # Шаг 2: Запуск FFmpeg
    ffmpeg_started = await loop.run_in_executor(None, start_ffmpeg_stream)

    if not ffmpeg_started:
        stop_icecast()
        await status_msg.edit_text("❌ **Ошибка:** Не удалось запустить аудио поток")
        return

    # Успешный запуск
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Открыть в браузере", url=STREAM_URL)],
        [InlineKeyboardButton("📋 Скопировать ссылку", callback_data="copy_url")]
    ])

    await status_msg.edit_text(
        f"✅ **Радио успешно запущено!**\n\n"
        f"🔗 **Прямая ссылка:**\n`{STREAM_URL}`\n\n"
        f"📊 **Статистика сервера:**\n"
        f"http://{PUBLIC_HOST}:{PUBLIC_PORT}\n\n"
        f"Для остановки используйте /stop",
        reply_markup=keyboard
    )

    logger.info(f"Радио запущено. URL: {STREAM_URL}")


@app.on_message(filters.command("stop"))
async def stop_command(client, message):
    """Останавливает радио."""
    global stream_active

    if not stream_active:
        await message.reply_text("ℹ️ Радио не запущено")
        return

    status_msg = await message.reply_text("🛑 Останавливаю радио...")

    # Останавливаем FFmpeg и IceCast
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, stop_ffmpeg_stream)
    await loop.run_in_executor(None, stop_icecast)

    await status_msg.edit_text("✅ **Радио остановлено**")


@app.on_message(filters.command("status"))
async def status_command(client, message):
    """Показывает статус радио."""
    if stream_active:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Открыть поток", url=STREAM_URL)]
        ])

        await message.reply_text(
            f"📊 **Статус радио:**\n\n"
            f"✅ Статус: **Активно**\n"
            f"🔗 Поток: `{STREAM_URL}`\n"
            f"🌐 IceCast: http://{PUBLIC_HOST}:{PUBLIC_PORT}\n"
            f"📁 Музыка: {MUSIC_DIR}",
            reply_markup=keyboard
        )
    else:
        await message.reply_text("⚫ **Статус:** Остановлено")


@app.on_message(filters.command("info"))
async def info_command(client, message):
    """Показывает техническую информацию."""
    local_ip = get_local_ip()

    info_text = (
        f"📡 **Информация о сервере:**\n\n"
        f"🌐 Публичный хост: `{PUBLIC_HOST}:{PUBLIC_PORT}`\n"
        f"🏠 Локальный IP: `{local_ip}`\n"
        f"📡 IceCast mount: `{ICECAST_MOUNT}`\n"
        f"📁 Папка с музыкой: `{MUSIC_DIR}`\n"
        f"🎵 Статус: {'Активен' if stream_active else 'Остановлен'}\n"
    )

    await message.reply_text(info_text)


@app.on_callback_query()
async def callback_handler(client, callback_query):
    """Обработчик inline кнопок."""
    if callback_query.data == "copy_url":
        await callback_query.answer("Ссылка скопирована в текст сообщения", show_alert=False)
        await callback_query.message.reply_text(
            f"📋 Ссылка на радио:\n`{STREAM_URL}`"
        )


# Graceful shutdown
async def shutdown_handler():
    """Корректное завершение работы."""
    logger.info("Завершение работы...")
    stop_ffmpeg_stream()
    stop_icecast()
    await app.stop()


if __name__ == "__main__":
    try:
        logger.info("Запуск Radio Bot с IceCast...")
        app.run()
    except KeyboardInterrupt:
        asyncio.run(shutdown_handler())
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        stop_ffmpeg_stream()
        stop_icecast()