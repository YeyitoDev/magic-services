FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p images output logs csv estados credentials

CMD python -c "import os,base64; d=os.environ['GOOGLE_CREDENTIALS_JSON']; open('credentials/google.json','w').write(base64.b64decode(d).decode() if d[0]!='{' else d)" && python main.py
