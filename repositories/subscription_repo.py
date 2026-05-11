"""
Subscription Repository - Magic Chatbot v2
===========================================
Repositorio para operaciones de acceso a datos de la entidad Subscription.

Operaciones:
- Búsqueda de suscripciones activas, por usuario, expiradas y próximas a vencer.
- Creación y actualización de suscripciones.
- Eliminación de suscripciones.
- Extensión de fecha de fin basada en compras.

Uso:
    repo = SubscriptionRepository(session)
    active_subs = repo.get_active_subs()
    expired = repo.get_expired_subs()
"""

from datetime import date, timedelta

from sqlalchemy import and_

from models.purchase import Purchase
from models.subscription import Subscription
from repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository):
    """
    Repositorio con operaciones específicas para la tabla `subscriptions`.

    Maneja el ciclo de vida completo de las suscripciones: creación,
    extensión, consulta de vigencia y eliminación de suscripciones vencidas.
    """

    # ------------------------------------------------------------------
    # Consultas de suscripciones activas
    # ------------------------------------------------------------------

    def get_active_subs(self) -> list[Subscription]:
        """
        Obtiene todas las suscripciones actualmente activas.

        Una suscripción está activa si su end_date >= fecha de hoy.

        Returns:
            Lista de suscripciones vigentes.
        """
        today = date.today()
        return (
            self._session.query(Subscription)
            .filter(Subscription.end_date >= today)
            .all()
        )

    def get_active_sub(
        self, user_telegram_id: int
    ) -> list[Subscription]:
        """
        Obtiene las suscripciones activas de un usuario específico.

        Args:
            user_telegram_id: ID de Telegram del usuario.

        Returns:
            Lista de suscripciones activas del usuario.
        """
        today = date.today()
        return (
            self._session.query(Subscription)
            .filter(
                and_(
                    Subscription.user_telegram_id == user_telegram_id,
                    Subscription.end_date >= today,
                )
            )
            .all()
        )

    def get_sub_by_user_and_service(
        self, user_telegram_id: int, service_id: int
    ) -> Subscription | None:
        """
        Busca la suscripción de un usuario a un servicio específico.

        Retorna la suscripción más reciente (mayor end_date) si hay varias.

        Args:
            user_telegram_id: ID de Telegram del usuario.
            service_id: ID del servicio.

        Returns:
            La suscripción encontrada o None.
        """
        return (
            self._session.query(Subscription)
            .filter(
                and_(
                    Subscription.user_telegram_id == user_telegram_id,
                    Subscription.service_id == service_id,
                )
            )
            .order_by(Subscription.end_date.desc())
            .first()
        )

    # ------------------------------------------------------------------
    # Consultas de suscripciones vencidas / próximas a vencer
    # ------------------------------------------------------------------

    def get_expired_subs(self) -> list[Subscription]:
        """
        Obtiene suscripciones vencidas (end_date < hoy).

        Estas son candidatas para el proceso de limpieza (kick del grupo).

        Returns:
            Lista de suscripciones expiradas.
        """
        today = date.today()
        return (
            self._session.query(Subscription)
            .filter(Subscription.end_date < today)
            .all()
        )

    def get_expiring_soon(self, days: int = 3) -> list[Subscription]:
        """
        Obtiene suscripciones que vencerán en los próximos N días.

        Útil para enviar avisos de renovación antes del vencimiento.

        Args:
            days: Días de anticipación (default 3).

        Returns:
            Lista de suscripciones próximas a vencer.
        """
        today = date.today()
        deadline = today + timedelta(days=days)
        return (
            self._session.query(Subscription)
            .filter(
                and_(
                    Subscription.end_date >= today,
                    Subscription.end_date <= deadline,
                )
            )
            .all()
        )

    # ------------------------------------------------------------------
    # Creación y actualización
    # ------------------------------------------------------------------

    def get_or_create_sub(
        self, user_telegram_id: int, service_id: int
    ) -> Subscription:
        """
        Obtiene una suscripción activa existente o crea una nueva mínima.

        Si no existe, crea una suscripción con start_date = hoy y
        end_date = hoy (0 días). Luego el caller puede extenderla.

        Args:
            user_telegram_id: ID de Telegram del usuario.
            service_id: ID del servicio.

        Returns:
            Suscripción existente o recién creada.
        """
        today = date.today()

        # Buscar suscripción activa existente
        subscription = (
            self._session.query(Subscription)
            .filter(
                and_(
                    Subscription.user_telegram_id == user_telegram_id,
                    Subscription.service_id == service_id,
                    Subscription.end_date >= today,
                )
            )
            .first()
        )

        if subscription is None:
            subscription = Subscription(
                user_telegram_id=user_telegram_id,
                service_id=service_id,
                start_date=today,
                end_date=today,
            )
            self.add(subscription)
            self.commit()

        return subscription

    def extend_subscription(
        self,
        subscription: Subscription,
        additional_days: int,
    ) -> Subscription:
        """
        Extiende la fecha de fin de una suscripción por N días.

        Args:
            subscription: Instancia de Subscription a extender.
            additional_days: Número de días a agregar a end_date.

        Returns:
            La misma instancia ya actualizada y persistida.
        """
        subscription.extend(additional_days)
        self.commit()
        return subscription

    def create_from_purchase(self, purchase: Purchase, duration_days: int) -> Subscription:
        """
        Crea (o extiende) una suscripción a partir de un registro de compra.

        Si el usuario ya tiene una suscripción activa para ese servicio,
        la extiende. Si no, crea una nueva con start_date = purchase_date
        y end_date = purchase_date + duration_days.

        Args:
            purchase: Instancia de Purchase con los datos de la compra.
            duration_days: Duración en días de la suscripción.

        Returns:
            La suscripción creada o extendida.
        """
        subscription = self.get_sub_by_user_and_service(
            user_telegram_id=purchase.user_telegram_id,
            service_id=purchase.service_id,
        )

        purchase_date = purchase.purchase_date.date() if hasattr(
            purchase.purchase_date, 'date'
        ) else purchase.purchase_date

        if subscription:
            # Extender suscripción existente
            subscription.end_date = subscription.end_date + timedelta(days=duration_days)
        else:
            # Crear nueva suscripción
            subscription = Subscription(
                user_telegram_id=purchase.user_telegram_id,
                service_id=purchase.service_id,
                start_date=purchase_date,
                end_date=purchase_date + timedelta(days=duration_days),
            )
            self.add(subscription)

        self.commit()
        return subscription

    # ------------------------------------------------------------------
    # Eliminación
    # ------------------------------------------------------------------

    def delete_sub(self, subscription: Subscription) -> None:
        """
        Elimina físicamente una suscripción de la base de datos.

        Args:
            subscription: Instancia de Subscription a eliminar.
        """
        self.delete(subscription)
        self.commit()

    def delete_expired_subs(self) -> int:
        """
        Elimina todas las suscripciones vencidas de la base de datos.

        Returns:
            Número de suscripciones eliminadas.
        """
        expired = self.get_expired_subs()
        count = len(expired)
        for sub in expired:
            self.delete(sub)
        if count > 0:
            self.commit()
        return count
