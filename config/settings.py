"""
Centralized Settings Management - Magic Chatbot v2
===================================================
Lee todas las variables de entorno usando python-dotenv y las expone
a través de una clase Settings con validación automática.

Entornos soportados:
- testing: Desarrollo y pruebas (QAS). Debug activado, jobs desactivados.
- production: Producción (PythonAnywhere). Debug desactivado.

Principios aplicados:
- 12-Factor App: toda la configuración desde variables de entorno.
- Fail-fast: validate() detecta variables requeridas faltantes al arranque.
- Computed properties: DATABASE_URL se construye a partir de sus partes.

Uso:
    from config.settings import settings
    token = settings.TELEGRAM_BOT_TOKEN
"""

import os

from dotenv import load_dotenv

# Cargar .env al importar el módulo (busca en el directorio de trabajo)
load_dotenv()


class Settings:
    """
    Configuración centralizada de la aplicación.

    Todas las variables se leen del entorno con valores por defecto seguros.
    Las credenciales y secrets NUNCA tienen valor por defecto en producción.

    Entornos válidos:
    - testing: Entorno de desarrollo/pruebas (QAS).
    - production: Entorno productivo (PythonAnywhere).
    """

    # ============================================================
    # APPLICATION
    # ============================================================
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "testing")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "MagoChatbot")
    PROJECT_VERSION: str = os.getenv("PROJECT_VERSION", "2.3.0")

    # ============================================================
    # TELEGRAM
    # ============================================================
    TELEGRAM_BOT_TOKEN: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_BOT_USERNAME: str = os.getenv("TELEGRAM_BOT_USERNAME", "magopagos_bot")

    @property
    def TELEGRAM_VALIDATOR_IDS(self) -> list[str]:  # noqa: N802
        """
        IDs de Telegram de los validadores autorizados (separados por coma).

        Solo estos usuarios pueden validar/rechazar pagos.
        Por defecto: 6475885611 (único validador para testing y producción).
        """
        raw: str = os.getenv("TELEGRAM_VALIDATOR_IDS", "6475885611")
        return [uid.strip() for uid in raw.split(",") if uid.strip()]

    TELEGRAM_VIP_GROUP_ID: str = os.getenv(
        "TELEGRAM_VIP_GROUP_ID", "-1002451833719"
    )
    TELEGRAM_WEBHOOK_URL: str | None = os.getenv("TELEGRAM_WEBHOOK_URL")

    @property
    def TELEGRAM_DEFAULT_VIP_LINK(self) -> str:  # noqa: N802
        """Link de invitación por defecto cuando no se puede generar uno nuevo."""
        return os.getenv("TELEGRAM_DEFAULT_VIP_LINK", "https://t.me/+VllSzEZ2smk2MTk5")

    # ============================================================
    # DATABASE (MySQL via SQLAlchemy)
    # ============================================================
    DB_ENGINE: str = os.getenv("DB_ENGINE", "mysql+pymysql")
    DB_USER: str | None = os.getenv("DB_USER")
    DB_PASSWORD: str | None = os.getenv("DB_PASSWORD")
    DB_HOST: str | None = os.getenv("DB_HOST")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_NAME: str | None = os.getenv("DB_NAME")

    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))

    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        """URL de conexión computada a partir de componentes individuales."""
        if not all([self.DB_USER, self.DB_PASSWORD, self.DB_HOST, self.DB_NAME]):
            return ""
        return (
            f"{self.DB_ENGINE}://{self.DB_USER}:{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ============================================================
    # GOOGLE CLOUD
    # ============================================================
    GOOGLE_CREDENTIALS_PATH: str = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        "./credentials/magic-chatbottelegram-948350ae1b51.json",
    )
    GOOGLE_SHEETS_ID: str | None = os.getenv("GOOGLE_SHEETS_ID")
    GOOGLE_WSP_SPREADSHEET_ID: str | None = os.getenv("GOOGLE_WSP_SPREADSHEET_ID")
    GOOGLE_SHEETS_WORKSHEET_NAME: str = os.getenv(
        "GOOGLE_SHEETS_WORKSHEET_NAME", "datos_usuarios"
    )

    # ============================================================
    # AWS
    # ============================================================
    AWS_ACCESS_KEY_ID: str | None = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_DYNAMODB_TABLE: str = os.getenv("AWS_DYNAMODB_TABLE", "MAGIC-USER-SESSIONS-LOG")

    # ============================================================
    # BETSAFE - LINKS PROMOCIONALES
    # ============================================================
    BETSAFE_PROMO_LINK: str = os.getenv(
        "BETSAFE_PROMO_LINK",
        "https://bit.ly/promobetsafemagic",
    )
    BETSAFE_BUTTON_TEXT: str = os.getenv(
        "BETSAFE_BUTTON_TEXT", "¡OBTÉN TUS 70 SOLES GRATIS!"
    )

    # ============================================================
    # FLASK API
    # ============================================================
    FLASK_HOST: str = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
    FLASK_SECRET_KEY: str = os.getenv(
        "FLASK_SECRET_KEY", "change-me-in-production"
    )
    API_KEY: str | None = os.getenv("API_KEY")

    # ============================================================
    # JOBS / SCHEDULER
    # ============================================================
    JOB_REMINDER_INTERVAL_MINUTES: int = int(
        os.getenv("JOB_REMINDER_INTERVAL_MINUTES", "10")
    )
    JOB_SUBSCRIPTION_CHECK_HOUR: str = os.getenv(
        "JOB_SUBSCRIPTION_CHECK_HOUR", "0"
    )
    JOB_CLEANUP_HOUR: str = os.getenv("JOB_CLEANUP_HOUR", "3")
    ENABLE_JOBS: bool = os.getenv("ENABLE_JOBS", "false").lower() == "true"
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Lima")

    # ============================================================
    # LOGGING
    # ============================================================
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")
    LOG_FILE_PATH: str = os.getenv("LOG_FILE_PATH", "./logs")
    LOG_FILE_MAX_SIZE: int = int(os.getenv("LOG_FILE_MAX_SIZE", "10485760"))  # 10MB
    LOG_FILE_BACKUP_COUNT: int = int(os.getenv("LOG_FILE_BACKUP_COUNT", "5"))

    # ============================================================
    # PYTHONANYWHERE (Deployment)
    # ============================================================
    PYTHONANYWHERE_DOMAIN: str | None = os.getenv("PYTHONANYWHERE_DOMAIN")
    PYTHONANYWHERE_USERNAME: str | None = os.getenv("PYTHONANYWHERE_USERNAME")

    # ============================================================
    # CORS / SECURITY
    # ============================================================
    ALLOWED_HOSTS: list[str] = os.getenv(
        "ALLOWED_HOSTS", "localhost,127.0.0.1"
    ).split(",")
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000"
    ).split(",")
    SESSION_SECRET: str | None = os.getenv("SESSION_SECRET")

    # ============================================================
    # MÉTODOS DE VALIDACIÓN Y UTILIDAD
    # ============================================================

    def validate(self, raise_exception: bool = True) -> list[str]:
        """
        Valida que todas las variables de entorno requeridas estén definidas.

        Args:
            raise_exception: Si True, lanza ValueError con los campos faltantes.

        Returns:
            Lista de nombres de variables faltantes (vacía si todo ok).

        Raises:
            ValueError: Si hay variables requeridas faltantes y raise_exception=True.
        """
        required_vars: dict = {
            "TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN,
            "DB_USER": self.DB_USER,
            "DB_PASSWORD": self.DB_PASSWORD,
            "DB_HOST": self.DB_HOST,
            "DB_NAME": self.DB_NAME,
        }

        missing: list[str] = [
            name for name, value in required_vars.items() if not value
        ]

        if missing and raise_exception:
            raise ValueError(
                f"Faltan variables de entorno requeridas: {', '.join(missing)}\n"
                f"Copia .env.testing o .env.example a .env y completa los valores.\n"
                f"Para testing: copia .env.testing → .env\n"
                f"Para producción: copia .env.example → .env y completa todos los campos."
            )

        return missing

    def is_production(self) -> bool:
        """
        Verifica si la aplicación corre en entorno de producción.

        Returns:
            True si ENVIRONMENT == 'production'.
        """
        return self.ENVIRONMENT == "production"

    def is_testing(self) -> bool:
        """
        Verifica si la aplicación corre en entorno de testing/pruebas.

        Returns:
            True si ENVIRONMENT == 'testing'.
        """
        return self.ENVIRONMENT == "testing"

    def is_development(self) -> bool:
        """
        Alias para is_testing(). Mantenido por compatibilidad con código legacy.

        Returns:
            True si es entorno testing.
        """
        return self.is_testing()

    def get_db_url(self) -> str:
        """Retorna la URL de conexión a la base de datos."""
        return self.DATABASE_URL

    def get_validator_ids(self) -> list[str]:
        """
        Retorna la lista de IDs de validadores autorizados.

        Returns:
            Lista de strings con los IDs de Telegram de los validadores.
        """
        return self.TELEGRAM_VALIDATOR_IDS

    def is_validator(self, telegram_id: int) -> bool:
        """
        Verifica si un usuario de Telegram es un validador autorizado.

        Args:
            telegram_id: ID de Telegram del usuario a verificar.

        Returns:
            True si el ID está en la lista de validadores autorizados.
        """
        return str(telegram_id) in self.TELEGRAM_VALIDATOR_IDS

    def get_validator_ids_as_int(self) -> list[int]:
        """
        Retorna los IDs de validadores como enteros.

        Returns:
            Lista de ints con los IDs de Telegram de los validadores.
        """
        return [int(uid) for uid in self.TELEGRAM_VALIDATOR_IDS]


# Instancia global singleton para uso en toda la aplicación
settings = Settings()
