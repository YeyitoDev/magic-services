"""
Subscription Service - Magic Chatbot v2
========================================
Lógica de negocio central para la gestión de suscripciones y compras.

Este servicio contiene la lógica más importante del negocio:
- Determinar el tipo de servicio según el monto pagado.
- Calcular la duración de la suscripción según rangos de precio.
- Registrar compras (Purchase) y crear/extender suscripciones (Subscription).
- Manejar los distintos escenarios de error (monto no reconocido, usuario no encontrado).

Principios aplicados:
- Single Responsibility: este servicio solo maneja la lógica de compra/suscripción.
- Dependency Inversion: recibe repositorios por constructor, no crea sesiones.
- Fail-fast: valida condiciones al inicio y retorna errores descriptivos.

Uso:
    from services.subscription_service import SubscriptionService

    service = SubscriptionService(user_repo, service_repo, purchase_repo, sub_repo)
    result = service.process_purchase(
        telegram_id=12345,
        price=150.0,
        from_channel="telegram",
    )
    if result.success:
        print(f"Compra registrada: {result.message}")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from utils.datetime_utils import LIMA_TZ, get_lima_time

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------

@dataclass
class PurchaseResult:
    """
    Resultado de una operación de compra/suscripción.

    Attributes:
        success: True si la operación se completó exitosamente.
        message: Mensaje descriptivo para el usuario o para logs.
        service_type: Tipo de servicio determinado ("stake", "grupo_vip").
        service_id: ID del servicio en la base de datos (1=Stake, 2=Grupo VIP).
        duration_months: Duración en meses de la suscripción (0 para Stake).
        is_subscription: True si es suscripción recurrente, False si es pago único.
        end_date: Fecha de vencimiento de la suscripción (None para Stake).
    """
    
    
    success: bool = False
    message: str = ""
    service_type: str = ""
    service_id: int = 0
    duration_months: int = 0
    is_subscription: bool = False
    end_date: datetime | None = None
    price: float = 0.0
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constantes de negocio
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Subscription Service
# ---------------------------------------------------------------------------

class SubscriptionService:
    """
    Servicio de lógica de negocio para compras y suscripciones.

    Orquesta el proceso completo de compra:
    1. Determina el tipo de servicio según el monto.
    2. Valida que el usuario exista.
    3. Determina la duración de la suscripción (si aplica).
    4. Registra la compra (Purchase).
    5. Crea o extiende la suscripción (Subscription).

    Dependencias:
        user_repo: UserRepository para búsqueda de usuarios.
        service_repo: ServiceRepository para búsqueda de servicios/precios.
        purchase_repo: PurchaseRepository para registro de compras.
        subscription_repo: SubscriptionRepository para gestión de suscripciones.
    """

    def __init__(self, user_repo, service_repo, purchase_repo, subscription_repo, pricing_service=None):
        """
        Inicializa el servicio con sus dependencias.

        Args:
            user_repo: Repositorio de usuarios.
            service_repo: Repositorio de servicios.
            purchase_repo: Repositorio de compras.
            subscription_repo: Repositorio de suscripciones.
            pricing_service: Servicio de precios dinámico (opcional).
        """
        self._user_repo = user_repo
        self._service_repo = service_repo
        self._purchase_repo = purchase_repo
        self._subscription_repo = subscription_repo
        self._pricing_service = pricing_service

    # ------------------------------------------------------------------
    # Método principal: procesar compra
    # ------------------------------------------------------------------

    def process_purchase(
        self,
        telegram_id: int,
        price: float,
        from_channel: str,
        purchase_date: str | None = None,
    ) -> PurchaseResult:
        """
        Procesa la compra de un servicio por parte de un usuario.

        Flujo completo:
        1. Valida que el usuario exista en la base de datos.
        2. Determina el tipo de servicio (Stake vs Grupo VIP) según el monto.
        3. Para Grupo VIP, determina la duración según el rango de precio.
        4. Registra la compra (Purchase).
        5. Si es suscripción, crea o extiende la suscripción (Subscription).
        6. Retorna un PurchaseResult con el resultado.

        Args:
            telegram_id: ID de Telegram del usuario comprador.
            price: Monto pagado (en soles peruanos).
            from_channel: Canal de origen de la compra (ej: "telegram", "whatsapp").
            purchase_date: Fecha de compra en formato 'ddmmyyyy'.
                           Si es None, se usa la fecha/hora actual en Lima.

        Returns:
            PurchaseResult con success=True/False, mensaje descriptivo,
            y metadatos del servicio adquirido.

        Example:
            >>> result = service.process_purchase(12345, 150.0, "telegram")
            >>> if result.success:
            ...     print(f"Compra exitosa: {result.service_type}")
        """
        # --- Paso 0: Parsear fecha de compra ---
        purchase_dt = self._resolve_purchase_date(purchase_date)

        # --- Paso 1: Validar que el usuario exista ---
        user = self._user_repo.get_by_telegram_id(telegram_id)
        if user is None:
            return PurchaseResult(
                success=False,
                message="Usuario no encontrado en la base de datos.",
                errors=["user_not_found"],
            )

        # --- Paso 2: Determinar tipo de servicio ---
        service_type, service_id = self._determine_service_type(price)

        if service_type is None:
            return PurchaseResult(
                success=False,
                message=f"El monto S/ {price:.2f} no corresponde a ningún servicio válido.",
                errors=["invalid_amount"],
            )

        # --- Paso 3: Determinar duración si es suscripción ---
        duration_months = 0
        duration_days = 0
        is_subscription = False
        end_date = None

        if service_type == "grupo_vip":
            plan = self._determine_vip_plan(price)
            if plan is None:
                return PurchaseResult(
                    success=False,
                    message=(
                        f"El monto S/ {price:.2f} no corresponde a un plan VIP válido. "
                        f"Planes: 1 mes S/ 90-130, 2 meses S/ 140-180, 3 meses S/ 190-230."
                    ),
                    errors=["invalid_vip_amount"],
                )
            duration_months = plan["duration_months"]
            duration_days = plan["duration_days"]
            is_subscription = True

        # --- Pasos 4 y 5: Registrar compra y suscripción de forma ATÓMICA ---
        # La compra y la suscripción comparten la misma sesión y se confirman
        # en un único commit. Si la suscripción falla, se revierte también la
        # compra (no quedan compras "huérfanas" sin suscripción).
        try:
            self._purchase_repo.create_purchase(
                user_telegram_id=telegram_id,
                service_id=service_id,
                price=price,
                from_channel=from_channel,
                purchase_date=purchase_dt,
                commit=False,
            )

            if is_subscription:
                subscription = self._create_or_extend_subscription(
                    telegram_id=telegram_id,
                    service_id=service_id,
                    purchase_date=purchase_dt,
                    duration_days=duration_days,
                    commit=False,
                )
                end_date = subscription.end_date
                was_created = (
                    subscription.start_date
                    == subscription.end_date - timedelta(days=duration_days)
                )
                message = (
                    f"Suscripción {service_type} "
                    f"{'creada' if was_created else 'extendida'}. "
                    f"Fecha de vencimiento: {end_date.strftime('%d/%m/%Y')}."
                )
            else:
                # Stake: pago único, sin suscripción
                message = f"Registro exitoso para {service_type} (pago único)."

            # Commit único: confirma compra (+ suscripción) atómicamente.
            self._purchase_repo.commit()
            logger.info(
                f"Compra procesada (atómica): user={telegram_id}, "
                f"service={service_type}, price={price}, channel={from_channel}, "
                f"end_date={end_date}"
            )
        except Exception as e:
            # Revertir TODO: ni compra ni suscripción quedan registradas.
            self._purchase_repo.rollback()
            logger.error(
                f"Error atómico al procesar compra para user={telegram_id}: {e}",
                exc_info=True,
            )
            return PurchaseResult(
                success=False,
                message=(
                    f"Error al procesar la compra: {str(e)}. "
                    f"No se registró ningún cambio."
                ),
                service_type=service_type,
                service_id=service_id,
                errors=["purchase_transaction_failed", str(e)],
            )

        return PurchaseResult(
            success=True,
            message=message,
            service_type=service_type,
            service_id=service_id,
            duration_months=duration_months,
            is_subscription=is_subscription,
            end_date=end_date,
            price=price,
        )

    # ------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------

    def _resolve_purchase_date(
        self, purchase_date_str: str | None
    ) -> datetime:
        """
        Convierte una fecha de compra en string a datetime con timezone Lima.

        Si no se proporciona fecha, usa la fecha/hora actual en Lima.

        Args:
            purchase_date_str: Fecha en formato 'ddmmyyyy' o None.

        Returns:
            Datetime con timezone America/Lima.

        Raises:
            ValueError: Si el formato de fecha es inválido.
        """
        if purchase_date_str is None:
            return get_lima_time()

        try:
            naive_dt = datetime.strptime(purchase_date_str, "%d%m%Y")
            return LIMA_TZ.localize(naive_dt)
        except ValueError as e:
            raise ValueError(
                f"Formato de fecha inválido: '{purchase_date_str}'. "
                f"Use el formato 'ddmmyyyy' (ej: 15012025)."
            ) from e

    def _determine_service_type(self, price: float) -> tuple:
        """
        Determina el tipo de servicio según el monto pagado.

        Usa el PricingService (DB-driven) si está disponible; si no,
        aplica fallback legacy basado en umbral fijo (>50 = VIP, <=50 = Stake).

        Args:
            price: Monto pagado.

        Returns:
            Tupla (service_type, service_id) donde:
            - service_type: "stake" o "grupo_vip".
            - service_id: ID del servicio correspondiente.
            - Si el monto no es válido, retorna (None, 0).
        """
        if self._pricing_service:
            plan = self._pricing_service.match_price(price)
            if plan:
                service_type = "grupo_vip" if plan.service_id == 2 else "stake"
                return (service_type, plan.service_id)
        # Fallback legacy
        if price > 50:
            return ("grupo_vip", 2)
        elif 0 < price <= 50:
            return ("stake", 1)
        return (None, 0)

    def _determine_vip_plan(self, price: float) -> dict | None:
        """
        Determina el plan VIP según el monto pagado.

        Usa el PricingService (DB-driven) si está disponible; si no,
        retorna None para que se use el comportamiento legacy.

        Args:
            price: Monto pagado por el usuario.

        Returns:
            Diccionario con la info del plan (min_amount, max_amount,
            duration_months, duration_days), o None.
        """
        if self._pricing_service:
            plan = self._pricing_service.match_price(price)
            if plan and plan.service_id == 2:
                return {
                    "min_amount": plan.price - plan.discount - 5,
                    "max_amount": plan.price + 5,
                    "duration_months": plan.duration_months,
                    "duration_days": plan.duration_months * 30,
                }
        return None

    def _create_or_extend_subscription(
        self,
        telegram_id: int,
        service_id: int,
        purchase_date: datetime,
        duration_days: int,
        commit: bool = True,
    ):
        """
        Crea una nueva suscripción o extiende una existente.

        Si el usuario ya tiene una suscripción activa para este servicio,
        se extiende la fecha de fin. Si no, se crea una nueva con
        start_date = fecha de compra y end_date = start_date + duration_days.

        Args:
            telegram_id: ID de Telegram del usuario.
            service_id: ID del servicio.
            purchase_date: Fecha de la compra.
            duration_days: Duración en días de la suscripción.

        Returns:
            La suscripción creada o extendida.
        """
        # Buscar suscripción existente (activa o no)
        subscription = self._subscription_repo.get_sub_by_user_and_service(
            user_telegram_id=telegram_id,
            service_id=service_id,
        )

        purchase_date_only = purchase_date.date() if hasattr(
            purchase_date, 'date'
        ) else purchase_date

        if subscription:
            # Extender suscripción existente desde su end_date actual
            subscription = self._subscription_repo.extend_subscription(
                subscription=subscription,
                additional_days=duration_days,
                commit=False,
            )
            # Asegurar que is_active esté a True al extender
            subscription.is_active = True
            if commit:
                self._subscription_repo.commit()
            logger.info(
                f"Suscripción extendida: user={telegram_id}, "
                f"service_id={service_id}, nueva end_date={subscription.end_date}"
            )
        else:
            # Crear nueva suscripción
            from models.subscription import Subscription

            subscription = Subscription(
                user_telegram_id=telegram_id,
                service_id=service_id,
                start_date=purchase_date_only,
                end_date=purchase_date_only + timedelta(days=duration_days),
                is_active=True,
            )
            self._subscription_repo.add(subscription)
            if commit:
                self._subscription_repo.commit()
            logger.info(
                f"Suscripción creada: user={telegram_id}, "
                f"service_id={service_id}, end_date={subscription.end_date}"
            )

        return subscription

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_active_subscriptions(self) -> list:
        """
        Obtiene todas las suscripciones activas.

        Returns:
            Lista de Subscription vigentes (end_date >= hoy).
        """
        return self._subscription_repo.get_active_subs()

    def get_user_active_subscriptions(self, telegram_id: int) -> list:
        """
        Obtiene las suscripciones activas de un usuario.

        Args:
            telegram_id: ID de Telegram del usuario.

        Returns:
            Lista de Subscription activas del usuario.
        """
        return self._subscription_repo.get_active_sub(telegram_id)

    def get_expired_subscriptions(self) -> list:
        """
        Obtiene suscripciones vencidas para el proceso de limpieza.

        Returns:
            Lista de Subscription con end_date < hoy.
        """
        return self._subscription_repo.get_expired_subs()

    def get_expiring_soon(self, days: int = 3) -> list:
        """
        Obtiene suscripciones que vencerán pronto.

        Args:
            days: Días de anticipación.

        Returns:
            Lista de Subscription próximas a vencer.
        """
        return self._subscription_repo.get_expiring_soon(days)

    def cancel_subscription(self, telegram_id: int, service_id: int) -> bool:
        """
        Cancela (elimina) una suscripción de un usuario.

        Args:
            telegram_id: ID de Telegram del usuario.
            service_id: ID del servicio a cancelar.

        Returns:
            True si se eliminó correctamente, False si no existía.
        """
        subscription = self._subscription_repo.get_sub_by_user_and_service(
            user_telegram_id=telegram_id,
            service_id=service_id,
        )
        if subscription:
            self._subscription_repo.delete_sub(subscription)
            logger.info(
                f"Suscripción cancelada: user={telegram_id}, "
                f"service_id={service_id}"
            )
            return True
        return False

    def delete_expired_subscriptions(self) -> int:
        """
        Elimina todas las suscripciones vencidas de la base de datos.

        Returns:
            Número de suscripciones eliminadas.
        """
        count = self._subscription_repo.delete_expired_subs()
        logger.info(f"Limpieza de suscripciones: {count} expiradas eliminadas.")
        return count

    def get_service_name(self, service_id: int) -> str | None:
        """
        Obtiene el nombre del servicio dado su ID.

        Args:
            service_id: ID del servicio.

        Returns:
            Nombre del servicio o None.
        """
        return self._service_repo.get_service_name(service_id)
