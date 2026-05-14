# Magic Chatbot v2 - Guía de Operaciones

> **Versión:** 2.0.0  
> **Entorno:** Python 3.12+ · SQLAlchemy 2.0 · python-telegram-bot 20+  
> **Última actualización:** Mayo 2025

---

## 🏗️ Arquitectura

Magic Chatbot v2 sigue una **arquitectura en capas** con inyección de dependencias (IoC) y principios SOLID. Cada capa tiene una responsabilidad única y las dependencias fluyen hacia abajo.

```
┌─────────────────────────────────────────────────┐
│                    main.py                       │  ← Punto de entrada
│         (polling / webhook / jobs / cleanup)     │
├──────────────┬──────────────────────────────────┤
│   api/       │         handlers/                │  ← Capa de presentación
│  (Flask)     │  (commands, callbacks, messages) │
├──────────────┴──────────────────────────────────┤
│                services/                         │  ← Capa de negocio
│  (user, subscription, payment, promotion,       │
│   reminder, google_sheets, google_vision)       │
├─────────────────────────────────────────────────┤
│              repositories/                       │  ← Capa de acceso a datos
│  (user_repo, purchase_repo, subscription_repo,  │
│   service_repo, selected_service_repo)          │
├─────────────────────────────────────────────────┤
│                models/                           │  ← Modelos ORM
│  (User, Purchase, Subscription, Service,        │
│   ServicePrice, SelectedService)               │
├─────────────────────────────────────────────────┤
│              core/                               │  ← Infraestructura
│  (database.py, container.py)                    │
├─────────────────────────────────────────────────┤
│              config/                             │  ← Configuración
│  (settings.py - 12-Factor App)                  │
└─────────────────────────────────────────────────┘
```

### Flujo de dependencias

```
config/settings.py  →  Lee .env, expone Settings singleton
        ↓
core/database.py    →  Crea engine SQLAlchemy y SessionLocal
        ↓
core/container.py   →  Contenedor IoC: registra repositorios y servicios
        ↓
repositories/       →  Acceso a datos (CRUD sobre modelos)
        ↓
services/           →  Lógica de negocio (usa repositorios vía contenedor)
        ↓
handlers/           →  Handlers de Telegram (reciben servicios por constructor)
        ↓
main.py             →  Construye la app, registra handlers, ejecuta el bot
```

### Principios aplicados

- **12-Factor App:** Toda la configuración desde variables de entorno.
- **Dependency Injection:** El contenedor (`core/container.py`) resuelve dependencias. Los handlers nunca instancian servicios directamente.
- **Fail-fast:** `settings.validate()` al arranque detecta variables faltantes y aborta inmediatamente.
- **Separation of Concerns:** Handlers solo orquestan; la lógica de negocio reside en `services/`.
- **Repository Pattern:** Los servicios acceden a datos a través de repositorios, nunca con queries inline.

---

## ⚙️ Configuración

### Variables de entorno (.env)

Todas las variables se leen desde el archivo `.env` ubicado en el directorio de trabajo (`v2_refactor/`). La clase `Settings` en `config/settings.py` las expone con validación automática.

#### 🌐 TELEGRAM

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ SÍ | — | Token del bot obtenido de @BotFather |
| `TELEGRAM_BOT_USERNAME` | ❌ | `magopagos_bot` | Username del bot (sin @) |
| `TELEGRAM_VALIDATOR_IDS` | ❌ | `6475885611` | IDs de validadores autorizados (separados por coma) |
| `TELEGRAM_VIP_GROUP_ID` | ❌ | `-1002451833719` | ID del grupo VIP para invitaciones |
| `TELEGRAM_WEBHOOK_URL` | ❌ (solo prod) | — | URL completa del webhook (ej: `https://tudominio.com/api/v1/telegram/webhook`) |

#### 🗄️ DATABASE (MySQL)

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `DB_ENGINE` | ❌ | `mysql+pymysql` | Driver SQLAlchemy |
| `DB_USER` | ✅ SÍ | — | Usuario de MySQL |
| `DB_PASSWORD` | ✅ SÍ | — | Contraseña de MySQL |
| `DB_HOST` | ✅ SÍ | — | Host del servidor MySQL |
| `DB_PORT` | ❌ | `3306` | Puerto de MySQL |
| `DB_NAME` | ✅ SÍ | — | Nombre de la base de datos |
| `DB_POOL_SIZE` | ❌ | `5` | Conexiones en el pool |
| `DB_MAX_OVERFLOW` | ❌ | `10` | Conexiones extra sobre el pool |
| `DB_POOL_TIMEOUT` | ❌ | `30` | Timeout en segundos para obtener conexión |

