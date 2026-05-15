FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl netcat-openbsd && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p images output logs csv estados credentials

# Start both: dummy TCP listener for health check + the bot
CMD sh -c 'while true; do nc -l -p 8080 -c "echo OK"; done & python main.py'
