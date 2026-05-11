# Deploy en PythonAnywhere

## Setup Inicial (hacer solo una vez)

### 1. Crear cuenta en pythonanywhere.com
Regístrate en [pythonanywhere.com](https://www.pythonanywhere.com) y crea una cuenta gratuita.

### 2. Abrir Bash Console y ejecutar:

```bash
# Clonar el repo
git clone https://github.com/YeyitoDev/magic-services.git
cd magic-services

# Crear virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configurar .env para testing
cp .env.testing .env

# Probar que arranca
python main.py
# Ctrl+C después de ver que conecta
```

### 3. Crear Always-on Task

Dashboard → Tasks → Always-on tasks → Add:

```
Command: cd ~/magic-services && source .venv/bin/activate && python main.py
```

### 4. Configurar API Token

Account → API Token → Generate → Guardarlo como `PYTHONANYWHERE_API_TOKEN`

### 5. Configurar Telegram Bot Token

Crear un bot con [@BotFather](https://t.me/BotFather) en Telegram y guardar el token como `TELEGRAM_BOT_TOKEN`.

### 6. GitHub Secrets

Agregar en Settings → Secrets → Actions:

| Secret | Valor |
|--------|-------|
| PYTHONANYWHERE_USERNAME | Tu usuario |
| PYTHONANYWHERE_PASSWORD | Tu contraseña |
| PYTHONANYWHERE_API_TOKEN | Token generado |
| TELEGRAM_BOT_TOKEN | Token del bot |

## Deploy Automático

- Push a `develop` → Deploy a testing (vía SSH + always-on task)
- Push a `main` → Deploy a producción (vía SSH + always-on task)

El workflow se encarga de:

1. Ejecutar los tests
2. Conectarse por SSH a PythonAnywhere
3. Hacer `git pull` de la rama correspondiente
4. Copiar el archivo `.env` adecuado (`.env.testing` o `.env.production`)
5. Reiniciar la always-on task vía API
6. Enviar notificación por Telegram