> **Nota:** `DATABASE_URL` es una propiedad computada que se construye automáticamente:  
> `mysql+pymysql://user:pass@host:port/dbname`

#### 🔑 GOOGLE CLOUD

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `GOOGLE_CREDENTIALS_PATH` | ❌ | `./credentials/magic-chatbottelegram-948350ae1b51.json` | Ruta al JSON de service account (dev local) |
| `GOOGLE_CREDENTIALS_JSON` | ❌ (prod) | — | Contenido completo del JSON como string (producción/CI) |
| `GOOGLE_SHEETS_ID` | ❌ | — | ID de la Google Sheet de datos de usuarios |
| `GOOGLE_WSP_SPREADSHEET_ID` | ❌ | — | ID de la Google Sheet de pagos WhatsApp |
| `GOOGLE_SHEETS_WORKSHEET_NAME` | ❌ | `datos_usuarios` | Nombre de la hoja de trabajo |

#### ☁️ AWS

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | ❌ | — | AWS Access Key (para DynamoDB) |
| `AWS_SECRET_ACCESS_KEY` | ❌ | — | AWS Secret Key |
| `AWS_REGION` | ❌ | `us-east-1` | Región AWS |
| `AWS_DYNAMODB_TABLE` | ❌ | `MAGIC-USER-SESSIONS-LOG` | Tabla DynamoDB para pipeline de promociones |

#### 🌐 FLASK API

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `FLASK_HOST` | ❌ | `0.0.0.0` | Host del servidor Flask |
| `FLASK_PORT` | ❌ | `5000` | Puerto del servidor Flask |
| `FLASK_SECRET_KEY` | ❌ | `change-me-in-production` | Secret key de Flask (¡cambiar en producción!) |
| `API_KEY` | ❌ | — | API Key para proteger endpoints REST |
| `ALLOWED_HOSTS` | ❌ | `localhost,127.0.0.1` | Hosts permitidos (coma-separados) |
| `CORS_ORIGINS` | ❌ | `http://localhost:3000` | Orígenes CORS permitidos |

#### 🕐 JOBS / SCHEDULER

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `ENABLE_JOBS` | ❌ | `false` | Habilitar scheduler de jobs programados |
| `JOB_REMINDER_INTERVAL_MINUTES` | ❌ | `10` | Intervalo en minutos para recordatorios de compra |
| `JOB_SUBSCRIPTION_CHECK_HOUR` | ❌ | `0` | Hora del día (0-23) para verificar suscripciones vencidas |
| `JOB_CLEANUP_HOUR` | ❌ | `3` | Hora del día para limpieza de suscripciones expiradas |
| `TIMEZONE` | ❌ | `America/Lima` | Zona horaria para jobs programados |

#### 📦 APPLICATION

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `ENVIRONMENT` | ❌ | `testing` | Entorno: `testing` o `production` |
| `DEBUG` | ❌ | `true` | Activar modo debug (logs SQL, Flask debug) |
| `LOG_LEVEL` | ❌ | `INFO` | Nivel de logging: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | ❌ | `text` | Formato de logs: `text` o `json` |
| `LOG_FILE_PATH` | ❌ | `./logs` | Directorio de archivos de log |
| `LOG_FILE_MAX_SIZE` | ❌ | `10485760` | Tamaño máximo de archivo de log (10 MB) |
| `LOG_FILE_BACKUP_COUNT` | ❌ | `5` | Número de archivos de backup rotados |

#### 🚀 PYTHONANYWHERE (Deploy)

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `PYTHONANYWHERE_DOMAIN` | ❌ (solo prod) | — | Dominio en PythonAnywhere (ej: `tunombre.pythonanywhere.com`) |
| `PYTHONANYWHERE_USERNAME` | ❌ (solo prod) | — | Usuario de PythonAnywhere |

---

### Ambientes

