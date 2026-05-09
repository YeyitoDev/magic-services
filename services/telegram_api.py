"""
Telegram API Service - Magic Chatbot v2
========================================
Wrapper de bajo nivel sobre la API HTTP de Telegram para tareas batch
que no requieren el framework python-telegram-bot (jobs, scripts, etc.).

Proporciona métodos para:
- Enviar mensajes, fotos, videos (desde URL o archivo local).
- Gestionar miembros del grupo (kick, ban, unban).
- Crear enlaces de invitación.
- Obtener administradores del chat.
- Enviar mensajes con teclados inline.

Todas las llamadas usan la API HTTP de Telegram vía `requests`.
El BOT_TOKEN se obtiene de config.settings.

Principios:
- Stateless: no mantiene estado entre llamadas. Cada método es independiente.
- Resiliente: incluye reintentos básicos y logging de errores.
- Tipado: type hints en todos los métodos.

Uso:
    from services.telegram_api import TelegramAPIService

    api = TelegramAPIService()
    api.send_message(chat_id=12345, text="Hola mundo")
    api.kick_user(chat_id=-1002451833719, user_id=67890)
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

BASE_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
DEFAULT_TIMEOUT = 30  # segundos


class TelegramAPIService:
    """
    Servicio wrapper sobre la API HTTP de Telegram Bot.

    Cada método realiza una llamada HTTP a la API y retorna la respuesta
    parseada como diccionario. Los errores se loguean y se relanzan como
    TelegramAPIError.

    Attributes:
        token (str): Token del bot.
        base_url (str): URL base de la API.
        timeout (int): Timeout por defecto para requests.
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """
        Inicializa el servicio con el token desde settings.

        Args:
            timeout: Timeout en segundos para cada request HTTP.
        """
        self.token: str = settings.TELEGRAM_BOT_TOKEN or ""
        self.base_url: str = f"https://api.telegram.org/bot{self.token}"
        self.timeout: int = timeout

        if not self.token:
            logger.warning(
                "TelegramAPIService inicializado sin BOT_TOKEN. "
                "Las llamadas a la API fallarán."
            )

    # ------------------------------------------------------------------
    # Métodos internos
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Realiza una petición HTTP a la API de Telegram.

        Args:
            method: Método HTTP ("GET" o "POST").
            endpoint: Endpoint de la API (ej: "sendMessage").
            data: Datos a enviar como form-data o query params.
            files: Archivos a subir (para multipart/form-data).
            timeout: Timeout en segundos.

        Returns:
            Diccionario con la respuesta JSON de la API.

        Raises:
            TelegramAPIError: Si la API retorna ok=false o hay error de red.
        """
        url = f"{self.base_url}/{endpoint}"
        timeout = timeout or self.timeout

        try:
            if method.upper() == "GET":
                response = requests.get(
                    url, params=data, timeout=timeout
                )
            else:
                response = requests.post(
                    url, data=data, files=files, timeout=timeout
                )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.error(f"Timeout llamando a {endpoint} (>{timeout}s)")
            raise TelegramAPIError(f"Timeout en {endpoint}: >{timeout}s")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Error de conexión en {endpoint}: {e}")
            raise TelegramAPIError(f"Error de conexión en {endpoint}: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error HTTP en {endpoint}: {e}")
            raise TelegramAPIError(f"Error HTTP en {endpoint}: {e}")

        result = response.json()

        if not result.get("ok", False):
            error_desc = result.get("description", "Error desconocido")
            logger.error(
                f"Telegram API error en {endpoint}: {error_desc}"
            )
            raise TelegramAPIError(f"Telegram API error: {error_desc}")

        return result

    # ------------------------------------------------------------------
    # Mensajes
    # ------------------------------------------------------------------

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[Any] = None,
        disable_notification: bool = False,
    ) -> Dict[str, Any]:
        """
        Envía un mensaje de texto a un chat.

        Args:
            chat_id: ID del chat o usuario destino.
            text: Texto del mensaje (puede contener HTML si parse_mode="HTML").
            parse_mode: Modo de parseo: "HTML", "Markdown", o None.
            reply_markup: Teclado inline opcional (InlineKeyboardMarkup o dict).
            disable_notification: Si True, envía el mensaje en silencio.

        Returns:
            Respuesta de la API con el mensaje enviado.
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }

        if parse_mode:
            data["parse_mode"] = parse_mode

        if reply_markup:
            if hasattr(reply_markup, "to_dict"):
                data["reply_markup"] = json.dumps(reply_markup.to_dict())
            elif isinstance(reply_markup, dict):
                data["reply_markup"] = json.dumps(reply_markup)
            else:
                data["reply_markup"] = reply_markup

        result = self._request("POST", "sendMessage", data=data)
        logger.debug(f"Mensaje enviado a {chat_id}: {text[:50]}...")
        return result

    def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Envía una foto a un chat.

        Args:
            chat_id: ID del chat destino.
            photo: URL de la imagen o ruta a archivo local.
            caption: Texto descriptivo de la imagen.
            parse_mode: Modo de parseo del caption.
            reply_markup: Teclado inline opcional.

        Returns:
            Respuesta de la API.
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "caption": caption,
        }

        if parse_mode:
            data["parse_mode"] = parse_mode

        if reply_markup:
            if isinstance(reply_markup, dict):
                data["reply_markup"] = json.dumps(reply_markup)
            elif hasattr(reply_markup, "to_dict"):
                data["reply_markup"] = json.dumps(reply_markup.to_dict())

        # Determinar si photo es URL o archivo local
        if photo.startswith("http://") or photo.startswith("https://"):
            data["photo"] = photo
            result = self._request("POST", "sendPhoto", data=data)
        else:
            # Archivo local
            with open(photo, "rb") as f:
                files = {"photo": f}
                result = self._request(
                    "POST", "sendPhoto", data=data, files=files
                )

        logger.debug(f"Foto enviada a {chat_id}")
        return result

    def send_video(
        self,
        chat_id: int,
        video: str,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: Optional[Any] = None,
        supports_streaming: bool = True,
    ) -> Dict[str, Any]:
        """
        Envía un video a un chat.

        Args:
            chat_id: ID del chat destino.
            video: URL del video o ruta a archivo local.
            caption: Texto descriptivo del video.
            parse_mode: Modo de parseo del caption.
            reply_markup: Teclado inline opcional.
            supports_streaming: Si True, el video se puede hacer streaming.

        Returns:
            Respuesta de la API.
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "caption": caption,
            "supports_streaming": supports_streaming,
        }

        if parse_mode:
            data["parse_mode"] = parse_mode

        if reply_markup:
            if isinstance(reply_markup, dict):
                data["reply_markup"] = json.dumps(reply_markup)
            elif hasattr(reply_markup, "to_dict"):
                data["reply_markup"] = json.dumps(reply_markup.to_dict())

        # Determinar si video es URL o archivo local
        if video.startswith("http://") or video.startswith("https://"):
            data["video"] = video
            result = self._request("POST", "sendVideo", data=data)
        else:
            with open(video, "rb") as f:
                files = {"video": f}
                result = self._request(
                    "POST", "sendVideo", data=data, files=files
                )

        logger.debug(f"Video enviado a {chat_id}")
        return result

    # ------------------------------------------------------------------
    # Gestión de miembros del chat
    # ------------------------------------------------------------------

    def kick_user(self, chat_id: int, user_id: int) -> Dict[str, Any]:
        """
        Expulsa (kick) a un usuario del chat/grupo.

        El usuario es baneado automáticamente al ser expulsado.
        Para permitir que pueda re-unirse, llamar a unban_user después.

        Args:
            chat_id: ID del chat/grupo (número negativo para supergrupos).
            user_id: ID de Telegram del usuario a expulsar.

        Returns:
            Respuesta de la API.
        """
        data = {
            "chat_id": chat_id,
            "user_id": user_id,
        }
        result = self._request("POST", "kickChatMember", data=data)
        logger.info(f"Usuario {user_id} expulsado del chat {chat_id}")
        return result

    def ban_user(
        self,
        chat_id: int,
        user_id: int,
        until_date: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Banea a un usuario del chat.

        Args:
            chat_id: ID del chat/grupo.
            user_id: ID de Telegram del usuario a banear.
            until_date: Timestamp Unix hasta cuando estará baneado.
                        None = permanente.

        Returns:
            Respuesta de la API.
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "user_id": user_id,
        }
        if until_date:
            data["until_date"] = until_date

        result = self._request("POST", "banChatMember", data=data)
        logger.info(
            f"Usuario {user_id} baneado del chat {chat_id}"
            + (f" hasta {until_date}" if until_date else " permanentemente")
        )
        return result

    def unban_user(
        self,
        chat_id: int,
        user_id: int,
        only_if_banned: bool = True,
    ) -> Dict[str, Any]:
        """
        Desbanea a un usuario del chat, permitiéndole re-unirse.

        Args:
            chat_id: ID del chat/grupo.
            user_id: ID de Telegram del usuario.
            only_if_banned: Si True, solo desbanea si el usuario está baneado.

        Returns:
            Respuesta de la API.
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "only_if_banned": only_if_banned,
        }
        result = self._request("POST", "unbanChatMember", data=data)
        logger.info(f"Usuario {user_id} desbaneado del chat {chat_id}")
        return result

    def remove_user_allow_rejoin(
        self, chat_id: int, user_id: int
    ) -> Dict[str, Any]:
        """
        Expulsa a un usuario y lo desbanea inmediatamente para permitir
        que pueda re-unirse al grupo con un enlace de invitación.

        Flujo: kick → unban (con only_if_banned=True).
        Este método replica la lógica de remove_user_allow_rejoin() del
        código original en tasks.py / jobMensajesRecordatorios.py.

        Args:
            chat_id: ID del chat/grupo.
            user_id: ID de Telegram del usuario.

        Returns:
            Diccionario con:
            - kick_success: bool
            - unban_success: bool
            - kick_result: respuesta de kick
            - unban_result: respuesta de unban (si aplica)
        """
        result = {
            "kick_success": False,
            "unban_success": False,
            "kick_result": None,
            "unban_result": None,
        }

        # 1. Expulsar al usuario
        try:
            kick_result = self.kick_user(chat_id, user_id)
            result["kick_result"] = kick_result
            result["kick_success"] = kick_result.get("ok", False)
        except TelegramAPIError as e:
            logger.error(f"Error al expulsar usuario {user_id}: {e}")
            result["kick_result"] = {"ok": False, "error": str(e)}
            return result

        # 2. Desbanear inmediatamente
        if result["kick_success"]:
            try:
                unban_result = self.unban_user(
                    chat_id, user_id, only_if_banned=True
                )
                result["unban_result"] = unban_result
                result["unban_success"] = unban_result.get("ok", False)
            except TelegramAPIError as e:
                logger.error(f"Error al desbanear usuario {user_id}: {e}")
                result["unban_result"] = {"ok": False, "error": str(e)}

        return result

    # ------------------------------------------------------------------
    # Enlaces de invitación
    # ------------------------------------------------------------------

    def create_invite_link(
        self,
        chat_id: int,
        expire_date: Optional[int] = None,
        member_limit: int = 1,
        name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Crea un enlace de invitación de un solo uso para un chat/grupo.

        Args:
            chat_id: ID del chat/grupo.
            expire_date: Timestamp Unix de expiración.
                         Si None, expira en 24 horas.
            member_limit: Número máximo de usos (1 = un solo uso).
            name: Nombre descriptivo del enlace.

        Returns:
            URL del enlace de invitación, o None si falla.
        """
        import time

        if expire_date is None:
            expire_date = int(time.time()) + 86400  # 24 horas

        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "member_limit": member_limit,
            "expire_date": expire_date,
        }
        if name:
            data["name"] = name

        try:
            result = self._request(
                "POST", "createChatInviteLink", data=data
            )
            invite_link = result.get("result", {}).get("invite_link")
            logger.info(
                f"Link de invitación creado para chat {chat_id}: {invite_link}"
            )
            return invite_link
        except TelegramAPIError as e:
            logger.error(
                f"No se pudo crear link de invitación para chat {chat_id}: {e}"
            )
            return None

    def export_chat_invite_link(self, chat_id: int) -> Optional[str]:
        """
        Obtiene el enlace de invitación principal del chat.

        A diferencia de create_invite_link, este método exporta el link
        de invitación primario del chat (no crea uno nuevo temporal).

        Args:
            chat_id: ID del chat/grupo.

        Returns:
            URL del enlace de invitación principal.
        """
        data = {"chat_id": chat_id}
        try:
            result = self._request(
                "POST", "exportChatInviteLink", data=data
            )
            link = result.get("result")
            logger.info(f"Link de invitación exportado para chat {chat_id}")
            return link
        except TelegramAPIError as e:
            logger.error(
                f"No se pudo exportar link de chat {chat_id}: {e}"
            )
            return None

    # ------------------------------------------------------------------
    # Administradores del chat
    # ------------------------------------------------------------------

    def get_chat_administrators(
        self, chat_id: int
    ) -> List[Dict[str, Any]]:
        """
        Obtiene la lista de administradores de un chat/grupo.

        Args:
            chat_id: ID del chat/grupo.

        Returns:
            Lista de diccionarios con info de cada administrador:
            - user: {id, is_bot, first_name, username, ...}
            - status: "creator" o "administrator"
            - is_anonymous, custom_title, etc.
        """
        data = {"chat_id": chat_id}
        try:
            result = self._request(
                "POST", "getChatAdministrators", data=data
            )
            admins = result.get("result", [])
            logger.debug(
                f"Obtenidos {len(admins)} administradores del chat {chat_id}"
            )
            return admins
        except TelegramAPIError as e:
            logger.error(
                f"No se pudieron obtener administradores del chat {chat_id}: {e}"
            )
            return []

    def get_admin_user_ids(self, chat_id: int) -> List[int]:
        """
        Obtiene solo los IDs de los administradores del chat.

        Args:
            chat_id: ID del chat/grupo.

        Returns:
            Lista de IDs de usuario que son administradores.
        """
        admins = self.get_chat_administrators(chat_id)
        return [
            admin.get("user", {}).get("id")
            for admin in admins
            if admin.get("user", {}).get("id")
        ]

    # ------------------------------------------------------------------
    # Métodos de utilidad
    # ------------------------------------------------------------------

    def get_chat_member(
        self, chat_id: int, user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene información sobre un miembro específico del chat.

        Args:
            chat_id: ID del chat/grupo.
            user_id: ID de Telegram del usuario.

        Returns:
            Diccionario con status, user info, etc., o None si falla.
        """
        data = {
            "chat_id": chat_id,
            "user_id": user_id,
        }
        try:
            result = self._request("POST", "getChatMember", data=data)
            return result.get("result")
        except TelegramAPIError as e:
            logger.warning(
                f"No se pudo obtener info del miembro {user_id} "
                f"en chat {chat_id}: {e}"
            )
            return None

    def is_member_in_chat(self, chat_id: int, user_id: int) -> bool:
        """
        Verifica si un usuario es miembro de un chat.

        Args:
            chat_id: ID del chat/grupo.
            user_id: ID de Telegram del usuario.

        Returns:
            True si el usuario está en el chat (status: member, administrator, creator).
        """
        member = self.get_chat_member(chat_id, user_id)
        if member is None:
            return False
        status = member.get("status", "")
        return status in ("member", "administrator", "creator")

    def delete_message(
        self, chat_id: int, message_id: int
    ) -> bool:
        """
        Elimina un mensaje del chat.

        Args:
            chat_id: ID del chat.
            message_id: ID del mensaje a eliminar.

        Returns:
            True si se eliminó correctamente.
        """
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        try:
            self._request("POST", "deleteMessage", data=data)
            logger.debug(f"Mensaje {message_id} eliminado del chat {chat_id}")
            return True
        except TelegramAPIError:
            return False


# ---------------------------------------------------------------------------
# Excepción personalizada
# ---------------------------------------------------------------------------


class TelegramAPIError(Exception):
    """
    Excepción lanzada cuando la API de Telegram retorna un error.

    Attributes:
        message (str): Mensaje descriptivo del error.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        return f"TelegramAPIError: {self.message}"
