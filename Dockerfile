FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    icecast2 \
    ffmpeg \
    wget \
    curl \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Копируем конфигурацию IceCast
COPY icecast.xml /etc/icecast2/icecast.xml

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Создаем директории
RUN mkdir -p /app/music /var/log/icecast2 /usr/share/icecast2

# Настраиваем права для IceCast
RUN chown -R www-data:www-data /var/log/icecast2 && \
    chown -R www-data:www-data /usr/share/icecast2 && \
    chmod 755 /var/log/icecast2

# Открываем порты
EXPOSE 8000  # IceCast HTTP порт

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Запускаем бота
CMD ["python", "bot.py"]