| Ambiente | Archivo | Descripción |
|---|---|---|
| **testing** | `.env.testing` | Desarrollo y QAS. Debug activado, jobs desactivados, DB local. |
| **production** | `.env.example` | Plantilla para producción. Completar TODAS las credenciales. |

```bash
# Setup para testing (desarrollo local)
cp .env.testing .env

# Setup para producción (completar credenciales manualmente)
cp .env.example .env
# Luego editar .env con valores reales
nano .env
```

> ⚠️ **Importante:** `.env` NUNCA se commitea a Git. Está listado en `.gitignore`. Usa los archivos `.env.testing` y `.env.example` como templates.

---

## 🚀 Ejecución

### Requisitos previos

```bash
# 1. Activar entorno virtual
source .venv/bin/activate

# 2. Instalar dependencias
cd v2_refactor
pip install -r requirements.txt

# 3. Verificar que .env existe
ls -la .env
```

### Iniciar el bot

```bash
# Activar entorno virtual (si no está activo)
source .venv/bin/activate
cd v2_refactor

# ─── Modo polling (desarrollo local) ───
# El bot consulta a Telegram cada 1 segundo por nuevos mensajes.
# Ideal para desarrollo y testing.
python3 main.py

# ─── Modo webhook (producción PythonAnywhere) ───
# Telegram envía updates vía HTTP POST. Requiere Flask.
# Debe configurarse TELEGRAM_WEBHOOK_URL en .env
python3 main.py --mode webhook

# ─── Bot + Jobs en paralelo ───
# Corre el bot y los jobs programados en hilos separados.
python3 main.py --all

# ─── En segundo plano (nohup) ───
nohup python3 main.py >> logs/bot_output.log 2>&1 &

# ─── Eliminar webhook y salir ───
# Útil cuando necesitas cambiar de webhook a polling.
python3 main.py --remove-webhook
```

### Jobs programados

```bash
# Pipeline de limpieza de suscripciones (SOLO REPORTE - no elimina usuarios)
# Compara miembros del grupo VIP vs BD y genera reportes de quién debería salir.
python3 main.py --cleanup

# Pipeline de promociones BetSafe
# Escanea DynamoDB, evalúa timestamps y envía promos según etapa del pipeline.
python3 main.py --promotions

# Solo jobs programados (sin bot)
# Ejecuta el scheduler con todos los jobs registrados.
python3 main.py --jobs-only
```

### Jobs batch independientes

El módulo `jobs/promotion_batch.py` puede ejecutarse directamente:

```bash
# Ejecución única (promociones + recordatorios)
python3 -m jobs.promotion_batch

# Modo daemon (loop cada N minutos)
python3 -m jobs.promotion_batch --daemon --interval 10

# Solo promociones, sin recordatorios
python3 -m jobs.promotion_batch --skip-reminders

# Solo recordatorios, sin promociones
python3 -m jobs.promotion_batch --skip-promotions
```

---

### Comandos del bot en Telegram

| Comando | Args | Función | Quién puede usarlo |
|---|---|---|---|
| `/start` | — | Registra al usuario, muestra el menú principal estilo "Don Gato" | Todos |
| `/vm` | `<user_id>` `<msg_id>` `<monto>` `[fecha]` | Validar/corregir monto manualmente. Útil cuando el OCR falla. | Solo validadores |
| `/wsp` | `<codigo_wsp>` | Registrar pago realizado por WhatsApp. Busca en Google Sheets el código WSP. | Solo validadores |
| `/valid` | `<codigo>` | Reclamar compra registrada desde API externa (CSV). Procesa el código de la plataforma externa. | Todos |
| `/id` | — | Muestra tu ID de Telegram (necesario para soporte y validaciones) | Todos |
| `/help` | — | Redirige a `/start`, muestra el menú principal | Todos |
| `/servicio_id` | — | Muestra el ID del servicio actualmente seleccionado | Todos |
| `/generar_link` | — | Genera link de invitación al grupo VIP (solo si tienes suscripción activa) | Usuarios con suscripción activa |
| `/mensaje_recordatorio` | — | Envía mensaje recordatorio con foto y precios al usuario | Solo validadores |

### Flujo de uso típico

1. **Usuario envía `/start`** → Se registra en BD, ve menú principal con botones:
   - 📊 Información de Servicios
   - 💰 Comprar Servicio
   - ❓ FAQ / Preguntas Frecuentes

