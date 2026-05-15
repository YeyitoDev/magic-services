FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p images output logs csv estados credentials

CMD python -c "import os; f=open('credentials/google.json','w'); f.write(os.environ['GOOGLE_CREDENTIALS_JSON']); f.close()" && python main.py
