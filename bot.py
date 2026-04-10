import os
import asyncio
import logging
import subprocess
import socket
import time
import signal
import requests
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Проверка обязательных переменных
if not API_ID:
    raise ValueError("API_ID не указан!")
if not API_HASH:
    raise ValueError("API_HASH не указан!")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не указан!")

# Настройки IceCast
ICECAST_HOST = os.getenv("ICECAST_HOST", "localhost")
ICECAST_PORT = int(os.getenv("ICECAST_PORT", "8000"))
ICECAST_PASSWORD = os.getenv("ICECAST_PASSWORD", "hackme")
ICECAST_MOUNT = os.getenv("ICECAST_MOUNT", "/radio.mp3")

# Публичный адрес сервера
PUBLIC_HOST = os.getenv("PUBLIC_HOST", "localhost")
PUBLIC_PORT = os.getenv("PUBLIC_PORT", "8000")

# Источник аудио
MUSIC_DIR = os.getenv("MUSIC_DIR", "/app/music")

# Глобальные переменные
icecast_process = None
ffmpeg_process = None
stream_active = False

# Формируем публичную ссылку
STREAM_URL = f"http://{PUBLIC_HOST}:{PUBLIC_PORT}{ICECAST_MOUNT}"

# Инициализация Pyrogram клиента
app = Client(
    "radio_bot",
    api_id=2040,
    api_hash="b18441a1ff607e10a989891a5462e627",
    bot_token="8788795304:AAE8a0TEsRw8aRhflGIrIQoJZIZf1ZErcA0"
)

def check_icecast_status():
    """Проверяет, запущен ли IceCast и отвечает ли он."""
    try:
        response = requests.get(f"http://{ICECAST_HOST}:{ICECAST_PORT}/status-json.xsl", timeout=5)
        if response.status_code == 200:
            logger.info("IceCast отвечает на запросы")
            return True
    except Exception as e:
        logger.warning(f"IceCast не отвечает: {e}")
    return False

def start_icecast():
    """Запускает IceCast сервер с подробным логированием."""
    global icecast_process
    
    # Проверяем, не запущен ли уже IceCast
    if check_icecast_status():
        logger.info("IceCast уже запущен и работает")
        return True
    
    logger.info("Запускаем IceCast сервер...")
    
    # Создаем конфигурацию IceCast если её нет
    icecast_config = "/etc/icecast2/icecast.xml"
    if not os.path.exists(icecast_config):
        logger.warning(f"Конфигурация IceCast не найдена: {icecast_config}")
        create_icecast_config()
    
    # Создаем необходимые директории
    os.makedirs("/var/log/icecast2", exist_ok=True)
    os.makedirs("/usr/share/icecast2", exist_ok=True)
    
    try:
        # Запускаем IceCast с выводом логов
        cmd = ["icecast2", "-c", icecast_config]
        
        # Открываем файлы для логов
        stdout_log = open("/var/log/icecast2/icecast_stdout.log", "w")
        stderr_log = open("/var/log/icecast2/icecast_stderr.log", "w")
        
        icecast_process = subprocess.Popen(
            cmd,
            stdout=stdout_log,
            stderr=stderr_log
        )
        
        # Ждем запуска и проверяем статус
        for i in range(10):  # 10 попыток по 1 секунде
            time.sleep(1)
            
            # Проверяем, жив ли процесс
            if icecast_process.poll() is not None:
                logger.error(f"IceCast завершился с кодом: {icecast_process.returncode}")
                # Читаем stderr для диагностики
                with open("/var/log/icecast2/icecast_stderr.log", "r") as f:
                    stderr_content = f.read()
                    logger.error(f"Ошибка IceCast: {stderr_content}")
                return False
            
            # Проверяем, отвечает ли сервер
            if check_icecast_status():
                logger.info("IceCast успешно запущен и отвечает на запросы")
                return True
            
            logger.info(f"Ожидание запуска IceCast... попытка {i+1}/10")
        
        logger.error("IceCast не запустился за отведенное время")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка запуска IceCast: {e}")
        return False