2. **Usuario selecciona "Comprar Servicio"** → Elige Stake o Grupo VIP → Ve precios y duración.

3. **Usuario presiona "Comprar"** → El bot le indica el monto exacto y la cuenta a donde depositar.

4. **Usuario envía foto del comprobante** → El bot procesa la imagen:
   - Si tiene OCR (Google Vision): extrae monto y fecha automáticamente.
   - Sin OCR: un validador revisa manualmente con `/vm`.

5. **Validador aprueba o rechaza** → El bot notifica al usuario y, si es aprobado, lo agrega al grupo VIP.

---

## 📊 Sistema de Logs

### Estructura de directorios

```
logs/
├── app_YYYY-MM-DD.log          # INFO+: Log general estructurado
├── error_YYYY-MM-DD.log        # ERROR+: Solo errores y críticos
├── bot_output.log              # Salida de nohup (stdout/stderr combinados)
├── domain/
│   ├── payment_YYYY-MM-DD.log  # Transacciones de pago (recibido, validado, rechazado)
│   └── audit_YYYY-MM-DD.log    # Auditoría (kicks, bans, expiraciones, creaciones)
└── archive/
    └── YYYY-MM/                # Logs antiguos comprimidos (.gz)
        ├── app_YYYY-MM-DD.gz
        └── error_YYYY-MM-DD.gz
```

### Funcionalidades del logger (`utils/logger.py`)

- **Rotación diaria automática:** Los archivos rotan a medianoche (hora local).
- **Compresión de archivos antiguos:** Logs de días anteriores se comprimen a `.gz` en `archive/YYYY-MM/`.
- **Formato dual:** `text` (legible por humanos) o `json` (estructurado para ELK/Splunk).
- **Domain loggers:** `PaymentLogger` y `AuditLogger` para trazabilidad de transacciones y auditoría.
- **TelegramAlertHandler:** Envía errores críticos a los validadores por Telegram.
- **HealthCheck:** Ping periódico para monitoreo de salud del sistema.

### Configuración

```bash
# En .env:
LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=text          # text o json
LOG_FILE_PATH=./logs     # Directorio de logs
LOG_FILE_MAX_SIZE=10485760   # 10 MB
LOG_FILE_BACKUP_COUNT=5      # 5 backups rotados
```

---

## 🗄️ Base de Datos

### Diagrama de tablas

```
┌──────────────────┐       ┌──────────────────────┐
│     users         │       │     services          │
├──────────────────┤       ├──────────────────────┤
│ telegram_id (PK) │──┐    │ service_id (PK)       │──┐
│ telegram_name    │  │    │ name (unique)         │  │
└──────────────────┘  │    │ description           │  │
         │            │    │ is_subscription       │  │
         │            │    └──────────────────────┘  │
         │            │               │              │
    ┌────┴────┐  ┌────┴────┐   ┌──────┴──────┐      │
    │ purchases│  │selected │   │service_prices│      │
    ├─────────┤  │_services│   ├─────────────┤      │
    │purchase │  ├─────────┤   │service_price│      │
    │_id (PK) │  │user_tel.│   │_id (PK)     │      │
    │user_tel.│  │(PK/FK)  │   │service_id(FK)│─────┘
    │service  │  │service  │   │price        │
    │_id (FK) │  │_id (FK) │   │discount     │
    │price    │  │selected │   │duration_mon.│
    │from_chan│  │_date    │   └─────────────┘
    │purchase │  │reminder │
    │_date    │  └─────────┘
    └─────────┘
         │
    ┌────┴───────────┐
    │ subscriptions  │
    ├────────────────┤
    │subscription_id │
    │user_telegram_id│
    │service_id (FK) │──┘
    │start_date      │
    │end_date        │
    └────────────────┘
```

### Descripción de tablas

| Tabla | Propósito | PK |
|---|---|---|
| `users` | Usuarios registrados en el bot | `telegram_id` (BigInteger) |
| `services` | Servicios ofrecidos (Stake, Grupo VIP) | `service_id` (Integer, autoincrement) |
| `service_prices` | Precios por servicio, con descuento y duración en meses | `service_price_id` (Integer, autoincrement) |
| `purchases` | Registro de cada compra realizada | `purchase_id` (BigInteger, autoincrement) |
| `subscriptions` | Suscripciones activas con fecha de inicio y fin | `subscription_id` (BigInteger, autoincrement) |
| `selected_services` | Servicio actualmente en el "carrito" del usuario y recordatorios enviados | `user_telegram_id` (BigInteger, PK/FK) |

