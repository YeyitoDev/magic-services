"""
Modelo Purchase: representa la compra de un servicio por parte de un usuario.

Registra cada transacción de compra con el monto exacto pagado, la fecha,
y el canal de procedencia (telegram, whatsapp, etc.).
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from models.base import BaseModel

if TYPE_CHECKING:
    from models.service import Service
    from models.user import User


class Purchase(BaseModel):
    """
    Registro de compra de un servicio por un usuario.

    Cada fila representa una transacción de compra única, con el precio
    pagado en el momento de la compra y el canal desde el cual se originó.

    Attributes:
        purchase_id (int): PK autoincremental.
        user_telegram_id (int): FK al usuario que realizó la compra.
        service_id (int): FK al servicio adquirido.
        purchase_date (datetime): Fecha y hora exacta de la compra.
        price (float): Precio pagado por el servicio.
        from_channel (str): Canal de origen (ej: 'telegram', 'whatsapp', 'wsp').
        user (User): Relación inversa al usuario comprador.
        service (Service): Relación inversa al servicio comprado.
    """

    __tablename__ = "purchases"

    purchase_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_telegram_id = Column(
        BigInteger, ForeignKey("users.telegram_id"), nullable=False
    )
    service_id = Column(
        Integer, ForeignKey("services.service_id"), nullable=False
    )
    purchase_date = Column(DateTime, nullable=False, default=datetime.now)
    price = Column(Float, nullable=False)
    from_channel = Column(String(255), nullable=False)

    # ------------------------------------------------------------------
    # Relaciones inversas
    # ------------------------------------------------------------------

    user: "User" = relationship(
        "User",
        back_populates="purchases",
        lazy="selectin",
    )
    service: "Service" = relationship(
        "Service",
        back_populates="purchases",
        lazy="selectin",
    )

    # ------------------------------------------------------------------
    # Métodos de utilidad
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Purchase(purchase_id={self.purchase_id}, "
            f"user_telegram_id={self.user_telegram_id}, "
            f"service_id={self.service_id}, "
            f"price={self.price}, "
            f"from_channel={self.from_channel!r}, "
            f"purchase_date={self.purchase_date!r})"
        )