def create_icecast_config():
    """Создает минимальную рабочую конфигурацию IceCast."""
    config_content = f"""<icecast>
    <limits>
        <clients>100</clients>
        <sources>2</sources>
        <queue-size>524288</queue-size>
        <client-timeout>30</client-timeout>
        <header-timeout>15</header-timeout>
        <source-timeout>10</source-timeout>
    </limits>

    <authentication>
        <source-password>{ICECAST_PASSWORD}</source-password>
        <relay-password>{ICECAST_PASSWORD}</relay-password>
        <admin-user>admin</admin-user>
        <admin-password>{ICECAST_PASSWORD}</admin-password>
    </authentication>

    <hostname>localhost</hostname>
    
    <listen-socket>
        <port>{ICECAST_PORT}</port>
        <bind-address>0.0.0.0</bind-address>
    </listen-socket>

    <fileserve>1</fileserve>

    <paths>
        <basedir>/usr/share/icecast2</basedir>
        <logdir>/var/log/icecast2</logdir>
        <webroot>/usr/share/icecast2/web</webroot>
        <adminroot>/usr/share/icecast2/admin</adminroot>
    </paths>

    <logging>
        <accesslog>access.log</accesslog>
        <errorlog>error.log</errorlog>
        <loglevel>4</loglevel>
    </logging>
</icecast>"""
    
    config_path = "/etc/icecast2/icecast.xml"
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    with open(config_path, "w") as f:
        f.write(config_content)
    
    logger.info(f"Создана конфигурация IceCast: {config_path}")

def start_ffmpeg_stream():
    """Запускает FFmpeg для отправки потока в IceCast."""
    global ffmpeg_process, stream_active
    
    if stream_active:
        logger.info("Поток уже активен")
        return True
    
    logger.info("Запускаем FFmpeg поток...")
    
    # Проверяем наличие музыки, если нет - создаем тестовый поток
    if not os.path.exists(MUSIC_DIR) or not os.listdir(MUSIC_DIR):
        logger.warning(f"Директория с музыкой пуста: {MUSIC_DIR}, создаю тестовый тон")
        
        # Генерируем тестовый аудио поток (синусоида 440 Гц)
        cmd = [
            'ffmpeg',
            '-re',
            '-f', 'lavfi',
            '-i', 'sine=frequency=440:duration=3600',
            '-c:a', 'libmp3lame',
            '-b:a', '128k',
            '-f', 'mp3',
            '-content_type', 'audio/mpeg',
            f'icecast://source:{ICECAST_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}'
        ]
    else:
        # Используем реальные файлы
        # Создаем плейлист
        playlist_path = os.path.join(MUSIC_DIR, "playlist.txt")
        with open(playlist_path, "w") as f:
            for file in os.listdir(MUSIC_DIR):
                if file.endswith(('.mp3', '.m4a', '.ogg', '.flac')):
                    f.write(f"file '{os.path.join(MUSIC_DIR, file)}'\n")
        
        cmd = [
            'ffmpeg',
            '-re',
            '-stream_loop', '-1',
            '-f', 'concat',
            '-safe', '0',
            '-i', playlist_path,
            '-c:a', 'libmp3lame',
            '-b:a', '128k',
            '-f', 'mp3',
            '-content_type', 'audio/mpeg',
            f'icecast://source:{ICECAST_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}{ICECAST_MOUNT}'
        ]
    
    try:
        # Открываем файлы для логов FFmpeg
        stdout_log = open("/var/log/ffmpeg_stdout.log", "w")
        stderr_log = open("/var/log/ffmpeg_stderr.log", "w")
        
        ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=stdout_log,
            stderr=stderr_log
        )
        
        time.sleep(3)
        
        if ffmpeg_process.poll() is None:
            stream_active = True
            logger.info("FFmpeg поток успешно запущен")
            return True
        else:
            logger.error(f"FFmpeg завершился с кодом: {ffmpeg_process.returncode}")
            with open("/var/log/ffmpeg_stderr.log", "r") as f:
                logger.error(f"Ошибка FFmpeg: {f.read()}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка запуска FFmpeg: {e}")
        return False

