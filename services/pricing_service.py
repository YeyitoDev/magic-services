"""
Dynamic Pricing Service - Magic Chatbot v2
===========================================
Servicio centralizado para consulta de precios desde la base de datos
con caché en JSON para evitar consultas repetitivas a la BD.

Principios:
- Single Source of Truth: la tabla service_prices es la única fuente.
- Caché inteligente: carga inicial desde BD → JSON, se refresca cada 30 min.
- Generación dinámica: mensajes de precios y teclados se arman desde los datos.
- Fail-safe: si la BD falla, usa el caché JSON.

Flujo:
1. Al iniciar → carga precios desde BD → guarda en pricing_cache.json
2. En cada consulta → sirve desde RAM (caché en memoria)
3. Cada 30 min → refresca desde BD
4. Si BD falla → usa caché JSON como fallback

Para agregar un nuevo plan solo se necesita:
    INSERT INTO service_prices (service_id, price, discount, duration_months)
    VALUES (2, 350, 20, 6);

Uso:
    from services.pricing_service import PricingService

    pricing = PricingService(service_repo)
    plan = pricing.match_price(amount=90)  # → ServicePrice(duration_months=1)
    mensaje = pricing.generate_pricing_message(service_id=2)
    teclado = pricing.generate_confirmation_keyboard(user_id=123, amount=100)
"""

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.service import ServicePrice

logger = logging.getLogger(__name__)

CACHE_FILE = "pricing_cache.json"
CACHE_TTL_SECONDS = 1800  # 30 minutos


