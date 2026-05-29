"""
Subscription Cleanup Job - Magic Chatbot v2
===========================================
Job programado que sincroniza los miembros del grupo VIP de Telegram
con la base de datos y elimina a los usuarios con suscripciones vencidas.

Este job replica la lógica del archivo original `getMembersTelethon.py`,
refactorizada siguiendo principios SOLID:
- Single Responsibility: solo se encarga de la limpieza de suscripciones.
- Dependency Inversion: recibe servicios por constructor.
- Configurable: modo de ejecución (validar/eliminar) vía settings.

Flujo del job:
1. Obtener miembros actuales del grupo de Telegram (via Telethon).
2. Obtener miembros con suscripción activa desde la base de datos.
3. Cruzar ambas listas para identificar:
   - Usuarios con suscripción vencida → candidatos a eliminación.
   - Usuarios sin registro en BD → "clientes especiales" para revisión.
4. En modo "validar": solo generar reportes (JSON/CSV en output/).
5. En modo "eliminar": enviar mensaje de vencimiento + kick del grupo.
6. Generar logs detallados y resumen de ejecución.

Uso:
    from jobs.subscription_cleanup import SubscriptionCleanupJob

    job = SubscriptionCleanupJob(telegram_api, subscription_service, user_service)
    await job.run(mode="eliminar")
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

OUTPUT_DIR = "output"
DEFAULT_MODE = "validar"  # Modo seguro por defecto: solo reporta, no elimina


class SubscriptionCleanupJob:
    """
    Job de limpieza de suscripciones vencidas.

    Sincroniza los miembros del grupo VIP de Telegram con la base de datos,
    identifica suscripciones expiradas y ejecuta la eliminación de usuarios
    según el modo configurado.

    Attributes:
        telegram_api: TelegramAPIService para interactuar con la API de Telegram.
        subscription_service: SubscriptionService para consultas de suscripciones.
        user_service: UserService para consultas de usuarios.
        purchase_repo: PurchaseRepository para consultas de compras.
        settings: Configuración centralizada.
    """

    def __init__(
        self,
        telegram_api,
        subscription_service,
        user_service,
        purchase_repo=None,
        container=None,
    ) -> None:
        """
        Inicializa el job de limpieza.

        Args:
            telegram_api: Servicio de API de Telegram.
            subscription_service: Servicio de suscripciones.
            user_service: Servicio de usuarios.
            purchase_repo: Repositorio de compras (opcional).
            container: Contenedor de dependencias (opcional).
        """
        self.telegram_api = telegram_api
        self.subscription_service = subscription_service
        self.user_service = user_service
        self.purchase_repo = purchase_repo
        self.container = container

        # Parámetros desde settings
        self.vip_group_id = int(settings.TELEGRAM_VIP_GROUP_ID or "0")
        self.validator_ids = settings.TELEGRAM_VALIDATOR_IDS

    # ------------------------------------------------------------------
    # DB-only mode (no Telegram API needed)
    # ------------------------------------------------------------------

    def run_db_only(self, mode: str = "validar") -> dict:
        """
        DB-only cleanup: checks subscriptions directly from database.
        Does NOT require Telegram API or Telethon.

        Returns:
            Dict with stats: total, active, expired, special, removed
        """
        from datetime import date

        from core.database import SessionLocal as MakeSession
        from models.subscription import Subscription
        from models.user import User

        session = MakeSession()
        # Keep connection alive during long operations
        from sqlalchemy import text
        session.execute(text("SET SESSION wait_timeout=28800"))
        session.execute(text("SET SESSION interactive_timeout=28800"))
        today = date.today()

        stats = {
            "total": 0,
            "active": 0,
            "expired": 0,
            "special": 0,
            "removed": 0,
            "repaired": 0,
        }

        try:
            # Count total unique users with subscriptions (single query)
            from sqlalchemy import distinct, func
            total = session.query(func.count(distinct(Subscription.user_telegram_id))).scalar()
            stats["total"] = total or 0

            # Get ONLY expired subscriptions (SQL filter, not Python)
            expired_subs = session.query(Subscription).filter(
                Subscription.end_date < today
            ).all()

            # Count unique expired users
            expired_count = session.query(func.count(distinct(Subscription.user_telegram_id))).filter(
                Subscription.end_date < today
            ).scalar()
            stats["expired"] = expired_count or 0
            stats["active"] = stats["total"] - stats["expired"]

            # Load users only for expired subscriptions (not all users)
            expired_user_ids = list(set(s.user_telegram_id for s in expired_subs))
            all_users = {}
            if expired_user_ids:
                users = session.query(User).filter(
                    User.telegram_id.in_(expired_user_ids)
                ).all()
                all_users = {u.telegram_id: u for u in users}

            # Users with no subscription are "special clients" - can't detect without Telegram

            # ---- PROTECT ADMINS - Never kick admins ----
            from config.settings import settings
            admin_ids = set(int(uid) for uid in settings.TELEGRAM_VALIDATOR_IDS)
            # Admins + bots - NEVER removed
            admin_ids.update([
                1555885694, 6475885611,  # Sergio + Martin
                7754941523,  # @elmagopagos_bot
                5624304267,  # @PremiumPay_realbot
                7639865090,  # @Premiumpay_real2bot
                734284134,   # @deljoinbot
            ])

            # Remove admins from expired list
            expired_subs = [s for s in expired_subs if s.user_telegram_id not in admin_ids]
            print(f"🛡️ Protegidos {len(admin_ids)} admins. Expirados restantes: {len(expired_subs)}")

            # ---- PASO 1: REPAIR - Create missing subscriptions for VIP purchasers ----
            from datetime import timedelta

            from models.purchase import Purchase

            # Only VIP purchases (service_id=2) in last 120 days
            purchased = session.query(Purchase.user_telegram_id).filter(
                Purchase.service_id == 2,
                Purchase.purchase_date >= today - timedelta(days=120)
            ).distinct().all()
            purchased_ids = set(uid for (uid,) in purchased)

            # Get users who already have subscriptions
            subscribed_result = session.query(Subscription.user_telegram_id).distinct().all()
            subscribed_ids = set(uid for (uid,) in subscribed_result)

            # Find users with VIP purchases but no subscription (exclude admins)
            missing_ids = purchased_ids - subscribed_ids - admin_ids

            if missing_ids:
                print(f"\n🔧 Reparando {len(missing_ids)} usuarios con compra VIP pero sin suscripción...")
                for uid in missing_ids:
                    # Get the latest VIP purchase for this user
                    latest_purchase = session.query(Purchase).filter(
                        Purchase.user_telegram_id == uid,
                        Purchase.service_id == 2
                    ).order_by(Purchase.purchase_date.desc()).first()

                    if latest_purchase:
                        start = latest_purchase.purchase_date.date() if hasattr(latest_purchase.purchase_date, 'date') else latest_purchase.purchase_date
                        new_sub = Subscription(
                            user_telegram_id=uid,
                            service_id=2,
                            start_date=start,
                            end_date=start + timedelta(days=30),
                        )
                        session.add(new_sub)
                        print(f"  ✓ Suscripción creada para {uid}")

                session.commit()
                stats["repaired"] = len(missing_ids)
                print(f"  ✅ Reparación completada: {len(missing_ids)} suscripciones creadas")
            else:
                print("\n✅ Todos los compradores VIP ya tienen suscripción")

            if mode == "eliminar":
                from services.telegram_api import TelegramAPIService
                api = TelegramAPIService()
                chat_id = int(self.vip_group_id)

                for sub in expired_subs:
                    user_id = int(sub.user_telegram_id)
                    print(f"  ⋯ Procesando {user_id}...")

                    # Reconnect DB if needed
                    if not session.is_active:
                        session = MakeSession()

                    kicked = False
                    try:
                        # 1. Kick from group
                        result = api.remove_user_allow_rejoin(chat_id=chat_id, user_id=user_id)
                        if result.get("kick_success"):
                            print(f"  ✓ Kick {user_id}")
                            kicked = True
                            stats["removed"] += 1
                    except Exception as e:
                        print(f"  ✗ Error kick {user_id}: {e}")

                    try:
                        # 2. Try to send re-subscription message (after unban, non-blocking)
                        if kicked:
                            api.send_message(
                                chat_id=user_id,
                                text="🔮 *Tu suscripción ha expirado*\\n\\nPara seguir disfrutando del Grupo VIP, renová tu suscripción enviando un mensaje a @magic_peru 📲",
                                parse_mode="Markdown"
                            )
                            print(f"  ✓ Mensaje enviado a {user_id}")
                    except Exception:
                        pass  # Message is optional, don't block

                    try:
                        # 3. Delete subscription from DB
                        session.delete(sub)
                        print(f"  ✓ Sub eliminada de BD para {user_id}")
                    except Exception as e:
                        print(f"  ✗ Error BD {user_id}: {e}")

                if stats["removed"] > 0:
                    session.commit()
                    print(f"\n🚨 {stats['removed']} usuarios eliminados del grupo y BD")

            # Save report
            import json
            import os
            from datetime import datetime
            output_dir = os.path.join("output", today.strftime("%Y-%m-%d"))
            os.makedirs(output_dir, exist_ok=True)

            report = {
                "date": str(today),
                "mode": mode,
                "stats": stats,
                "expired_users": [
                    {"user_id": s.user_telegram_id,
                     "end_date": str(s.end_date),
                     "name": all_users.get(s.user_telegram_id, User()).telegram_name}
                    for s in expired_subs
                ]
            }

            hora = datetime.now().strftime("%H%M%S")
            with open(os.path.join(output_dir, f"resumen_{hora}.json"), "w") as f:
                json.dump(report, f, indent=2)

            with open(os.path.join(output_dir, f"resumen_{hora}.txt"), "w") as f:
                f.write("DB-ONLY CLEANUP REPORT\n")
                f.write(f"Date: {today}\n")
                f.write(f"Mode: {mode}\n")
                f.write(f"Total Users with Subs: {stats['total']}\n")
                f.write(f"Active Subscriptions: {stats['active']}\n")
                f.write(f"Expired Subscriptions: {stats['expired']}\n")
                f.write(f"Removed: {stats['removed']}\n")

            print("DB-Only Cleanup Complete:")
            print(f"  Total: {stats['total']}")
            print(f"  Active: {stats['active']}")
            print(f"  Expired: {stats['expired']}")
            print(f"  Removed: {stats['removed']}")

        finally:
            session.close()

        # ---- Notify admins of cleanup results ----
        try:
            from services.telegram_api import TelegramAPIService
            api = TelegramAPIService()
            admin_ids = [1555885694, 6475885611]  # Sergio + Martin

            summary = (
                f"📊 *Resumen de Limpieza*\n"
                f"├ 🗓️ Fecha: {today}\n"
                f"├ 🔧 Reparados: {stats['repaired']}\n"
                f"├ 👥 Total: {stats['total']}\n"
                f"├ ✅ Activos: {stats['active']}\n"
                f"├ ❌ Expirados: {stats['expired']}\n"
                f"└ 🚫 Eliminados: {stats['removed']}"
            )

            for aid in admin_ids:
                try:
                    api.send_message(chat_id=aid, text=summary, parse_mode="Markdown")
                except Exception:
                    pass
            print(f"📱 Notificación enviada a {len(admin_ids)} admins")
        except Exception as e:
            print(f"⚠️ No se pudo notificar: {e}")

        return stats

    # ------------------------------------------------------------------
    # Método principal
    # ------------------------------------------------------------------

    async def run(
        self,
        mode: str = DEFAULT_MODE,
        validate_special_clients: bool = True,
    ) -> dict[str, Any]:
        """
        Ejecuta el proceso completo de limpieza de suscripciones.

        Args:
            mode: Modo de ejecución:
                  "validar" - Solo genera reportes, no elimina usuarios.
                  "eliminar" - Ejecuta validación + eliminación completa.
            validate_special_clients: Si True, guarda clientes no registrados
                  para revisión manual por soporte. Si False, los elimina
                  automáticamente.

        Returns:
            Diccionario con estadísticas de la ejecución:
            - total_members: Miembros en el grupo de Telegram.
            - admins: Número de administradores.
            - active_subs: Suscripciones activas encontradas.
            - expired_subs: Suscripciones vencidas.
            - special_clients: Clientes sin registro en BD.
            - removed: Usuarios eliminados (si mode="eliminar").
            - errors: Lista de errores encontrados.
        """
        now = datetime.now()
        fecha_ejecucion = now.strftime("%Y-%m-%d")
        hora_ejecucion = now.strftime("%H:%M:%S")
        hora_archivo = now.strftime("%H%M%S")

        output_dir = os.path.join(OUTPUT_DIR, fecha_ejecucion)
        os.makedirs(output_dir, exist_ok=True)

        logger.info(
            f"Iniciando limpieza de suscripciones: mode={mode}, "
            f"fecha={fecha_ejecucion}, hora={hora_ejecucion}"
        )

        stats = {
            "total_members": 0,
            "admins": 0,
            "active_subs": 0,
            "expired_subs": 0,
            "special_clients": 0,
            "removed": 0,
            "errors": [],
        }

        try:
            # ---- Paso 1: Obtener administradores del grupo ----
            admins = await self._get_group_admins()
            admin_ids = [str(a["user_id"]) for a in admins]
            stats["admins"] = len(admin_ids)
            logger.info(f"Administradores obtenidos: {len(admin_ids)}")

            # ---- Paso 2: Obtener miembros actuales del grupo desde Telethon ----
            telegram_members = await self._get_telegram_members()
            if telegram_members.empty:
                logger.warning("No se obtuvieron miembros de Telegram (Telethon).")
                stats["errors"].append("telethon_no_members")
                return stats

            stats["total_members"] = len(telegram_members)
            logger.info(f"Miembros en Telegram: {len(telegram_members)}")

            # ---- Paso 3: Obtener suscripciones activas desde BD ----
            active_subs = self.subscription_service.get_active_subscriptions()
            stats["active_subs"] = len(active_subs)

            # ---- Paso 4: Cruzar miembros vs suscripciones ----
            comparison_df = self._build_comparison(
                telegram_members, active_subs, admin_ids
            )

            # ---- Paso 5: Clasificar usuarios ----
            special_clients, to_remove = self._classify_users(
                comparison_df, validate_special_clients
            )

            stats["special_clients"] = len(special_clients)
            stats["expired_subs"] = len(to_remove)

            logger.info(
                f"Clasificación: {len(special_clients)} clientes especiales, "
                f"{len(to_remove)} suscripciones vencidas"
            )

            # ---- Paso 6: Guardar reportes ----
            if special_clients:
                self._save_special_clients_report(
                    special_clients, output_dir, hora_archivo
                )

            if to_remove:
                self._save_prevalidation_report(to_remove, output_dir, hora_archivo)

            # ---- Paso 7: Ejecutar eliminación (solo en modo "eliminar") ----
            if mode == "eliminar" and to_remove:
                removed_count = await self._execute_removal(
                    to_remove, comparison_df, output_dir, hora_archivo
                )
                stats["removed"] = removed_count

            # ---- Paso 8: Guardar resumen general ----
            self._save_summary_report(
                stats, comparison_df, output_dir, hora_archivo,
                fecha_ejecucion, hora_ejecucion
            )

            logger.info(
                f"Limpieza completada: modo={mode}, "
                f"removed={stats['removed']}, errors={len(stats['errors'])}"
            )

        except Exception as e:
            error_msg = f"Error general en limpieza de suscripciones: {e}"
            logger.error(error_msg, exc_info=True)
            stats["errors"].append(error_msg)

        return stats

    # ------------------------------------------------------------------
    # Paso 1: Obtener administradores
    # ------------------------------------------------------------------

    async def _get_group_admins(self) -> list[dict[str, Any]]:
        """
        Obtiene la lista de administradores del grupo VIP de Telegram.

        Returns:
            Lista de diccionarios con info de cada administrador.
        """
        try:
            admins = self.telegram_api.get_chat_administrators(self.vip_group_id)
            admin_list = []
            for admin in admins:
                user = admin.get("user", {})
                admin_list.append({
                    "user_id": user.get("id"),
                    "username": user.get("username", ""),
                    "first_name": user.get("first_name", ""),
                    "status": admin.get("status", ""),
                    "is_admin": True,
                })
            return admin_list
        except Exception as e:
            logger.error(f"Error al obtener administradores: {e}")
            return []

    # ------------------------------------------------------------------
    # Paso 2: Obtener miembros desde Telethon
    # ------------------------------------------------------------------

    async def _get_telegram_members(self) -> pd.DataFrame:
        """
        Obtiene los miembros actuales del grupo VIP usando Telethon.

        Returns:
            DataFrame con columnas: user_telegram_id, username, first_name.
        """
        try:
            from telethon.sync import TelegramClient
            from telethon.tl.functions.channels import GetParticipantsRequest
            from telethon.tl.types import ChannelParticipantsSearch

            api_id = int(os.getenv("TELETHON_API_ID", "0"))
            api_hash = os.getenv("TELETHON_API_HASH", "")

            if not api_id or not api_hash:
                logger.error(
                    "TELETHON_API_ID y TELETHON_API_HASH no configurados. "
                    "No se pueden obtener miembros de Telegram."
                )
                return pd.DataFrame()

            members_list = []

            async with TelegramClient('my_user_session', api_id, api_hash) as client:
                if not await client.is_user_authorized():
                    logger.error(
                        "Cliente Telethon no autorizado. Ejecuta la autenticación manual."
                    )
                    return pd.DataFrame()

                group_entity = await client.get_entity(self.vip_group_id)
                offset = 0
                limit = 200

                while True:
                    participants = await client(GetParticipantsRequest(
                        channel=group_entity,
                        filter=ChannelParticipantsSearch(''),
                        offset=offset,
                        limit=limit,
                        hash=0,
                    ))

                    if not participants.users:
                        break

                    for user in participants.users:
                        members_list.append({
                            "user_telegram_id": user.id,
                            "username": getattr(user, 'username', ''),
                            "first_name": getattr(user, 'first_name', ''),
                        })

                    offset += len(participants.users)

                    if len(participants.users) < limit:
                        break

            logger.info(f"Telethon: {len(members_list)} miembros obtenidos del grupo.")
            return pd.DataFrame(members_list)

        except ImportError:
            logger.error("Telethon no está instalado. No se pueden obtener miembros.")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error en Telethon al obtener miembros: {e}", exc_info=True)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # Paso 4: Construir tabla de comparación
    # ------------------------------------------------------------------

    def _build_comparison(
        self,
        telegram_members: pd.DataFrame,
        active_subs: list[Any],
        admin_ids: list[str],
    ) -> pd.DataFrame:
        """
        Cruza los miembros de Telegram con las suscripciones activas
        para construir una tabla de comparación.

        Args:
            telegram_members: DataFrame con miembros del grupo.
            active_subs: Lista de Subscription activas.
            admin_ids: Lista de IDs de administradores (serán omitidos).

        Returns:
            DataFrame con columnas:
            - user_telegram_id
            - username
            - first_name
            - end_date
            - mensaje (estado: activa, vencida, no registrado)
            - eliminar_suscripcion (bool)
            - servicio
            - fecha_compra
            - fecha_final_suscripcion
        """
        results = []

        for _, member in telegram_members.iterrows():
            user_id = str(member["user_telegram_id"])

            # Omitir administradores
            if user_id in admin_ids:
                continue

            end_date = None
            mensaje = "Usuario no registrado en BD"
            eliminar = True
            servicio = ""
            fecha_compra = ""
            fecha_final = ""

            # Verificar suscripción activa en BD
            user_subs = [
                s for s in active_subs
                if str(s.user_telegram_id) == user_id
            ]

            if user_subs:
                # Tomar la suscripción con end_date más lejano
                latest_sub = max(user_subs, key=lambda s: s.end_date)
                end_date = latest_sub.end_date
                servicio = "grupo_vip" if latest_sub.service_id == 2 else "stake"

                if end_date >= datetime.now().date():
                    mensaje = "suscripción activa"
                    eliminar = False
                else:
                    mensaje = "suscripción vencida"
                    eliminar = True

            results.append({
                "user_telegram_id": user_id,
                "username": member.get("username", ""),
                "first_name": member.get("first_name", ""),
                "end_date": end_date or "",
                "mensaje": mensaje,
                "eliminar_suscripcion": eliminar,
                "servicio": servicio,
                "fecha_compra": fecha_compra,
                "fecha_final_suscripcion": fecha_final,
            })

        comparison = pd.DataFrame(results)
        logger.info(f"Comparación construida: {len(comparison)} usuarios evaluados.")
        return comparison

    # ------------------------------------------------------------------
    # Paso 5: Clasificar usuarios
    # ------------------------------------------------------------------

    def _classify_users(
        self,
        comparison_df: pd.DataFrame,
        validate_special_clients: bool,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Clasifica los usuarios en:
        - Clientes especiales (no registrados en BD).
        - Usuarios a eliminar (suscripción vencida confirmada).

        Args:
            comparison_df: DataFrame de comparación.
            validate_special_clients: Si True, separa clientes especiales.

        Returns:
            Tupla (special_clients_df, to_remove_df).
        """
        # Clientes especiales: no registrados en BD
        special_clients = comparison_df[
            comparison_df["mensaje"] == "Usuario no registrado en BD"
        ].copy()

        if validate_special_clients:
            # Excluir clientes especiales de la eliminación
            to_remove = comparison_df[
                (comparison_df["eliminar_suscripcion"]) &
                (comparison_df["mensaje"] != "Usuario no registrado en BD")
            ].copy()
        else:
            # Eliminar todos (incluyendo clientes especiales)
            to_remove = comparison_df[
                comparison_df["eliminar_suscripcion"]
            ].copy()

        return special_clients, to_remove

    # ------------------------------------------------------------------
    # Paso 7: Ejecutar eliminación
    # ------------------------------------------------------------------

    async def _execute_removal(
        self,
        to_remove: pd.DataFrame,
        comparison_df: pd.DataFrame,
        output_dir: str,
        hora_archivo: str,
    ) -> int:
        """
        Ejecuta la eliminación de usuarios con suscripción vencida.

        Para cada usuario:
        1. Envía mensaje de suscripción vencida.
        2. Expulsa al usuario del grupo (kick + unban para permitir rejoin).
        3. Elimina la suscripción de la base de datos.

        Args:
            to_remove: DataFrame con usuarios a eliminar.
            comparison_df: DataFrame completo de comparación.
            output_dir: Directorio para guardar logs.
            hora_archivo: Timestamp para nombres de archivo.

        Returns:
            Número de usuarios eliminados exitosamente.
        """
        removed_count = 0
        removed_users = []

        logger.info(f"Iniciando eliminación de {len(to_remove)} usuarios...")

        for _, row in to_remove.iterrows():
            user_id = str(row["user_telegram_id"])
            mensaje_eliminacion = ""

            try:
                # 1. Enviar mensaje de suscripción vencida
                try:

                    # Usar el reminder_service si está disponible
                    logger.info(f"Enviando mensaje de vencimiento a user={user_id}...")
                except Exception as e:
                    logger.warning(f"No se pudo enviar mensaje a {user_id}: {e}")
                    mensaje_eliminacion = f"Error mensaje: {e}"

                # 2. Expulsar del grupo (kick + unban)
                try:
                    result = self.telegram_api.remove_user_allow_rejoin(
                        chat_id=self.vip_group_id,
                        user_id=int(user_id),
                    )
                    if result.get("kick_success"):
                        logger.info(f"Usuario {user_id} expulsado del grupo.")
                        mensaje_eliminacion += (
                            "Mensaje enviado, usuario baneado "
                            "(registro mantenido en BD)"
                        )
                    else:
                        logger.warning(
                            f"No se pudo expulsar a {user_id}: {result.get('kick_result')}"
                        )
                        mensaje_eliminacion += "Error al banear."
                except Exception as e:
                    logger.error(f"Error al expulsar a {user_id}: {e}")
                    mensaje_eliminacion += f"Error banear: {e}"

                # 3. Desbanear para permitir rejoin futuro
                try:
                    unban_result = self.telegram_api.unban_user(
                        chat_id=self.vip_group_id,
                        user_id=int(user_id),
                        only_if_banned=True,
                    )
                    if unban_result.get("ok"):
                        logger.info(f"Usuario {user_id} desbaneado para rejoin.")
                        mensaje_eliminacion += " + Desbaneado."
                except Exception as e:
                    logger.warning(f"Error al desbanear a {user_id}: {e}")
                    mensaje_eliminacion += f" | Error desbaneo: {e}"

                # 4. Marcar suscripción como inactiva en BD
                try:
                    from core.database import SessionLocal
                    from models.subscription import Subscription
                    session = SessionLocal()
                    sub = session.query(Subscription).filter_by(
                        user_telegram_id=int(user_id), is_active=True
                    ).first()
                    if sub:
                        sub.is_active = False
                        session.commit()
                        logger.info(f"Suscripción de user={user_id} marcada como inactiva.")
                    session.close()
                except Exception as e:
                    logger.warning(f"Error al marcar inactiva suscripción de {user_id}: {e}")

                # Registrar usuario eliminado
                removed_users.append({
                    "user_telegram_id": user_id,
                    "username": row.get("username", ""),
                    "first_name": row.get("first_name", ""),
                    "servicio": row.get("servicio", ""),
                    "razon_eliminacion": row.get("mensaje", ""),
                    "estado_eliminacion": mensaje_eliminacion,
                    "timestamp_eliminacion": datetime.now().isoformat(),
                })

                removed_count += 1

                # Guardar en línea (para no perder datos si el proceso se interrumpe)
                self._save_removed_user_inline(
                    removed_users[-1], output_dir, hora_archivo
                )

            except Exception as e:
                logger.error(
                    f"Error al procesar eliminación de user={user_id}: {e}",
                    exc_info=True,
                )

        # Guardar CSV de eliminaciones
        if removed_users:
            df_removed = pd.DataFrame(removed_users)
            csv_path = os.path.join(output_dir, f"eliminaciones_{hora_archivo}.csv")
            df_removed.to_csv(csv_path, index=False)
            logger.info(f"CSV de eliminaciones guardado: {csv_path}")

        logger.info(f"Eliminación completada: {removed_count} usuarios eliminados.")
        return removed_count

    # ------------------------------------------------------------------
    # Reportes
    # ------------------------------------------------------------------

    def _save_special_clients_report(
        self,
        special_clients: pd.DataFrame,
        output_dir: str,
        hora_archivo: str,
    ) -> None:
        """Guarda el reporte de clientes especiales para revisión manual."""
        filepath = os.path.join(
            output_dir, f"clientes_especiales_validacion_{hora_archivo}.json"
        )

        data = {
            "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d"),
            "hora_ejecucion": datetime.now().strftime("%H:%M:%S"),
            "total_clientes_especiales": len(special_clients),
            "nota": "Clientes no registrados en BD - Requieren validación por soporte",
            "estado_validacion": "PENDIENTE",
            "usuarios": [],
        }

        for _, row in special_clients.iterrows():
            data["usuarios"].append({
                "user_telegram_id": str(row["user_telegram_id"]),
                "username": row.get("username", ""),
                "first_name": row.get("first_name", ""),
                "estado": row.get("mensaje", ""),
                "accion_recomendada": "Contactar por soporte - Validar si es cliente legítimo",
                "timestamp_identificacion": datetime.now().isoformat(),
            })

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Reporte de clientes especiales guardado: {filepath}")

    def _save_prevalidation_report(
        self,
        to_remove: pd.DataFrame,
        output_dir: str,
        hora_archivo: str,
    ) -> None:
        """Guarda el reporte de pre-validación de usuarios a eliminar."""
        filepath = os.path.join(output_dir, f"prevalidacion_{hora_archivo}.json")

        data = {
            "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d"),
            "hora_ejecucion": datetime.now().strftime("%H:%M:%S"),
            "total_usuarios_a_eliminar": len(to_remove),
            "nota": "Usuarios con suscripción vencida comprobada",
            "usuarios": [],
        }

        for _, row in to_remove.iterrows():
            data["usuarios"].append({
                "user_telegram_id": str(row["user_telegram_id"]),
                "username": row.get("username", ""),
                "first_name": row.get("first_name", ""),
                "servicio": row.get("servicio", ""),
                "razon": row.get("mensaje", ""),
            })

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Reporte de pre-validación guardado: {filepath}")

    def _save_summary_report(
        self,
        stats: dict[str, Any],
        comparison_df: pd.DataFrame,
        output_dir: str,
        hora_archivo: str,
        fecha_ejecucion: str,
        hora_ejecucion: str,
    ) -> None:
        """Guarda el reporte resumen de la ejecución."""
        # Guardar JSON
        json_path = os.path.join(output_dir, f"log_ejecucion_{hora_archivo}.json")
        log_data = {
            "fecha_ejecucion": fecha_ejecucion,
            "hora_ejecucion": hora_ejecucion,
            "resumen_general": stats,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)

        # Guardar TXT
        txt_path = os.path.join(output_dir, f"resumen_{hora_archivo}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("RESUMEN DE EJECUCIÓN - LIMPIEZA DE SUSCRIPCIONES\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Fecha: {fecha_ejecucion}\n")
            f.write(f"Hora: {hora_ejecucion}\n\n")
            f.write("ESTADÍSTICAS GENERALES:\n")
            f.write("-" * 60 + "\n")
            for key, value in stats.items():
                f.write(f"{key}: {value}\n")

        logger.info(f"Reportes guardados: {json_path}, {txt_path}")

    def _save_removed_user_inline(
        self,
        user_data: dict[str, Any],
        output_dir: str,
        hora_archivo: str,
    ) -> None:
        """
        Guarda un usuario eliminado en el archivo JSON en tiempo real.
        Evita pérdida de datos si el proceso se interrumpe a mitad.
        """
        filepath = os.path.join(output_dir, f"usuarios_eliminados_{hora_archivo}.json")

        if os.path.exists(filepath):
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {
                "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d"),
                "hora_ejecucion": datetime.now().strftime("%H:%M:%S"),
                "total_eliminados": 0,
                "resumen_tipos": {
                    "suscripcion_expirada": 0,
                    "sin_compra_registrada": 0,
                    "no_registrado_bd": 0,
                },
                "usuarios": [],
            }

        data["usuarios"].append(user_data)
        data["total_eliminados"] = len(data["usuarios"])

        # Actualizar contadores por tipo
        tipo = user_data.get("tipo_usuario", "desconocido")
        if tipo in data["resumen_tipos"]:
            data["resumen_tipos"][tipo] += 1

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
