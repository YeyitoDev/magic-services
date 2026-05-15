FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p images output logs csv estados credentials

# Keep container alive and log everything
CMD sh -c 'python main.py 2>&1 | tee -a logs/app.log; echo "Bot exited with code $?"; tail -f /dev/null'