class PricingService:
    """
    Servicio de precios dinámico con caché en dos niveles (RAM + JSON).

    Attributes:
        _service_repo: Repositorio de servicios para consultar la BD.
        _cache: Lista de ServicePrice en memoria (nivel 1).
        _cache_updated_at: Timestamp de última actualización.
        _lock: Thread lock para thread-safety.
    """

    def __init__(self, service_repo) -> None:
        self._service_repo = service_repo
        self._cache: List[ServicePrice] = []
        self._cache_updated_at: Optional[datetime] = None
        self._lock = threading.Lock()

        # Cargar caché al iniciar
        self._load_cache()
        logger.info(f"PricingService inicializado: {len(self._cache)} precios cacheados.")

    # ------------------------------------------------------------------
    # Carga de caché (RAM + JSON fallback)
    # ------------------------------------------------------------------

    def _load_cache(self) -> None:
        """Carga precios desde BD, con fallback a JSON si la BD no responde."""
        try:
            prices = self._fetch_from_db()
            if prices:
                self._save_to_json(prices)
                with self._lock:
                    self._cache = prices
                    self._cache_updated_at = datetime.now()
                logger.debug(f"Caché actualizado desde BD: {len(prices)} precios.")
                return
        except Exception as e:
            logger.warning(f"No se pudo cargar precios desde BD: {e}")

        # Fallback: cargar desde JSON
        prices = self._load_from_json()
        if prices:
            with self._lock:
                self._cache = prices
                self._cache_updated_at = datetime.now()
            logger.warning(f"Caché cargado desde JSON (fallback): {len(prices)} precios.")
        else:
            logger.error("No se encontraron precios en BD ni en caché JSON.")

    def _fetch_from_db(self) -> List[ServicePrice]:
        """Obtiene todos los ServicePrice desde la BD."""
        return self._service_repo._session.query(ServicePrice).all()

    def _save_to_json(self, prices: List[ServicePrice]) -> None:
        """Guarda los precios en el archivo JSON de caché."""
        data = {
            "updated_at": datetime.now().isoformat(),
            "prices": [
                {
                    "service_price_id": p.service_price_id,
                    "service_id": p.service_id,
                    "price": p.price,
                    "discount": p.discount,
                    "duration_months": p.duration_months,
                }
                for p in prices
            ],
        }
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"No se pudo guardar caché JSON: {e}")

    def _load_from_json(self) -> List[ServicePrice]:
        """Carga precios desde el archivo JSON de caché."""
        if not os.path.exists(CACHE_FILE):
            return []
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
            return [
                ServicePrice(
                    service_price_id=p["service_price_id"],
                    service_id=p["service_id"],
                    price=p["price"],
                    discount=p["discount"],
                    duration_months=p["duration_months"],
                )
                for p in data.get("prices", [])
            ]
        except Exception as e:
            logger.warning(f"No se pudo cargar caché JSON: {e}")
            return []

    # ------------------------------------------------------------------
    # Refresh automático del caché
    # ------------------------------------------------------------------

    def _should_refresh(self) -> bool:
        """Verifica si el caché necesita refrescarse (TTL expirado)."""
        if self._cache_updated_at is None:
            return True
        elapsed = (datetime.now() - self._cache_updated_at).total_seconds()
        return elapsed >= CACHE_TTL_SECONDS

    def refresh_cache(self) -> None:
        """Fuerza un refresco del caché desde BD."""
        self._load_cache()

    def get_cache_age_seconds(self) -> float:
        """Retorna la antigüedad del caché en segundos."""
        if self._cache_updated_at is None:
            return float("inf")
        return (datetime.now() - self._cache_updated_at).total_seconds()

    # ------------------------------------------------------------------
    # Consultas de precios
    # ------------------------------------------------------------------

    def get_all_prices(self) -> List[ServicePrice]:
        """Obtiene todos los precios (con auto-refresh si TTL expiró)."""
        if self._should_refresh():
            self._load_cache()
        with self._lock:
            return list(self._cache)

    def get_prices_for_service(self, service_id: int) -> List[ServicePrice]:
        """Obtiene los precios de un servicio específico."""
        all_prices = self.get_all_prices()
        return [p for p in all_prices if p.service_id == service_id]

    def match_price(self, amount: float) -> Optional[ServicePrice]:
        """
        Encuentra el plan que corresponde a un monto pagado.

        Busca coincidencia exacta con price o price - discount.
        Si no hay coincidencia exacta, busca el más cercano.

        Args:
            amount: Monto pagado por el usuario.

        Returns:
            ServicePrice que coincide, o None si no se encuentra.
        """
        all_prices = self.get_all_prices()

        # Búsqueda exacta: price == amount o (price - discount) == amount
        for p in all_prices:
            if p.price == amount or (p.price - p.discount) == amount:
                return p

        # Búsqueda por rango (±5% de tolerancia)
        for p in all_prices:
            effective = p.price - p.discount
            if abs(effective - amount) <= effective * 0.05:
                return p

        return None

    def get_service_type(self, amount: float) -> Optional[str]:
        """
        Determina el tipo de servicio según el monto:
        - > 50 → grupo_vip
        - <= 50 → stake

        Args:
            amount: Monto pagado.

        Returns:
            "stake" o "grupo_vip", o None si no es válido.
        """
        plan = self.match_price(amount)
        if plan is None:
            return None
        # service_id 1 = Stake, 2 = Grupo VIP
        return "grupo_vip" if plan.service_id == 2 else "stake"

    # ------------------------------------------------------------------
    # Generación dinámica de mensajes y teclados
    # ------------------------------------------------------------------

    def generate_pricing_message(self, service_id: int) -> str:
        """
        Genera el mensaje de precios dinámicamente desde los datos cacheados.

        Args:
            service_id: ID del servicio (1=Stake, 2=Grupo VIP).

        Returns:
            Mensaje formateado con precios y cuentas bancarias.
        """
        prices = sorted(
            self.get_prices_for_service(service_id),
            key=lambda p: p.price,
        )

        if not prices:
            return "Precios no disponibles. Contacta a @magic_peru."

        if service_id == 1:  # Stake
            return (
                "🎲 *STAKE DE MÁXIMA SEGURIDAD*\n\n"
                f"💰 *Precio: S/ {prices[0].price:.0f}*\n\n"
                "Los números de cuenta son los siguientes mi hermano 🔮\n\n"
                "Titular: José González Reategui\n"
                "Yape/Plin: 952903700\n"
                "BCP: 19402020623033\n"
                "SCOTIA: 1780142814\n\n"
                "Solo envía la captura de tu transferencia por este medio 📲"
            )
        else:  # Grupo VIP
            lines = ["💎 *GRUPO VIP - PRECIOS EXCLUSIVOS*\n"]

            for p in prices:
                months = p.duration_months
                price = int(p.price)
                discount = int(p.discount)
                effective = price - discount

                if discount > 0:
                    lines.append(
                        f"🔥 *{months} mes(es)* = S/ {price} "
                        f"→ *S/ {effective}* (¡ahorra S/ {discount}!)"
                    )
                else:
                    lines.append(f"• *{months} mes(es)* = S/ {price}")

            lines.append("")
            lines.append("Los números de cuenta son los siguientes mi hermano 🔮")
            lines.append("")
            lines.append("Titular: José González Reategui")
            lines.append("Yape/Plin: 952903700")
            lines.append("BCP: 19402020623033")
            lines.append("SCOTIA: 1780142814")
            lines.append("")
            lines.append("Solo envía la captura de tu transferencia por este medio 📲")

            return "\n".join(lines)

    def generate_confirmation_keyboard(
        self, user_id: int, amount: float = 0, source: str = "telegram"
    ) -> Any:
        """
        Genera el teclado de confirmación manual dinámicamente.

        Args:
            user_id: ID del usuario.
            amount: Monto detectado (opcional).
            source: Canal de origen.

        Returns:
            InlineKeyboardMarkup con botones generados desde los precios.
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = []

        # Precios de Stake (service_id=1)
        stake_prices = self.get_prices_for_service(1)
        for p in stake_prices:
            keyboard.append([
                InlineKeyboardButton(
                    f"🎯 STAKE (S/ {int(p.price)})",
                    callback_data=f"buttom_validar_monto:valid:{user_id}:{int(p.price)}",
                )
            ])

        # Precios de VIP (service_id=2)
        vip_prices = sorted(
            self.get_prices_for_service(2), key=lambda p: p.duration_months
        )
        for p in vip_prices:
            months = p.duration_months
            vip_price = int(p.price)  # Show original price, not discounted
            keyboard.append([
                InlineKeyboardButton(
                    f"💎 VIP {months} {'Mes' if months == 1 else 'Meses'} (S/ {vip_price})",
                    callback_data=f"buttom_validar_monto:valid:{user_id}:{vip_price}",
                )
            ])

        # Botón cancelar
        keyboard.append([
            InlineKeyboardButton(
                "❌ CANCELAR",
                callback_data=f"buttom_validar_monto:cancel:{user_id}",
            )
        ])

        return InlineKeyboardMarkup(keyboard)

    def get_vip_threshold(self) -> float:
        """Retorna el umbral que separa Stake de VIP (precio máximo de Stake)."""
        stake_prices = self.get_prices_for_service(1)
        if stake_prices:
            return max(p.price for p in stake_prices)
        return 50.0  # default


# Singleton global
_pricing_service: Optional[PricingService] = None


def get_pricing_service(service_repo=None) -> PricingService:
    """Obtiene la instancia singleton de PricingService."""
    global _pricing_service
    if _pricing_service is None and service_repo is not None:
        _pricing_service = PricingService(service_repo)
    return _pricing_service
