FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p images output logs csv estados credentials

CMD python -c "
import os, base64
os.makedirs('credentials', exist_ok=True)
d = os.environ.get('GOOGLE_CREDENTIALS_JSON', '')
if d:
    try:
        data = base64.b64decode(d).decode() if d[0] != '{' else d
        open('credentials/google.json', 'w').write(data)
        print('✅ Google credentials written')
    except Exception as e:
        print(f'⚠️ Could not write Google credentials: {e}')
else:
    print('⚠️ GOOGLE_CREDENTIALS_JSON not set')
" && python main.py
