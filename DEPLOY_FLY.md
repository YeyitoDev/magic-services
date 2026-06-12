# Despliegue en Fly.io — Magic Chatbot v2

Guía para desplegar el bot (modo **polling**, 1 máquina) en Fly.io.
Los **jobs programados** corren por **GitHub Actions** (no en Fly).

---

## Arquitectura del despliegue

- **Bot (app `magic-services`)**: 1 sola máquina en polling 24/7.
- **Jobs**: GitHub Actions cron (`.github/workflows/*.yml`). No se despliega `fly.jobs.toml`.
- **Base de datos**: AWS RDS MySQL (externa, ya en producción).
- **Health check**: servidor HTTP mínimo en el puerto `8080` (`health_server.py`).

---

## Requisitos previos

1. Instalar flyctl:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```
2. Iniciar sesión:
   ```bash
   fly auth login
   ```

---

## 1. Crear la app (solo la primera vez)

Si la app `magic-services` aún no existe:
```bash
fly apps create magic-services
```

> Si ya existe, omite este paso.

---

## 2. Configurar los secrets

`.env` NO viaja a la imagen (está en `.gitignore` y `.dockerignore`).
Todas las variables deben cargarse como **secrets** de Fly.

### Secrets obligatorios (el bot no arranca sin estos)

```bash
fly secrets set \
  TELEGRAM_BOT_TOKEN="<token_bot_principal>" \
  DB_USER="yeyo_admin" \
  DB_PASSWORD="<password_prod>" \
  DB_HOST="magic-db-prd-original.cpmay4kgurq6.us-east-1.rds.amazonaws.com" \
  DB_NAME="magic-db-prd" \
  --app magic-services
```

### Secrets recomendados (funcionalidad completa)

```bash
fly secrets set \
  TELEGRAM_BOT_TOKEN_LINKS="<token_bot_productivo_para_links>" \
  TELEGRAM_BOT_USERNAME="magopagos_bot" \
  TELEGRAM_VALIDATOR_IDS="1555885694,1707092473" \
  TELEGRAM_VIP_GROUP_ID="-1002451833719" \
  DB_ENGINE="mysql+pymysql" \
  DB_PORT="3306" \
  AWS_ACCESS_KEY_ID="<aws_key>" \
  AWS_SECRET_ACCESS_KEY="<aws_secret>" \
  AWS_REGION="us-east-1" \
  AWS_DYNAMODB_TABLE="MAGIC-USER-SESSIONS-LOG" \
  GOOGLE_SHEETS_ID="<spreadsheet_id>" \
  GOOGLE_WSP_SPREADSHEET_ID="<wsp_spreadsheet_id>" \
  BETSAFE_PROMO_LINK="https://bit.ly/promobetsafemagic" \
  LOG_FORMAT="json" \
  --app magic-services
```

### Credenciales de Google (Vision + Sheets)

El archivo JSON NO está en la imagen. Se inyecta como secret y `startup.py`
lo escribe en `credentials/google.json` al arrancar.

Codifica el JSON en base64 y guárdalo como secret:
```bash
# macOS
fly secrets set GOOGLE_CREDENTIALS_JSON="$(base64 -i ../credentials/magic-chatbottelegram-948350ae1b51.json)" --app magic-services
```

> `GOOGLE_CREDENTIALS_PATH=./credentials/google.json` ya está fijado en `fly.toml`.

---

## 3. Desplegar

```bash
fly deploy --app magic-services
```

O automáticamente al hacer push a `main` (workflow `.github/workflows/fly-deploy.yml`).
Para que el deploy automático funcione, configura en GitHub el secret
`FLY_API_TOKEN`:
```bash
fly tokens create deploy --app magic-services
# Copia el token y agrégalo en GitHub → Settings → Secrets → Actions → FLY_API_TOKEN
```

---

## 4. Verificar

```bash
fly logs --app magic-services        # Ver logs en vivo
fly status --app magic-services      # Estado de la máquina
fly machine list --app magic-services
```

Debes ver:
- `✅ Health server listening on port 8080`
- `🤖 Iniciando bot en modo POLLING...`
- El health check en estado `passing`.

---

## ⚠️ Reglas importantes (polling)

1. **Una sola máquina.** Telegram solo permite UNA conexión `getUpdates` por
   token. `fly.toml` ya fuerza `min_machines_running = 1`,
   `auto_start_machines = false` y `auto_stop_machines = false`.
   NUNCA escales a 2+ máquinas con el mismo token o verás:
   `Conflict: terminated by other getUpdates request`.

2. **Deploy `immediate`.** Configurado en `fly.toml` para detener la máquina
   anterior antes de iniciar la nueva (evita el conflicto de getUpdates durante
   el deploy). El bot usa `drop_pending_updates=True` al reiniciar.

3. **El bot NO ejecuta jobs.** En modo polling no se inicia el scheduler.
   Los jobs corren por GitHub Actions.

---

## 5. Jobs por GitHub Actions

Los workflows ya existentes ejecutan los jobs vía cron:
- `cleanup-scheduled.yml` — limpieza de suscripciones vencidas
- `expiry-warnings.yml` — avisos de expiración
- `reminders-scheduled.yml` — recordatorios
- `reconcile-report.yml` — reportes de conciliación

Asegúrate de configurar en **GitHub → Settings → Secrets → Actions** las mismas
variables (`DB_*`, `TELEGRAM_*`, `TELETHON_API_ID`, `TELETHON_API_HASH`,
`TELETHON_SESSION`, `GOOGLE_CREDENTIALS_JSON`, `AWS_*`) que usan esos workflows.

> No despliegues `fly.jobs.toml` para evitar **doble ejecución** de los jobs.

---

## Rollback / reinicio

```bash
fly apps restart magic-services          # Reiniciar la máquina
fly releases --app magic-services        # Ver historial de releases
fly deploy --image <release_anterior>    # Volver a una versión previa
```