### Inicialización

Las tablas se crean automáticamente al iniciar el bot gracias a `Base.metadata.create_all()` en `core/database.py → init_db()`. No se requiere ejecutar scripts SQL manualmente.

---

## 🔑 Credenciales Google

El sistema soporta dos métodos para cargar las credenciales de Google Cloud (Service Account):

### Método 1: Variable de entorno (producción / CI/CD) ⭐ Recomendado

```bash
# En .env de producción:
GOOGLE_CREDENTIALS_JSON='{"type":"service_account","project_id":"...","private_key":"..."}'
```

En GitHub Actions, configura el secreto `GOOGLE_CREDENTIALS_JSON` con el JSON completo.

### Método 2: Archivo JSON local (desarrollo)

```bash
# En .env de desarrollo:
GOOGLE_CREDENTIALS_PATH=./credentials/magic-chatbottelegram-948350ae1b51.json
```

Coloca el archivo JSON de la service account en `./credentials/`.

### Servicios que usan Google Cloud

| Servicio | Archivo | Propósito |
|---|---|---|
| Google Sheets | `services/google_sheets.py` | Leer datos de usuarios y códigos WSP |
| Google Vision | `services/google_vision.py` | OCR para extraer montos/fechas de comprobantes |

> Si no hay credenciales configuradas, el bot funciona sin OCR (los validadores procesan manualmente con `/vm`).

---

## 🧪 Tests

### Ejecutar tests

```bash
# Todos los tests con output verboso
python3 -m pytest tests/ -v

# Con cobertura
python3 -m pytest tests/ --cov=. --cov-report=html

# Con cobertura XML (para CI/CD)
python3 -m pytest tests/ --cov=. --cov-report=xml --cov-report=term

# Un archivo específico
python3 -m pytest tests/test_user_repo.py -v

# Un test específico
python3 -m pytest tests/test_user_repo.py::test_create_user -v
```

### Estructura de tests

```
tests/
├── __init__.py
└── conftest.py         # Fixtures compartidas (BD en memoria SQLite, mocks, datos de prueba)
```

### Fixtures disponibles (`conftest.py`)

| Fixture | Scope | Descripción |
|---|---|---|
| `engine` | session | Engine SQLAlchemy con SQLite en memoria |
| `tables` | session | Crea/destruye todas las tablas |
| `db_session` | function | Sesión aislada con rollback automático |
| `user_repo` | function | UserRepository con BD de test |
| `service_repo` | function | ServiceRepository con BD de test |
| `purchase_repo` | function | PurchaseRepository con BD de test |
| `subscription_repo` | function | SubscriptionRepository con BD de test |
| `sample_user` | function | Usuario de prueba pre-cargado |
| `sample_service` | function | Servicios Stake + Grupo VIP con precios |
| `sample_subscription` | function | Suscripción activa de prueba |
| `sample_purchase` | function | Compra de prueba |
| `user_service` | function | UserService real sobre BD de test |
| `subscription_service` | function | SubscriptionService real sobre BD de test |
| `payment_service` | function | PaymentService real sobre BD de test |
| `mock_user_repo` | function | UserRepository mockeado (tests unitarios) |
| `mock_bot` | function | Bot de Telegram mockeado |
| `mock_update` | function | Update de Telegram mockeado |
| `mock_context` | function | ContextTypes mockeado |
| `mock_settings_env` | function | Variables de entorno para tests (autouse) |

### Ejemplo de test

```python
# tests/test_user_repo.py
def test_create_user(user_repo, db_session):
    """Crear un usuario nuevo debe persistirlo en BD."""
    user = user_repo.create(telegram_id=99999, telegram_name="Test User")
    
    assert user.telegram_id == 99999
    assert user.telegram_name == "Test User"
    
    # Verificar que se persistió
    found = user_repo.get_by_telegram_id(99999)
    assert found is not None
    assert found.telegram_name == "Test User"
```

---

## 📦 Deploy a PythonAnywhere

### Requisitos previos

