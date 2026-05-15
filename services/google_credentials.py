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
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def get_google_credentials() -> dict[str, Any]:
    """
    Obtiene las credenciales de Google Cloud desde:
    1. Variable de entorno GOOGLE_CREDENTIALS_JSON (prod/CI)
    2. Archivo JSON en GOOGLE_CREDENTIALS_PATH (dev local)
    3. Archivo por defecto: credentials/google.json (PythonAnywhere)

    Returns:
        Diccionario con las credenciales de la service account.

    Raises:
        FileNotFoundError: Si no se encuentran credenciales en ninguna fuente.
    """
    from config.settings import settings

    # 1. Variable de entorno GOOGLE_CREDENTIALS_JSON
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        try:
            # Fix: Fly.io secrets may escape newlines as \\n
            if "\\n" in creds_json:
                creds_json = creds_json.replace("\\n", "\n")
            creds = json.loads(creds_json)
            logger.info("Google credentials loaded from GOOGLE_CREDENTIALS_JSON env var")
            return creds
        except json.JSONDecodeError as e:
            logger.warning(f"GOOGLE_CREDENTIALS_JSON has invalid JSON: {e}. Trying file...")

    # 2. Archivo en GOOGLE_CREDENTIALS_PATH
    creds_path = settings.GOOGLE_CREDENTIALS_PATH
    if creds_path and os.path.exists(creds_path):
        try:
            with open(creds_path) as f:
                creds = json.load(f)
            logger.info(f"Google credentials loaded from file: {creds_path}")
            return creds
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load from {creds_path}: {e}. Trying default...")

    # 3. Archivo por defecto: credentials/google.json
    default_path = "./credentials/google.json"
    if os.path.exists(default_path):
        try:
            with open(default_path) as f:
                creds = json.load(f)
            logger.info(f"Google credentials loaded from default file: {default_path}")
            return creds
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load from {default_path}: {e}")

    raise FileNotFoundError(
        "Google credentials not found. Set GOOGLE_CREDENTIALS_JSON env var "
        "or create credentials/google.json with valid JSON."
    )


def get_credentials_json_string() -> str:
    """
    Returns the credentials as a JSON string (useful for subprocess/threading).
    """
    return json.dumps(get_google_credentials())
