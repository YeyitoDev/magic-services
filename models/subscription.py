"""
Modelo Subscription - Magic Chatbot v2
=======================================
Representa la suscripción activa de un usuario a un servicio por un periodo
determinado. Incluye propiedades para verificar vigencia y días restantes.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Column, Date, ForeignKey, Integer
from sqlalchemy.orm import relationship

from models.base import BaseModel

if TYPE_CHECKING:
    from models.service import Service
    from models.user import User


class Subscription(BaseModel):
    """
    Suscripción de un usuario a un servicio con fecha de inicio y fin.

    Representa el periodo durante el cual un usuario tiene acceso a un
    servicio por suscripción (ej: Grupo VIP por 1, 2 o 3 meses).

    Attributes:
        subscription_id (int): PK autoincremental.
        user_telegram_id (int): FK al usuario suscrito.
        service_id (int): FK al servicio contratado.
        start_date (date): Fecha de inicio de la suscripción.
        end_date (date): Fecha de vencimiento de la suscripción.
        is_active (bool): Columna - True si la suscripción está activa (no cancelada).
        user (User): Relación inversa al usuario.
        service (Service): Relación inversa al servicio.

    Properties:
        is_valid (bool): True si end_date >= hoy (vigente por fecha).
        days_remaining (int): Días restantes hasta el vencimiento (negativo si ya expiró).
    """

    __tablename__ = "subscriptions"

    subscription_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_telegram_id = Column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    service_id = Column(
        Integer, ForeignKey("services.service_id"), nullable=False
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, doc="True si la suscripción está activa")

    # ------------------------------------------------------------------
    # Relaciones inversas
    # ------------------------------------------------------------------

    user: "User" = relationship(
        "User",
        back_populates="subscriptions",
        lazy="selectin",
    )
    service: "Service" = relationship(
        "Service",
        back_populates="subscriptions",
        lazy="selectin",
    )

    # ------------------------------------------------------------------
    # Propiedades de dominio
    # ------------------------------------------------------------------

    @property
    def is_valid(self) -> bool:
        """True si end_date >= hoy (vigente por fecha)."""
        return self.end_date >= date.today()

    @property
    def days_remaining(self) -> int:
        """
        Calcula los días restantes hasta el vencimiento.

        Returns:
            Número de días que faltan para que expire la suscripción.
            Puede ser negativo si ya expiró.
        """
        delta = self.end_date - date.today()
        return delta.days

    # ------------------------------------------------------------------
    # Métodos de utilidad
    # ------------------------------------------------------------------

    def extend(self, additional_days: int) -> None:
        """
        Extiende la fecha de fin de la suscripción por N días adicionales.

        Args:
            additional_days: Número de días a agregar a end_date.
        """
        from datetime import timedelta

        self.end_date = self.end_date + timedelta(days=additional_days)

    def __repr__(self) -> str:
        return (
            f"Subscription(subscription_id={self.subscription_id}, "
            f"user_telegram_id={self.user_telegram_id}, "
            f"service_id={self.service_id}, "
            f"start_date={self.start_date!r}, "
            f"end_date={self.end_date!r}, "
            f"is_active={self.is_active}, is_valid={self.is_valid})"
        )
