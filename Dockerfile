FROM python:3.12-slim

WORKDIR /app

# Install git-lfs to pull actual image files
RUN apt-get update && apt-get install -y git-lfs curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy .git directory for LFS pointers
COPY .git .git
COPY .gitattributes .

# Pull LFS files (actual images/videos)
RUN git lfs pull

# Copy the rest of the app
COPY . .

RUN mkdir -p images output logs csv estados credentials

CMD python -c "import os,base64; d=os.environ['GOOGLE_CREDENTIALS_JSON']; open('credentials/google.json','w').write(base64.b64decode(d).decode() if d[0]!='{' else d)" && python main.py