1. Cuenta en [PythonAnywhere](https://www.pythonanywhere.com) (plan Hacker o superior para webhooks).
2. Repositorio Git con el código.
3. Variables de entorno configuradas.

### Paso a paso manual

```bash
# 1. Conectarse a PythonAnywhere por SSH o abrir una Bash Console

# 2. Clonar el repositorio
git clone https://github.com/tuusuario/magic-chatbot.git
cd magic-chatbot/v2_refactor

# 3. Crear entorno virtual e instalar dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Configurar .env para producción
cp .env.example .env
nano .env   # Completar TODAS las credenciales:
            # TELEGRAM_BOT_TOKEN, DB_USER, DB_PASSWORD, DB_HOST, DB_NAME
            # GOOGLE_CREDENTIALS_JSON (el JSON completo como string)
            # TELEGRAM_WEBHOOK_URL=https://tudominio.pythonanywhere.com/api/v1/telegram/webhook
            # ENVIRONMENT=production
            # DEBUG=false

# 5. Configurar Web App en el dashboard de PythonAnywhere:
#    - Elegir "Manual configuration" con Python 3.12
#    - Configurar el path al entorno virtual: /home/tuusuario/magic-chatbot/v2_refactor/.venv
#    - Editar el archivo WSGI para apuntar a la app Flask

# 6. Contenido del archivo WSGI (/var/www/tuusuario_pythonanywhere_com_wsgi.py):
```

```python
import sys
import os

# Agregar el directorio del proyecto al PYTHONPATH
project_path = '/home/tuusuario/magic-chatbot/v2_refactor'
if project_path not in sys.path:
    sys.path.insert(0, project_path)

# Cargar variables de entorno desde .env
from dotenv import load_dotenv
load_dotenv(os.path.join(project_path, '.env'))

# Inicializar el sistema y crear la app Flask
from api.app import create_app
application = create_app()
```

```bash
# 7. Para tasks programadas (cron jobs en PythonAnywhere):
#    Ir a "Tasks" en el dashboard y configurar:

#    Recordatorios cada 10 minutos:
#    cd /home/tuusuario/magic-chatbot/v2_refactor && source .venv/bin/activate && python3 -m jobs.promotion_batch >> logs/cron_promotions.log 2>&1

#    Limpieza de suscripciones (diario a las 3 AM):
#    cd /home/tuusuario/magic-chatbot/v2_refactor && source .venv/bin/activate && python3 main.py --cleanup >> logs/cron_cleanup.log 2>&1

# 8. Recargar la Web App desde el dashboard
```

### Verificación post-deploy

```bash
# Health check
curl https://tudominio.pythonanywhere.com/api/v1/health

# Respuesta esperada:
# {"status":"ok","service":"Magic Chatbot API","version":"2.0.0","environment":"production",...}

# Hello test
curl https://tudominio.pythonanywhere.com/api/v1/hello
```

---

## 🔄 CI/CD (GitHub Actions)

### `ci.yml` - Integración Continua

Se ejecuta en cada push a `main`, `develop` y ramas `feature/**`, y en PRs hacia `main`.

```yaml
# Resumen del pipeline:
# 1. Checkout del código
# 2. Setup Python 3.12
# 3. Instalación de dependencias (requirements.txt + pytest + ruff)
# 4. Lint con Ruff
# 5. Creación de .env desde .env.example + secrets de GitHub
# 6. Ejecución de tests con cobertura
# 7. Upload de reporte de cobertura a Codecov
```

**Secrets requeridos en GitHub:**
- `TELEGRAM_BOT_TOKEN`: Token del bot de testing.
- `GOOGLE_CREDENTIALS_JSON`: JSON de service account (para tests de Google Sheets/Vision).

### `deploy.yml` - Deploy a PythonAnywhere

Se ejecuta en push a `main` o manualmente (`workflow_dispatch`).

```yaml
# Resumen del pipeline:
# 1. Checkout del código
# 2. Deploy vía jensvog/pythonanywhere-deploy-action
# 3. Notificación de éxito al validador por Telegram
```

**Secrets requeridos en GitHub:**
- `PYTHONANYWHERE_USERNAME`: Usuario de PythonAnywhere.
- `PYTHONANYWHERE_API_TOKEN`: API Token de PythonAnywhere.
- `PYTHONANYWHERE_DOMAIN`: Dominio de la web app (ej: `tunombre.pythonanywhere.com`).
- `TELEGRAM_BOT_TOKEN`: Token del bot para notificar deploy.

---

## 🐛 Troubleshooting

| Error | Causa | Solución |
|---|---|---|
| `Conflict: terminated by other getUpdates request` | Otra instancia del bot está corriendo en modo polling | `pkill -9 -f "python3 main.py"` o cambiar a webhook |
| `There is no text in the message to edit` | Se intentó editar texto en un mensaje que es una foto | Usar `_safe_edit_message()` que envía mensaje nuevo en vez de editar |
| `Button_data_invalid` | `callback_data` mal formado o excede 64 bytes | Revisar formato de montos y fechas en los callbacks |
| `created_at unknown column` | `TimestampMixin` no se aplicó correctamente en modelos legacy | Ya corregido en v2 con `__allow_unmapped__ = True` |
| `Can't connect to MySQL server` | Host/port/credenciales incorrectos o firewall | Verificar `.env`: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` |
| `Telegram API Unauthorized` | Token inválido o revocado | Verificar `TELEGRAM_BOT_TOKEN` con @BotFather |
| `Webhook not working / 404` | URL del webhook mal configurada | Verificar `TELEGRAM_WEBHOOK_URL` y que la ruta `/api/v1/telegram/webhook` exista |
| `No module named 'X'` | Dependencia faltante | `pip install -r requirements.txt` |
| `Google credentials not found` | Sin credenciales configuradas | Configurar `GOOGLE_CREDENTIALS_JSON` (prod) o `GOOGLE_CREDENTIALS_PATH` (dev) |
| `DynamoDB table not found` | Región incorrecta o tabla no existe | Verificar `AWS_REGION` y `AWS_DYNAMODB_TABLE` |
| Jobs no se ejecutan | `ENABLE_JOBS=false` | Cambiar a `ENABLE_JOBS=true` en `.env` |
| `peewee.InterfaceError` o error de BD legacy | Código viejo importando peewee en vez de SQLAlchemy | Buscar imports de peewee y migrar a SQLAlchemy/repositorios |
| El bot no responde después de horas | Conexión a MySQL expirada | Verificado con `pool_pre_ping=True` y `pool_recycle=3600` en v2 |
| `sys.exit(1)` al arrancar | Faltan variables de entorno requeridas | `settings.validate()` imprime las variables faltantes. Completarlas en `.env`. |

### Comandos de diagnóstico rápido

```bash
# Ver procesos del bot corriendo
ps aux | grep "python3 main.py"

# Matar todas las instancias
pkill -9 -f "python3 main.py"

# Ver logs en tiempo real
tail -f logs/app_*.log

# Ver solo errores recientes
tail -50 logs/error_*.log

# Verificar configuración
python3 -c "from config.settings import settings; print(settings.DATABASE_URL)"

# Test de conexión a BD
python3 -c "from core.database import engine; conn = engine.connect(); print('✅ BD OK'); conn.close()"

# Test de token de Telegram
python3 -c "
import requests
from config.settings import settings
r = requests.get(f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe')
print(r.json())
"

# Ver webhook info
python3 -c "
import asyncio
from config.settings import settings
from telegram import Bot
async def check():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    info = await bot.get_webhook_info()
    print(info)
asyncio.run(check())
"
```

---

## 📂 Estructura completa del proyecto

```
v2_refactor/
├── main.py                    # Punto de entrada principal
├── requirements.txt           # Dependencias del proyecto
├── pyproject.toml             # Config de Ruff, Pytest, Coverage
├── .env                       # Variables de entorno (NO commiteado)
├── .env.testing               # Template para testing
├── .env.example               # Template para producción
│
├── config/                    # ⚙️ Configuración
│   ├── __init__.py
│   └── settings.py            # Settings singleton con validación
│
├── core/                      # 🏗️ Infraestructura
│   ├── __init__.py
│   ├── database.py            # Engine SQLAlchemy, SessionLocal, init_db()
│   └── container.py           # Contenedor IoC (registro/resolución de servicios)
│
├── models/                    # 📊 Modelos ORM (SQLAlchemy)
│   ├── __init__.py
│   ├── base.py                # Base, BaseModel, TimestampMixin
│   ├── user.py                # User
│   ├── service.py             # Service, ServicePrice
│   ├── purchase.py            # Purchase
│   ├── subscription.py        # Subscription
│   └── selected_service.py    # SelectedService (carrito + recordatorios)
│
├── repositories/              # 🗃️ Acceso a datos (Repository Pattern)
│   ├── __init__.py
│   ├── base.py                # BaseRepository genérico
│   ├── user_repo.py
│   ├── service_repo.py
│   ├── purchase_repo.py
│   ├── subscription_repo.py
│   └── selected_service_repo.py
│
├── services/                  # 🧠 Lógica de negocio
│   ├── __init__.py
│   ├── user_service.py
│   ├── subscription_service.py
│   ├── payment_service.py
│   ├── promotion_service.py   # Pipeline BetSafe vía DynamoDB
│   ├── reminder_service.py    # Recordatorios de compra pendiente
│   ├── google_credentials.py  # Carga flexible de credenciales Google
│   ├── google_sheets.py       # Lectura/escritura en Google Sheets
│   ├── google_vision.py       # OCR de comprobantes
│   └── telegram_api.py        # Cliente de Telegram (invitaciones, kicks)
│
├── handlers/                  # 🎮 Handlers de Telegram
│   ├── __init__.py
│   ├── commands.py            # /start, /vm, /wsp, /valid, /id, etc.
│   ├── callbacks.py           # Botones inline (menús, compras, validación)
│   ├── messages.py            # Mensajes de texto e imágenes
│   └── errors.py              # Manejador global de errores
│
├── jobs/                      # 🕐 Tareas programadas
│   ├── __init__.py
│   ├── scheduler.py           # APScheduler: registra todos los jobs
│   ├── subscription_cleanup.py # Limpieza de suscripciones vencidas
│   └── promotion_batch.py     # Batch: promociones + recordatorios
│
├── api/                       # 🌐 API REST (Flask)
│   ├── __init__.py
│   ├── app.py                 # Factory: create_app()
│   └── routes.py              # Endpoints REST
│
├── utils/                     # 🛠️ Utilidades
│   ├── __init__.py
│   ├── logger.py              # Logger con rotación, domain loggers, Telegram alerts
│   ├── keyboards.py           # Teclados inline del bot
│   ├── decorators.py          # Decoradores reutilizables
│   ├── datetime_utils.py      # Utilidades de fechas y timezone
│   └── text_parser.py         # Parseo de montos y fechas
│
├── tests/                     # 🧪 Tests
│   ├── __init__.py
│   └── conftest.py            # Fixtures compartidas
│
├── logs/                      # 📊 Archivos de log
│   ├── domain/                # Logs de dominio (pagos, auditoría)
│   └── archive/               # Logs comprimidos por mes
│
├── images/                    # 🖼️ Comprobantes de pago recibidos
├── output/                    # 📄 Reportes de jobs
├── csv/                       # 📋 Datos CSV de API externa
└── estados/                   # 📌 Estados de validación (legacy compat)
```

---

## 🔐 Endpoints de la API REST

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/api/v1/health` | Público | Health check con versión y timestamp |
| `GET` | `/api/v1/hello` | Público | Endpoint de prueba |
| `POST` | `/api/v1/register_service_payment` | API Key | Registrar pago desde plataforma externa |
| `POST` | `/api/v1/payments/validate` | API Key | Validar pago manualmente vía API |
| `GET` | `/api/v1/stats` | API Key | Estadísticas del sistema |
| `POST` | `/api/v1/telegram/webhook` | Telegram | Webhook para recibir updates de Telegram |

### Ejemplo: Registrar pago externo

```bash
curl -X POST https://tudominio.pythonanywhere.com/api/v1/register_service_payment \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-api-key" \
  -d '{
    "id": "unique_id_123",
    "from_channel": "whatsapp",
    "name": "Juan Perez",
    "date": "2025-05-07",
    "amount": 150.00,
    "service": "grupo_vip"
  }'
```

---

## 📞 Soporte

Para problemas, dudas o asistencia:
- **Telegram:** @magic_peru
- **Logs:** Revisar `logs/error_YYYY-MM-DD.log` para errores detallados.
- **Health check:** `GET /api/v1/health` para verificar estado del servicio.

---

**Magic Chatbot v2** · Construido con ❤️ por el equipo Magic · Arquitectura refactorizada 2025