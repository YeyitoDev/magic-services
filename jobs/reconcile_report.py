"""
Reconcile Report Job - Magic Chatbot v2
========================================
Reporte de reconciliación (SOLO LECTURA) entre los miembros reales del grupo
VIP de Telegram y las suscripciones en la base de datos.

A diferencia del cleanup DB-only (que solo mira `end_date` en la BD y nunca ve
quién está realmente en el grupo), este job obtiene la lista real de miembros
vía Telethon y cruza ambas fuentes para explicar el desajuste de números:

  Lado grupo (miembros reales, excluyendo admins y bots):
    - activos      : miembro con suscripción vigente en BD
    - vencidos     : miembro con suscripción vencida en BD  → candidato a kick
    - no_registrados: miembro sin ningún registro en BD     → revisión manual

  Lado BD:
    - activos_fuera_grupo : suscripción vigente pero el usuario no está en el grupo
    - vencidos_fuera_grupo: filas vencidas de usuarios que ya salieron (BD obsoleta)

NO realiza ningún kick, unban ni borrado: únicamente reporta y guarda artefactos.

Uso:
    python -m jobs.reconcile_report
"""

import asyncio
import json
import os
import sys
from datetime import date, datetime

from utils.logger import setup_logger

logger = setup_logger(
    "jobs.reconcile_report",
    log_format="text",
    console_output=True,
)

ADMIN_IDS = [1555885694, 6475885611]  # Sergio + Martin


def _latest_end_dates() -> dict[int, date]:
    """Devuelve {user_telegram_id: end_date más reciente} de todas las subs."""
    from core.database import SessionLocal
    from models.subscription import Subscription

    session = SessionLocal()
    try:
        rows = session.query(
            Subscription.user_telegram_id, Subscription.end_date
        ).all()
    finally:
        session.close()

    latest: dict[int, date] = {}
    for user_id, end_date in rows:
        uid = int(user_id)
        if uid not in latest or end_date > latest[uid]:
            latest[uid] = end_date
    return latest


async def run_reconcile_report() -> dict:
    """Genera el reporte de reconciliación grupo ↔ BD (solo lectura)."""
    from jobs.subscription_cleanup import SubscriptionCleanupJob
    from services.telegram_api import TelegramAPIService

    today = date.today()
    job = SubscriptionCleanupJob(
        telegram_api=TelegramAPIService(),
        subscription_service=None,
        user_service=None,
    )

    # ---- Lado Telegram ----
    admins = await job._get_group_admins()
    admin_ids = {int(a["user_id"]) for a in admins if a.get("user_id")}
    admin_ids |= set(ADMIN_IDS)

    members_df = await job._get_telegram_members()
    if members_df.empty:
        raise RuntimeError(
            "No se obtuvieron miembros vía Telethon. Revisa TELETHON_API_ID/"
            "TELETHON_API_HASH/TELETHON_SESSION y que la sesión esté autorizada."
        )

    member_ids: set[int] = set()
    bots = 0
    members_real: list[dict] = []  # miembros humanos no-admin
    for _, m in members_df.iterrows():
        uid = int(m["user_telegram_id"])
        member_ids.add(uid)
        if bool(m.get("is_bot", False)):
            bots += 1
            continue
        if uid in admin_ids:
            continue
        members_real.append(
            {
                "user_id": uid,
                "username": m.get("username", ""),
                "first_name": m.get("first_name", ""),
            }
        )

    # ---- Lado BD ----
    latest = _latest_end_dates()
    active_db = {uid for uid, ed in latest.items() if ed >= today}
    expired_db = {uid for uid, ed in latest.items() if ed < today}

    # ---- Cruce: lado grupo ----
    active_in_group, expired_in_group, unregistered_in_group = [], [], []
    for m in members_real:
        uid = m["user_id"]
        if uid in active_db:
            active_in_group.append(m)
        elif uid in expired_db:
            expired_in_group.append({**m, "end_date": str(latest[uid])})
        else:
            unregistered_in_group.append(m)

    # ---- Cruce: lado BD ----
    active_not_in_group = sorted(active_db - member_ids)
    expired_not_in_group = sorted(expired_db - member_ids)

    stats = {
        "fecha": str(today),
        "grupo": {
            "total_miembros": len(member_ids),
            "admins": len(admin_ids & member_ids),
            "bots": bots,
            "activos": len(active_in_group),
            "vencidos_en_grupo": len(expired_in_group),
            "no_registrados": len(unregistered_in_group),
        },
        "bd": {
            "usuarios_con_sub": len(latest),
            "activos": len(active_db),
            "vencidos": len(expired_db),
            "activos_fuera_grupo": len(active_not_in_group),
            "vencidos_fuera_grupo": len(expired_not_in_group),
        },
    }

    logger.info(f"Reconciliación: {json.dumps(stats, ensure_ascii=False)}")

    # ---- Guardar reporte ----
    output_dir = os.path.join("output", today.strftime("%Y-%m-%d"))
    os.makedirs(output_dir, exist_ok=True)
    hora = datetime.now().strftime("%H%M%S")
    report = {
        **stats,
        "detalle": {
            "vencidos_en_grupo": expired_in_group[:500],
            "no_registrados": unregistered_in_group[:500],
            "activos_fuera_grupo": active_not_in_group[:500],
            "vencidos_fuera_grupo": expired_not_in_group[:500],
        },
    }
    report_path = os.path.join(output_dir, f"reconciliacion_{hora}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Reporte guardado: {report_path}")

    # ---- Resumen a administradores ----
    g, b = stats["grupo"], stats["bd"]
    summary = (
        f"🔎 *Reconciliación Grupo ↔ BD*\n"
        f"├ 🗓️ Fecha: {today}\n"
        f"├ 👥 Miembros grupo: {g['total_miembros']} "
        f"(admins {g['admins']}, bots {g['bots']})\n"
        f"├ ✅ En grupo con sub activa: {g['activos']}\n"
        f"├ ⏰ En grupo con sub vencida: {g['vencidos_en_grupo']}  → expulsar\n"
        f"├ ❓ En grupo sin registro: {g['no_registrados']}  → revisar\n"
        f"├ 🗄️ BD activos: {b['activos']} / vencidos: {b['vencidos']}\n"
        f"├ 📤 Activos fuera del grupo: {b['activos_fuera_grupo']}\n"
        f"└ 🧹 Vencidos fuera del grupo (BD obsoleta): {b['vencidos_fuera_grupo']}"
    )
    api = TelegramAPIService()
    for aid in ADMIN_IDS:
        try:
            api.send_message(chat_id=aid, text=summary, parse_mode="Markdown")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"No se pudo avisar al admin {aid}: {e}")

    return stats


def main() -> int:
    try:
        asyncio.run(run_reconcile_report())
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error en el reporte de reconciliación: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
