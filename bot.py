import os
import asyncio
import logging
import subprocess
import socket
import time
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
ICECAST_HOST = os.getenv("ICECAST_HOST", "localhost")
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


def start_icecast():
    """Запускает IceCast сервер."""
    global icecast_process

    try:
        # Проверяем, не запущен ли уже IceCast
        check_cmd = ["pgrep", "-f", "icecast2"]
        result = subprocess.run(check_cmd, capture_output=True)
        if result.returncode == 0:
            logger.info("IceCast уже запущен")
            return True

        # Запускаем IceCast
        cmd = ["icecast2", "-c", "/etc/icecast2/icecast.xml", "-b"]
        icecast_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # Ждем запуска
        time.sleep(3)

        # Проверяем, что процесс работает
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
        os.makedirs(MUSIC_DIR, exist_ok=True)
        # Создаем тестовый тихий поток если нет музыки
        cmd = [
            'ffmpeg',
            '-re',
            '-f', 'lavfi',
            '-i', 'anullsrc=r=44100:cl=mono',
            '-c:a', 'libmp3lame',
            '-b:a', '128k',
            '-f', 'mp3',
            '-content_type', 'audio/mpeg',
            f'icecast://source:{ICECAST_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}'
        ]
    else:
        # Формируем FFmpeg команду с реальной музыкой
        cmd = [
            'ffmpeg',
            '-re',
            '-stream_loop', '-1',
            '-f', 'concat',
            '-safe', '0',
            '-i', f'{MUSIC_DIR}/playlist.txt' if os.path.exists(f'{MUSIC_DIR}/playlist.txt') else '-',
            '-c:a', 'libmp3lame',
            '-b:a', '128k',
            '-f', 'mp3',
            '-content_type', 'audio/mpeg',
            f'icecast://source:{ICECAST_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}'
        ]

    try:
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

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


@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Запускает радио и отправляет ссылку."""
    global stream_active

    if stream_active:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Открыть в браузере", url=STREAM_URL)]
        ])

        await message.reply_text(
            f"📻 **Радио уже работает!**\n\n"
            f"🔗 **Ссылка на поток:**\n`{STREAM_URL}`\n\n"
            f"Откройте в VLC или браузере",
            reply_markup=keyboard
        )
        return

    status_msg = await message.reply_text("🚀 **Запускаю радио...**")

    # Запускаем IceCast
    if not start_icecast():
        await status_msg.edit_text("❌ Ошибка запуска IceCast сервера")
        return

    await status_msg.edit_text("🚀 **Запускаю радио...**\n✅ IceCast запущен\n⏳ Запуск потока...")

    # Запускаем FFmpeg
    if not start_ffmpeg_stream():
        await status_msg.edit_text("❌ Ошибка запуска аудио потока")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Открыть в браузере", url=STREAM_URL)]
    ])

    await status_msg.edit_text(
        f"✅ **Радио успешно запущено!**\n\n"
        f"🔗 **Прямая ссылка:**\n`{STREAM_URL}`\n\n"
        f"Для остановки: /stop",
        reply_markup=keyboard
    )


@app.on_message(filters.command("stop"))
async def stop_command(client, message):
    """Останавливает радио."""
    global ffmpeg_process, icecast_process, stream_active

    if not stream_active:
        await message.reply_text("ℹ️ Радио не запущено")
        return

    # Останавливаем FFmpeg
    if ffmpeg_process:
        ffmpeg_process.terminate()
        ffmpeg_process = None

    # Останавливаем IceCast
    if icecast_process:
        icecast_process.terminate()
        icecast_process = None

    stream_active = False
    await message.reply_text("✅ **Радио остановлено**")


if __name__ == "__main__":
    logger.info("Запуск Radio Bot...")
    app.run()
