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

# Создаем необходимые директории для IceCast
RUN mkdir -p /var/log/icecast2 /usr/share/icecast2 /app/music

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Открываем порты
EXPOSE 8000

# Запускаем бота
CMD ["python", "bot.py"]
