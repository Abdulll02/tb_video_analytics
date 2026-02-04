FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости (нужны для сборки некоторых python пакетов)
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]