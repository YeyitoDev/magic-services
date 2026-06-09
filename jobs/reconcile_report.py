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
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from utils.logger import setup_logger

logger = setup_logger(
    "jobs.reconcile_report",
    log_format="text",
    console_output=True,
)

ADMIN_IDS = [1555885694, 6475885611]  # Sergio + Martin


@dataclass(frozen=True)
class _UserDbInfo:
    """Datos enriquecidos de un usuario desde la BD."""

    end_date: date | None = None
    last_purchase_date: datetime | None = None
    last_purchase_price: float | None = None
    last_purchase_channel: str = ""
    total_purchases: int = 0


def _fetch_db_snapshot() -> dict[int, _UserDbInfo]:
    """Obtiene snapshot de suscripciones + compras por usuario."""
    from core.database import SessionLocal
    from models.purchase import Purchase
    from models.subscription import Subscription

    session = SessionLocal()
    try:
        subs = session.query(Subscription.user_telegram_id, Subscription.end_date).all()
        purchases = (
            session.query(
                Purchase.user_telegram_id,
                Purchase.purchase_date,
                Purchase.price,
                Purchase.from_channel,
            )
            .order_by(Purchase.purchase_date.desc())
            .all()
        )
    finally:
        session.close()

    info: dict[int, _UserDbInfo] = {}
    for user_id, end_date in subs:
        uid = int(user_id)
        info[uid] = _UserDbInfo(end_date=end_date)

    # Enriquecer con compras
    purchase_counts: dict[int, int] = {}
    for user_id, pdate, price, channel in purchases:
        uid = int(user_id)
        purchase_counts[uid] = purchase_counts.get(uid, 0) + 1
        existing = info.get(uid)
        if existing is None or existing.last_purchase_date is None:
            info[uid] = _UserDbInfo(
                end_date=existing.end_date if existing else None,
                last_purchase_date=pdate,
                last_purchase_price=price,
                last_purchase_channel=channel or "",
                total_purchases=purchase_counts[uid],
            )
        else:
            # Solo actualizar contador si ya tenemos la última compra
            info[uid] = _UserDbInfo(
                end_date=existing.end_date,
                last_purchase_date=existing.last_purchase_date,
                last_purchase_price=existing.last_purchase_price,
                last_purchase_channel=existing.last_purchase_channel,
                total_purchases=purchase_counts[uid],
            )

    return info


def _build_excel(
    output_path: str,
    active_in_group: list[dict],
    expired_in_group: list[dict],
    unregistered_in_group: list[dict],
    active_not_in_group: list[int],
    expired_not_in_group: list[int],
    db_info: dict[int, _UserDbInfo],
) -> None:
    """Genera un archivo Excel con hojas para cada categoría."""

    def _row(user_id: int, username: str = "", first_name: str = "") -> dict[str, Any]:
        info = db_info.get(user_id, _UserDbInfo())
        return {
            "user_id": user_id,
            "username": f"@{username}" if username else "",
            "first_name": first_name,
            "sub_end_date": info.end_date.isoformat() if info.end_date else "",
            "last_purchase_date": (
                info.last_purchase_date.isoformat() if info.last_purchase_date else ""
            ),
            "last_purchase_price": info.last_purchase_price or "",
            "last_purchase_channel": info.last_purchase_channel,
            "total_purchases": info.total_purchases,
            "estado": "",
            "notas_revision": "",
        }

    # ---- Hoja 1: Sin registro en BD (los 56 revisar) ----
    df_unreg = pd.DataFrame(
        [_row(m["user_id"], m.get("username", ""), m.get("first_name", "")) for m in unregistered_in_group]
    )
    df_unreg["estado"] = "SIN_REGISTRO"
    df_unreg["notas_revision"] = "Revisar boleta de compra manualmente"

    # ---- Hoja 2: Vencidos en grupo (kick candidatos) ----
    df_exp = pd.DataFrame(
        [
            {
                **_row(m["user_id"], m.get("username", ""), m.get("first_name", "")),
                "estado": "VENCIDO",
                "notas_revision": "Expulsar del grupo",
            }
            for m in expired_in_group
        ]
    )

    # ---- Hoja 3: Activos fuera del grupo (re-invitar) ----
    df_active_out = pd.DataFrame(
        [
            {
                **_row(uid),
                "estado": "ACTIVO_FUERA_GRUPO",
                "notas_revision": "Re-invitar al grupo",
            }
            for uid in active_not_in_group
        ]
    )

    # ---- Hoja 4: Vencidos fuera del grupo (BD obsoleta) ----
    df_expired_out = pd.DataFrame(
        [
            {
                **_row(uid),
                "estado": "BD_OBSOLETA",
                "notas_revision": "Borrar fila de BD",
            }
            for uid in expired_not_in_group
        ]
    )

    # ---- Hoja 5: Activos en grupo (OK) ----
    df_active = pd.DataFrame(
        [_row(m["user_id"], m.get("username", ""), m.get("first_name", "")) for m in active_in_group]
    )
    df_active["estado"] = "OK"
    df_active["notas_revision"] = ""

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_unreg.to_excel(writer, sheet_name="Sin registro BD", index=False)
        df_exp.to_excel(writer, sheet_name="Vencidos en grupo", index=False)
        df_active_out.to_excel(writer, sheet_name="Activos fuera grupo", index=False)
        df_expired_out.to_excel(writer, sheet_name="Vencidos fuera grupo", index=False)
        df_active.to_excel(writer, sheet_name="Activos OK", index=False)

    logger.info(f"Excel guardado: {output_path}")


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

    # ---- Carga BD ----
    logger.info("Cargando snapshot de BD (subs + compras)...")
    db_info = _fetch_db_snapshot()
    latest = {uid: info.end_date for uid, info in db_info.items() if info.end_date}
    active_db = {uid for uid, ed in latest.items() if ed >= today}
    expired_db = {uid for uid, ed in latest.items() if ed < today}

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
    members_real: list[dict] = []
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

    # ---- Guardar reportes ----
    output_dir = os.path.join("output", today.strftime("%Y-%m-%d"))
    os.makedirs(output_dir, exist_ok=True)
    hora = datetime.now().strftime("%H%M%S")

    # JSON legacy
    report = {
        **stats,
        "detalle": {
            "vencidos_en_grupo": expired_in_group[:500],
            "no_registrados": unregistered_in_group[:500],
            "activos_fuera_grupo": active_not_in_group[:500],
            "vencidos_fuera_grupo": expired_not_in_group[:500],
        },
    }
    json_path = os.path.join(output_dir, f"reconciliacion_{hora}.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"JSON guardado: {json_path}")

    # Excel detallado para revisión manual
    excel_path = os.path.join(output_dir, f"reconciliacion_{hora}.xlsx")
    _build_excel(
        excel_path,
        active_in_group,
        expired_in_group,
        unregistered_in_group,
        active_not_in_group,
        expired_not_in_group,
        db_info,
    )

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
