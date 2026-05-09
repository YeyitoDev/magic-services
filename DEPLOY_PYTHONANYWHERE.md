# 1. Crear feature branch
git checkout develop
git pull origin develop
git checkout -b feature/nueva-funcionalidad

# 2. Hacer cambios y commit
git add .
git commit -m "feat: descripción del cambio"

# 3. Push y crear PR
git push origin feature/nueva-funcionalidad
# Crear Pull Request en GitHub de feature/* → develop

# 4. Merge a develop (tras review)
git checkout develop
git merge feature/nueva-funcionalidad
git push origin develop

# 5. Release a main
git checkout main
git merge develop
git tag v2.0.1
git push origin main --tags
# → CI/CD hace deploy automático a PythonAnywhere
```

## Convenciones de commit

| Tipo | Ejemplo |
|------|---------|
| `feat:` | `feat: dynamic pricing from database` |
| `fix:` | `fix: button_data_invalid in payment keyboard` |
| `refactor:` | `refactor: extract PricingService from subscription_service` |
| `docs:` | `docs: add PythonAnywhere deployment guide` |
| `chore:` | `chore: update dependencies` |
</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
<｜｜DSML｜｜invoke name="edit_file">
<｜｜DSML｜｜parameter name="display_description" string="true">Create DEPLOY_PYTHONANYWHERE.md</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="mode" string="true">create</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="path" string="true">/Users/sergio/Desktop/Magic/MagicWeb/magic-chatbot/v2_refactor/DEPLOY_PYTHONANYWHERE.md</｜｜DSML｜｜parameter>
<｜｜DSML｜｜parameter name="content" string="true"># Deploy en PythonAnywhere - Magic Chatbot v2

## 1. Subir el código

```bash
# Opción A: Git clone (recomendado)
cd ~
git clone https://github.com/TU_USUARIO/magic-chatbot.git
cd magic-chatbot

# Opción B: Upload ZIP
# En el dashboard: Files → Upload a file → magic-chatbot.zip → Unzip
```

## 2. Configurar entorno virtual

```bash
cd ~/magic-chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r v2_refactor/requirements.txt
```

## 3. Configurar variables de entorno

```bash
cd ~/magic-chatbot/v2_refactor
cp .env.example .env
nano .env
```

Variables CRÍTICAS para producción:
```
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=TU_TOKEN_PRODUCCION
DB_HOST=magic-db-prd-original.cpmay4kgurq6.us-east-1.rds.amazonaws.com
DB_NAME=magic-db-prd
DB_USER=yeyo_admin
DB_PASSWORD=PrDMagic2024.
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
```

## 4. Always-on Task (mantiene el bot vivo 24/7)

```
Dashboard → Tasks → Always-on tasks → Add:
  Command: cd ~/magic-chatbot && source .venv/bin/activate && cd v2_refactor && python3 main.py
```

## 5. Scheduled Tasks (cron jobs)

| Tarea | Schedule | Command |
|-------|----------|---------|
| Limpieza suscripciones | Diario 20:00 UTC-5 | `cd ~/magic-chatbot && source .venv/bin/activate && cd v2_refactor && python3 -m jobs.subscription_cleanup validar` |
| Pipeline promociones | Cada 15 min | `cd ~/magic-chatbot && source .venv/bin/activate && cd v2_refactor && python3 main.py --promotions` |

## 6. Verificar que funcione

```bash
# Ver logs
tail -f ~/magic-chatbot/v2_refactor/logs/app_$(date +%Y-%m-%d).log

# Ver que el bot responda
# Enviar /start a tu bot desde Telegram
```

## 7. GitHub Secrets (para CI/CD)

En GitHub → Settings → Secrets and variables → Actions → Añadir:
- `TELEGRAM_BOT_TOKEN`
- `GOOGLE_CREDENTIALS_JSON`
- `PYTHONANYWHERE_USERNAME`
- `PYTHONANYWHERE_API_TOKEN`
- `PYTHONANYWHERE_DOMAIN`
</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>