@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Запускает радио и отправляет ссылку."""
    global stream_active
    
    logger.info(f"Получена команда /start от {message.from_user.id}")
    
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
    
    status_msg = await message.reply_text("🚀 **Запускаю радио...**\n\n⏳ Запуск IceCast сервера...")
    
    # Запускаем IceCast
    loop = asyncio.get_event_loop()
    icecast_started = await loop.run_in_executor(None, start_icecast)
    
    if not icecast_started:
        await status_msg.edit_text(
            "❌ **Ошибка запуска IceCast сервера**\n\n"
            "Проверьте логи командой:\n"
            "`docker-compose exec radio-bot cat /var/log/icecast2/icecast_stderr.log`"
        )
        return
    
    await status_msg.edit_text("🚀 **Запускаю радио...**\n\n✅ IceCast запущен\n⏳ Запуск аудио потока...")
    
    # Запускаем FFmpeg
    ffmpeg_started = await loop.run_in_executor(None, start_ffmpeg_stream)
    
    if not ffmpeg_started:
        await status_msg.edit_text(
            "❌ **Ошибка запуска аудио потока**\n\n"
            "Проверьте логи командой:\n"
            "`docker-compose exec radio-bot cat /var/log/ffmpeg_stderr.log`"
        )
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Открыть в браузере", url=STREAM_URL)],
        [InlineKeyboardButton("📊 Статистика IceCast", url=f"http://{PUBLIC_HOST}:{PUBLIC_PORT}")]
    ])
    
    await status_msg.edit_text(
        f"✅ **Радио успешно запущено!**\n\n"
        f"🔗 **Прямая ссылка:**\n`{STREAM_URL}`\n\n"
        f"📊 **Статистика:** http://{PUBLIC_HOST}:{PUBLIC_PORT}\n\n"
        f"Для остановки: /stop\n"
        f"Для диагностики: /logs",
        reply_markup=keyboard
    )
    
    logger.info(f"Радио запущено. URL: {STREAM_URL}")

@app.on_message(filters.command("stop"))
async def stop_command(client, message):
    """Останавливает радио."""
    global ffmpeg_process, icecast_process, stream_active
    
    if not stream_active:
        await message.reply_text("ℹ️ Радио не запущено")
        return
    
    status_msg = await message.reply_text("🛑 Останавливаю радио...")
    
    # Останавливаем FFmpeg
    if ffmpeg_process:
        ffmpeg_process.terminate()
        try:
            ffmpeg_process.wait(timeout=5)
        except:
            ffmpeg_process.kill()
        ffmpeg_process = None
    
    # Останавливаем IceCast
    if icecast_process:
        icecast_process.terminate()
        try:
            icecast_process.wait(timeout=5)
        except:
            icecast_process.kill()
        icecast_process = None
    
    stream_active = False
    await status_msg.edit_text("✅ **Радио остановлено**")

@app.on_message(filters.command("status"))
async def status_command(client, message):
    """Показывает статус радио."""
    if stream_active:
        await message.reply_text(
            f"📊 **Статус радио:**\n\n"
            f"✅ Статус: **Активно**\n"
            f"🔗 Поток: `{STREAM_URL}`\n"
            f"🌐 IceCast: http://{PUBLIC_HOST}:{PUBLIC_PORT}"
        )
    else:
        await message.reply_text("⚫ **Статус:** Остановлено")

@app.on_message(filters.command("logs"))
async def logs_command(client, message):
    """Отправляет последние строки логов."""
    logs_text = "**Последние логи:**\n\n"
    
    # Логи IceCast
    if os.path.exists("/var/log/icecast2/icecast_stderr.log"):
        with open("/var/log/icecast2/icecast_stderr.log", "r") as f:
            icecast_logs = f.read()[-500:]  # Последние 500 символов
            if icecast_logs:
                logs_text += f"**IceCast:**\n```{icecast_logs}```\n\n"
    
    # Логи FFmpeg
    if os.path.exists("/var/log/ffmpeg_stderr.log"):
        with open("/var/log/ffmpeg_stderr.log", "r") as f:
            ffmpeg_logs = f.read()[-500:]
            if ffmpeg_logs:
                logs_text += f"**FFmpeg:**\n```{ffmpeg_logs}```"
    
    if logs_text == "**Последние логи:**\n\n":
        await message.reply_text("Логи пусты или недоступны")
    else:
        await message.reply_text(logs_text[:4000])  # Telegram лимит 4096

if __name__ == "__main__":
    logger.info("Запуск Radio Bot...")
    
    # Создаем директории для логов
    os.makedirs("/var/log/icecast2", exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)
    
    # Запускаем бота
    app.run()
