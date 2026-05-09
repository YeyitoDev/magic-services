"""
Reminder Service - Magic Chatbot v2
====================================
Servicio de dominio para la gestión de recordatorios de compra.

Maneja el pipeline de recordatorios para usuarios que seleccionaron
un servicio pero no completaron la compra:

Fase 1 (reminder=0, 1min - 24h): Envía imagen + precios actualizados.
Fase 2 (reminder=1, >24h): Envía video recordatorio.
Fase 3 (reminder>=2, >24h): Elimina el registro de selección.

También gestiona el envío de mensajes de suscripción vencida a usuarios
que han sido expulsados del grupo por falta de pago.

Principios:
- Single Responsibility: solo lógica de recordatorios y notificaciones.
- Dependency Inversion: depende de repositorios y servicios externos.
- Configurable: intervalos y rutas de archivos vía settings.

Uso:
    from services.reminder_service import ReminderService

    reminder_svc = ReminderService(selected_service_repo, subscription_repo)
    await reminder_svc.process_pending_reminders()
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.settings import settings
from repositories.selected_service_repo import SelectedServiceRepository
from repositories.subscription_repo import SubscriptionRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Templates de mensajes
# ---------------------------------------------------------------------------

RECORDATORIO_10_MINUTOS = (
    "¿QUIERES GANAR CÓMO MIS CLIENTES?\n"
    "Las mejores fijas estadísticas de todo el Perú, "
    "simplemente selecciona que servicios deseas y unete! 🔮✅"
)

RECORDATORIO_24_HORAS = (
    "¡LA ÚNICA COMUNIDAD RENTABLE DE TODO EL PERÚ!\n"
    "Que esperas para unirte mi hermano 🔥"
)

MENSAJE_SUSCRIPCION_VENCIDA_TEMPLATE = """¿QUIERES GANAR CÓMO MIS CLIENTES?

🔴 *SUSCRIPCIÓN VENCIDA*

Lamentamos informarte que tu suscripción ha expirado el *{fecha}*.

¡LA ÚNICA COMUNIDAD RENTABLE DE TODO EL PERÚ!
Que esperas para volver a unirte mi hermano 🔥

Para continuar disfrutando de nuestros servicios premium y acceder
nuevamente al grupo VIP, debes renovar tu suscripción.

📱 *¿Cómo renovar?*
Selecciona el plan que desees y vuelve a unirte! 🔮✅

Una vez completado el pago, serás agregado nuevamente al grupo.

❓ *¿Preguntas o problemas?*
Contáctame directamente: @magic_peru 📲
Estoy aquí para ayudarte 24/7 💬

¡Esperamos verte pronto! 🔮✨"""


# ---------------------------------------------------------------------------
# Recordatorios de precios
# ---------------------------------------------------------------------------

RECORDATORIO_PRECIOS_CAPTION = """
HERMANO SOLO POR HOY TE DOY S/. 10 DE DESCUENTO EN EL GRUPO VIP!

Nuevos Precios VIP ✅
* 1 Mes = S/. 90
* 2 Meses = S/. 140
* 3 Meses = S/. 190

Los números de cuenta son los siguiente mi hermano 🔮

Titular: José González Reategui
Yape/Plin: 952903700
BCP: 19402020623033
SCOTIA: 1780142814

