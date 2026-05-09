"""
Google Credentials Manager - Magic Chatbot v2
==============================================
Maneja las credenciales de Google Cloud de forma flexible:
- Desarrollo: archivo JSON local (GOOGLE_CREDENTIALS_PATH)
- Producción: variable de entorno GOOGLE_CREDENTIALS_JSON con el JSON completo
- CI/CD: GitHub Secret → variable de entorno

Uso:
    from services.google_credentials import get_google_credentials

    creds = get_google_credentials()
    # creds es un diccionario con el contenido del JSON de service account
"""

import json
import os
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_google_credentials() -> Dict[str, Any]:
    """
    Obtiene las credenciales de Google Cloud desde:
    1. Variable de entorno GOOGLE_CREDENTIALS_JSON (prod/CI)
    2. Archivo JSON en GOOGLE_CREDENTIALS_PATH (dev local)

    Returns:
        Diccionario con las credenciales de la service account.

    Raises:
        FileNotFoundError: Si no se encuentran credenciales en ninguna fuente.
        json.JSONDecodeError: Si el JSON es inválido.
    """
    from config.settings import settings

    # Opción 1: Variable de entorno con el JSON completo (producción)
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        logger.info("Google credentials loaded from GOOGLE_CREDENTIALS_JSON env var")
        return json.loads(creds_json)

    # Opción 2: Archivo JSON local (desarrollo)
    creds_path = settings.GOOGLE_CREDENTIALS_PATH
    if creds_path and os.path.exists(creds_path):
        logger.info(f"Google credentials loaded from file: {creds_path}")
        with open(creds_path, 'r') as f:
            return json.load(f)

    raise FileNotFoundError(
        "Google credentials not found. Set GOOGLE_CREDENTIALS_JSON env var "
        "or ensure GOOGLE_CREDENTIALS_PATH points to a valid JSON file."
    )


def get_credentials_json_string() -> str:
    """
    Returns the credentials as a JSON string (useful for subprocess/threading).
    """
    return json.dumps(get_google_credentials())