Solo envía la captura de tu transferencia por este medio 📲
"""


# ---------------------------------------------------------------------------
# Rutas de archivos multimedia
# ---------------------------------------------------------------------------

IMAGENES_DIR = "./imagenes_promocionales"
RECORDATORIO_GANADORES_IMG = os.path.join(IMAGENES_DIR, "recordatorio_ganadores.jpeg")
GRUPO_VIP_IMG = os.path.join(IMAGENES_DIR, "grupo_vip_1.jpg")
RECORDATORIO_VIDEO = os.path.join(IMAGENES_DIR, "recordatorio_video.mp4")


# ---------------------------------------------------------------------------
# Reminder Service
# ---------------------------------------------------------------------------

class ReminderService:
    """
    Servicio de lógica de negocio para recordatorios y notificaciones.

    Gestiona:
    - Recordatorios de compra pendiente (fase 1 y fase 2).
    - Limpieza de selecciones expiradas.
    - Mensajes de suscripción vencida.

    Dependencias:
        selected_service_repo: Para consultar/actualizar selecciones.
        subscription_repo: Para consultar suscripciones vencidas.
    """

    def __init__(
        self,
        selected_service_repo: SelectedServiceRepository,
        subscription_repo: SubscriptionRepository,
    ) -> None:
        """
        Inicializa el servicio con sus repositorios.

        Args:
            selected_service_repo: Repositorio de servicios seleccionados.
            subscription_repo: Repositorio de suscripciones.
        """
        self._selected_repo = selected_service_repo
        self._subscription_repo = subscription_repo

    # ------------------------------------------------------------------
    # Pipeline principal de recordatorios
    # ------------------------------------------------------------------

    def process_pending_reminders(self) -> Dict[str, Any]:
        """
        Procesa todos los recordatorios pendientes del sistema.

        Itera sobre todos los registros de SelectedService y aplica
        la lógica de recordatorios según el contador `reminder` y
        el tiempo transcurrido desde la selección.

        Lógica por fase:
        - Fase 1: reminder=0 y 1min ≤ tiempo < 24h → envía foto + precios.
        - Fase 2: reminder=1 y tiempo ≥ 24h → envía video recordatorio.
        - Fase 3: reminder≥2 o tiempo > 24h con ambos enviados → elimina registro.

        Returns:
            Diccionario con estadísticas del procesamiento:
            - total_processed: Total de registros procesados.
            - phase1_sent: Recordatorios fase 1 enviados.
            - phase2_sent: Recordatorios fase 2 enviados.
            - deleted: Registros eliminados.
            - errors: Lista de errores encontrados.
        """
        stats = {
            "total_processed": 0,
            "phase1_sent": 0,
            "phase2_sent": 0,
            "deleted": 0,
            "errors": [],
        }

        try:
            pending_services = self._selected_repo.get_all()
            stats["total_processed"] = len(pending_services)

            logger.info(
                f"Procesando {len(pending_services)} recordatorios pendientes..."
            )

            for selected in pending_services:
                user_id = selected.user_telegram_id
                selected_date = selected.selected_date
                reminder = selected.reminder
                current_time = datetime.now()

                # Calcular tiempo transcurrido en minutos
                time_diff = current_time - selected_date
                minutes_elapsed = int(time_diff.total_seconds() / 60)

                logger.debug(
                    f"User {user_id}: reminder={reminder}, "
                    f"elapsed={minutes_elapsed}min"
                )

                # --- Fase 1: Recordatorio a los ~10 minutos ---
                if reminder == 0 and 1 <= minutes_elapsed < (24 * 60):
                    logger.info(
                        f"FASE 1: Enviando recordatorio 1 a user={user_id}"
                    )
                    try:
                        self._send_phase1_reminder(user_id)
                        self._selected_repo.increment_reminder(user_id)
                        stats["phase1_sent"] += 1
                        logger.info(
                            f"Recordatorio fase 1 enviado a user={user_id}"
                        )
                    except Exception as e:
                        error_msg = f"Error fase 1 user={user_id}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)

                # --- Fase 2: Recordatorio a las ~24 horas ---
                elif reminder == 1 and minutes_elapsed >= (24 * 60):
                    logger.info(
                        f"FASE 2: Enviando recordatorio 2 a user={user_id}"
                    )
                    try:
                        self._send_phase2_reminder(user_id)
                        self._selected_repo.delete_by_user(user_id)
                        stats["phase2_sent"] += 1
                        logger.info(
                            f"Recordatorio fase 2 enviado y registro eliminado "
                            f"para user={user_id}"
                        )
                    except Exception as e:
                        error_msg = f"Error fase 2 user={user_id}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)

                # --- Fase 3: Limpieza ---
                elif reminder >= 2 or (
                    reminder >= 1 and minutes_elapsed >= (48 * 60)
                ):
                    logger.info(
                        f"FASE 3: Eliminando selección expirada de user={user_id}"
                    )
                    try:
                        self._selected_repo.delete_by_user(user_id)
                        stats["deleted"] += 1
                        logger.info(
                            f"Selección expirada eliminada para user={user_id}"
                        )
                    except Exception as e:
                        error_msg = f"Error al eliminar selección user={user_id}: {e}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)

                else:
                    # No aplica ninguna fase aún (muy pronto, o estado intermedio)
                    logger.debug(
                        f"User {user_id}: sin acciones pendientes "
                        f"(reminder={reminder}, elapsed={minutes_elapsed}min)"
                    )

                # Pequeña pausa entre usuarios para no saturar la API
                time.sleep(0.5)

        except Exception as e:
            error_msg = f"Error general en process_pending_reminders: {e}"
            logger.error(error_msg, exc_info=True)
            stats["errors"].append(error_msg)

        logger.info(
            f"Procesamiento de recordatorios completado: "
            f"fase1={stats['phase1_sent']}, fase2={stats['phase2_sent']}, "
            f"deleted={stats['deleted']}, errors={len(stats['errors'])}"
        )

        return stats

    # ------------------------------------------------------------------
    # Envío de recordatorios individuales
    # ------------------------------------------------------------------

    def _send_phase1_reminder(self, user_id: int) -> None:
        """
        Envía el recordatorio de fase 1: imágenes + precios.

        Args:
            user_id: ID de Telegram del usuario.
        """
        from services.telegram_api import TelegramAPIService

        api = TelegramAPIService()

        # Enviar primera imagen (recordatorio ganadores)
        if os.path.exists(RECORDATORIO_GANADORES_IMG):
            api.send_photo(
                chat_id=user_id,
                photo=RECORDATORIO_GANADORES_IMG,
                caption=RECORDATORIO_10_MINUTOS,
            )

        # Enviar segunda imagen (grupo VIP + precios)
        if os.path.exists(GRUPO_VIP_IMG):
            api.send_photo(
                chat_id=user_id,
                photo=GRUPO_VIP_IMG,
                caption=RECORDATORIO_PRECIOS_CAPTION,
            )

        logger.debug(f"Fase 1 completada para user={user_id}")

    def _send_phase2_reminder(self, user_id: int) -> None:
        """
        Envía el recordatorio de fase 2: video.

        Args:
            user_id: ID de Telegram del usuario.
        """
        from services.telegram_api import TelegramAPIService

        api = TelegramAPIService()

        if os.path.exists(RECORDATORIO_VIDEO):
            api.send_video(
                chat_id=user_id,
                video=RECORDATORIO_VIDEO,
                caption=RECORDATORIO_24_HORAS,
            )
        else:
            # Fallback: enviar mensaje de texto si no hay video
            logger.warning(
                f"Video de recordatorio no encontrado en {RECORDATORIO_VIDEO}. "
                f"Enviando texto en su lugar."
            )
            api.send_message(
                chat_id=user_id,
                text=RECORDATORIO_24_HORAS,
            )

        logger.debug(f"Fase 2 completada para user={user_id}")

    # ------------------------------------------------------------------
    # Mensajes de suscripción vencida
    # ------------------------------------------------------------------

    def send_expired_subscription_message(
        self,
        user_telegram_id: int,
        end_date: datetime,
    ) -> bool:
        """
        Envía un mensaje al usuario informando que su suscripción ha vencido.

        Se utiliza en el proceso de limpieza de suscripciones
        (getMembersTelethon) antes de expulsar al usuario del grupo VIP.

        Args:
            user_telegram_id: ID de Telegram del usuario.
            end_date: Fecha en la que venció la suscripción.

        Returns:
            True si el mensaje se envió correctamente, False si hubo error.
        """
        try:
            from services.telegram_api import TelegramAPIService

            # Formatear la fecha en español
            from utils.datetime_utils import format_date_spanish

            fecha_formateada = format_date_spanish(end_date)

            mensaje = MENSAJE_SUSCRIPCION_VENCIDA_TEMPLATE.format(
                fecha=fecha_formateada
            )

            api = TelegramAPIService()
            result = api.send_message(
                chat_id=user_telegram_id,
                text=mensaje,
                parse_mode="Markdown",
            )

            logger.info(
                f"Mensaje de suscripción vencida enviado a user={user_telegram_id}"
            )
            return result.get("ok", False)

        except Exception as e:
            logger.error(
                f"Error al enviar mensaje de suscripción vencida "
                f"a user={user_telegram_id}: {e}",
                exc_info=True,
            )
            return False

    # ------------------------------------------------------------------
    # Notificaciones de expiración próxima
    # ------------------------------------------------------------------

    def send_expiring_soon_notifications(self, days: int = 3) -> int:
        """
        Envía notificaciones a usuarios cuyas suscripciones están
        próximas a vencer.

        Args:
            days: Días de anticipación para la notificación (default: 3).

        Returns:
            Número de notificaciones enviadas.
        """
        expiring_subs = self._subscription_repo.get_expiring_soon(days)
        sent_count = 0

        for sub in expiring_subs:
            try:
                from services.telegram_api import TelegramAPIService
                from utils.datetime_utils import format_date_spanish

                fecha_formateada = format_date_spanish(sub.end_date)

                mensaje = (
                    f"⚠️ *Tu suscripción está por vencer*\n\n"
                    f"Tu acceso al Grupo VIP vence el *{fecha_formateada}*.\n\n"
                    f"Renueva ahora para no perder el acceso a los pronósticos "
                    f"exclusivos de Magic 🔮\n\n"
                    f"Envía un mensaje a @magic_peru para renovar."
                )

                api = TelegramAPIService()
                api.send_message(
                    chat_id=sub.user_telegram_id,
                    text=mensaje,
                    parse_mode="Markdown",
                )
                sent_count += 1

                logger.info(
                    f"Notificación de expiración enviada a user={sub.user_telegram_id}"
                )

            except Exception as e:
                logger.error(
                    f"Error al enviar notificación de expiración "
                    f"a user={sub.user_telegram_id}: {e}"
                )

        logger.info(
            f"Notificaciones de expiración: {sent_count} enviadas "
            f"(de {len(expiring_subs)} suscripciones próximas a vencer)"
        )
        return sent_count

    # ------------------------------------------------------------------
    # Limpieza de selecciones expiradas
    # ------------------------------------------------------------------

    def cleanup_expired_selections(self, max_minutes: int = 1440) -> int:
        """
        Elimina todas las selecciones de servicio que han expirado
        por inactividad prolongada.

        Args:
            max_minutes: Tiempo máximo en minutos antes de considerar
                         una selección como expirada (default: 1440 = 24h).

        Returns:
            Número de selecciones eliminadas.
        """
        deleted_count = 0
        all_selections = self._selected_repo.get_all()

        for selected in all_selections:
            if selected.is_expired(max_minutes):
                self._selected_repo.delete_by_user(selected.user_telegram_id)
                deleted_count += 1
                logger.debug(
                    f"Selección expirada eliminada: user={selected.user_telegram_id}"
                )

        logger.info(f"Limpieza de selecciones: {deleted_count} eliminadas.")
        return deleted_count
