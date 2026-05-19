"""
Callback Handlers - Magic Chatbot v2
======================================
Handlers para los callbacks de botones inline de Telegram.

Procesa todas las interacciones del usuario con los teclados inline:
- Selección de servicio (Stake, Grupo VIP).
- Validación de pagos (validar, rechazar, monto incorrecto).
- Navegación del calendario.
- Preguntas frecuentes.
- Confirmación de compra.
- Navegación de menú (regresar, etc.).

Principios:
- Thin Handlers: solo orquestan; la lógica de negocio está en los servicios.
- Dependency Injection: reciben servicios por constructor.
- Single Responsibility: cada método maneja un tipo de callback.

Uso:
    from handlers.callbacks import CallbackHandlers

    cb = CallbackHandlers(user_service, subscription_service, payment_service)
    app.add_handler(CallbackQueryHandler(cb.handle_button))
"""

import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """
    Handlers para todos los callbacks de botones inline del bot.

    Centraliza la lógica de routing de callbacks y la delegación
    a los servicios de dominio correspondientes.

    Attributes:
        user_service: Servicio de gestión de usuarios.
        subscription_service: Servicio de suscripciones/compras.
        payment_service: Servicio de validación de pagos.
        vision_service: Servicio de Google Cloud Vision.
        sheets_service: Servicio de Google Sheets.
        promotion_service: Servicio de promociones.
        settings: Configuración centralizada.
    """

    def __init__(
        self,
        user_service,
        subscription_service,
        payment_service,
        vision_service=None,
        sheets_service=None,
        promotion_service=None,
        settings=None,
    ):
        """
        Inicializa los handlers de callback con los servicios necesarios.

        Args:
            user_service: UserService.
            subscription_service: SubscriptionService.
            payment_service: PaymentService.
            vision_service: GoogleVisionService (opcional).
            sheets_service: GoogleSheetsService (opcional).
            promotion_service: PromotionService (opcional).
            settings: Configuración centralizada (opcional).
        """
        self.user_service = user_service
        self.subscription_service = subscription_service
        self.payment_service = payment_service
        self.vision_service = vision_service
        self.sheets_service = sheets_service
        self.promotion_service = promotion_service

        if settings is None:
            from config.settings import settings as s
            self.settings = s
        else:
            self.settings = settings

    async def _safe_edit_message(self, query, text: str, reply_markup=None):
        """Edits a message safely, handling both text and photo messages."""
        try:
            if query.message.photo:
                await query.edit_message_caption(caption=text, reply_markup=reply_markup)
            else:
                await query.edit_message_text(text=text, reply_markup=reply_markup)
        except Exception as e:
            error_msg = str(e)
            if "not modified" in error_msg.lower() or "message is not modified" in error_msg.lower():
                logger.debug(f"Mensaje no modificado (ignorado): {e}")
                return  # Not an error, content is the same
            logger.warning(f"No se pudo editar mensaje: {e}")

    # ------------------------------------------------------------------
    # Router principal de callbacks
    # ------------------------------------------------------------------

    async def handle_button(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Router principal de callbacks. Despacha según el prefijo del callback_data.

        Formato de callback_data: "context_button:action:param1:param2:..."

        Args:
            update: Update de Telegram.
            context: Contexto de la aplicación.
        """
        query = update.callback_query
        await query.answer()

        data = query.data.split(":")
        if not data:
            logger.warning("Callback sin datos recibido.")
            return

        context_button = data[0]
        user_id = int(query.from_user.id)
        nombre_usuario = query.from_user.first_name or "Usuario"

        logger.debug(
            f"Callback recibido: button={context_button}, user={user_id}, "
            f"data={data}"
        )

        # Registrar interacción del usuario
        await self._register_user_interaction(user_id, nombre_usuario)

        try:
            # --- Menú principal / Información de servicio ---
            if context_button == "informacion_servicio":
                await self._handle_service_info(update, context, data)

            elif context_button == "consulta_tipo_servicio":
                await self._handle_service_selection(update, context, data)

            elif context_button == "preguntas_frecuentes":
                await self._handle_faq(update, context, data)

            elif context_button == "regresar_menu_principal":
                await self._handle_back_to_menu(update, context, data)

            # --- Compra de servicio ---
            elif context_button == "comprar_servicio":
                await self._handle_buy_service(update, context, data)

            # --- Validación de pago ---
            elif context_button == "validar_monto":
                await self._handle_payment_validation(update, context, data)

            elif context_button == "buttom_validar_monto":
                await self._handle_manual_service_confirm(update, context, data)

            # --- Calendario ---
            elif context_button.startswith("cal_"):
                await self._handle_calendar_callback(update, context, data)

            # --- Ignorar ---
            elif context_button == "cal_ignore":
                pass  # Callback ignorado intencionalmente

            else:
                logger.warning(
                    f"Callback no reconocido: {context_button}"
                )
                await query.edit_message_text(
                    text="Opción no reconocida. Usa /start para volver al menú."
                )

        except Exception as e:
            error_msg = str(e)
            if "not modified" in error_msg.lower() or "message is not modified" in error_msg.lower():
                logger.debug(f"Mensaje no modificado: {e}")
                return  # Ignore, content didn't change
            logger.error(f"Error en callback '{context_button}': {e}", exc_info=True)
            await self._safe_edit_message(
                query,
                text="Ocurrió un error procesando tu solicitud. "
                "Intenta de nuevo o contacta a @magic_peru."
            )

    # ------------------------------------------------------------------
    # Información de servicio
    # ------------------------------------------------------------------

    async def _handle_service_info(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """Muestra información detallada de un servicio."""
        query = update.callback_query
        action = data[1] if len(data) > 1 else "general"
        user_id = query.from_user.id

        if action == "stake" or action == "Stake":
            mensaje = (
                "El stake de máxima seguridad consta de una apuesta con una "
                "probabilidad de acierto mayor al 96% en el partido indicado. "
                "Nosotros estamos entrando con S/. 20,000 a esta jugada. "
                "GARANTIZADA DE VICTORIA."
            )
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/stake_maximo.png", "rb"),
                caption=mensaje,
            )

        elif action == "grupo_vip" or action == "Grupo VIP":
            mensaje = (
                "En el grupo VIP recibirás diariamente entre 3 a 4 pronósticos "
                "estadísticos con la probabilidad más alta de ganar. En este grupo "
                "solo realizamos apuestas 100% estadísticas seleccionadas por "
                "nuestros analistas donde también tendrás asesoría directa por "
                "ellos para colocar las jugadas."
            )
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/grupo_vip_1.jpg", "rb"),
            )
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/grupo_vip_2.jpg", "rb"),
                caption=mensaje,
            )

        elif action == "general":
            from utils.keyboards import service_info_keyboard
            await query.edit_message_text(
                text=(
                    "📋 *Nuestros Servicios*\n\n"
                    "🎯 *Grupo VIP*: Pronósticos diarios premium con asesoría directa.\n"
                    "🎲 *Stake*: Apuesta de máxima seguridad con >96% de acierto.\n\n"
                    "Selecciona uno para más información:"
                ),
                parse_mode="Markdown",
                reply_markup=service_info_keyboard("general"),
            )

    # ------------------------------------------------------------------
    # Selección de servicio
    # ------------------------------------------------------------------

    async def _handle_service_selection(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """Procesa la selección de un tipo de servicio por el usuario."""
        query = update.callback_query
        user_id = query.from_user.id
        tipo_servicio = data[1] if len(data) > 1 else None

        if tipo_servicio == "preguntas_frecuentes":
            await self._handle_faq(update, context, data)
            return

        # Send service images FIRST (like original code)
        if tipo_servicio in ("Stake", "stake"):
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/stake_maximo.png", "rb"),
                caption="El stake de máxima seguridad consta de una apuesta con una probabilidad de acierto mayor al 96% en el partido indicado. Nosotros estamos entrando con S/. 20,000 a esta jugada. GARANTIZADA DE VICTORIA."
            )
        elif tipo_servicio in ("Grupo VIP", "grupo_vip"):
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/grupo_vip_1.jpg", "rb"),
            )
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/grupo_vip_2.jpg", "rb"),
                caption="En el grupo VIP recibirás diariamente entre 3 a 4 pronósticos estadísticos con la probabilidad más alta de ganar. En este grupo solo realizamos apuestas 100% estadísticas seleccionadas por nuestros analistas donde también tendrás asesoría directa por ellos para colocar las jugadas."
            )

        # Then show pricing message with dynamic prices
        await self._send_service_pricing(
            update=update,
            context=context,
            user_id=user_id,
            tipo_servicio=tipo_servicio,
        )

        # Guardar la selección del usuario
        service_name = "Grupo VIP" if tipo_servicio in ("Grupo VIP", "grupo_vip") else tipo_servicio
        from core.database import SessionLocal
        from repositories.selected_service_repo import SelectedServiceRepository

        session = SessionLocal()
        try:
            repo = SelectedServiceRepository(session)
            service = self.subscription_service._service_repo.get_by_name(service_name)
            if service:
                repo.upsert(user_telegram_id=user_id, service_id=service.service_id)
                logger.info(f"Usuario {user_id} seleccionó servicio: {service_name}")
        finally:
            session.close()

    async def _send_service_pricing(self, update, context, user_id, tipo_servicio):
        query = update.callback_query
        if tipo_servicio in ("Stake", "stake"):
            mensaje = (
                "🎲 *STAKE DE MÁXIMA SEGURIDAD*\n\n"
                "💰 *Precio: S/ 50.00*\n\n"
                "Los números de cuenta son los siguientes mi hermano 🔮\n\n"
                "Titular: José González Reategui\n"
                "Yape/Plin: 952903700\n"
                "BCP: 194020262033\n"
                "SCOTIA: 1780142814\n\n"
                "Solo envía la captura de tu transferencia por este medio 📲"
            )
        else:
            mensaje = (
                "💎 *GRUPO VIP*\n\n"
                "🔥 *PRECIOS VIP*\n"
                "* 1 Mes = S/. 100\n"
                "* 2 Meses = S/. 150\n"
                "* 3 Meses = S/. 200\n\n"
                "Los números de cuenta son los siguientes mi hermano 🔮\n\n"
                "Titular: José González Reategui\n"
                "Yape/Plin: 952903700\n"
                "BCP: 19402020623033\n"
                "SCOTIA: 1780142814\n\n"
                "Solo envía la captura de tu transferencia por este medio 📲"
            )
        from utils.keyboards import buy_service_keyboard
        await query.edit_message_text(
            text=mensaje, parse_mode="Markdown",
            reply_markup=buy_service_keyboard(tipo_servicio),
        )

    # ------------------------------------------------------------------
    # FAQ
    # ------------------------------------------------------------------

    async def _handle_faq(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """Muestra preguntas frecuentes y respuestas."""
        query = update.callback_query
        action = data[1] if len(data) > 1 else "general"

        faq_respuestas = {
            "grupo_vip": {
                "pregunta": "¿Qué es el Grupo VIP?",
                "respuesta": (
                    "El Grupo VIP es nuestra comunidad exclusiva donde recibes "
                    "diariamente entre 3 a 4 pronósticos estadísticos con la más "
                    "alta probabilidad de acierto. Incluye asesoría directa de "
                    "nuestros analistas para colocar las jugadas."
                ),
                "video": "./videos_promocionales/GRUPO_VIP_EXPLICACION.mp4",
            },
            "stake": {
                "pregunta": "¿Qué es el Stake?",
                "respuesta": (
                    "El Stake de Máxima Seguridad es una apuesta única con más "
                    "del 96% de probabilidad de acierto. Entramos con S/ 20,000 "
                    "a esta jugada. ¡Garantizada!"
                ),
                "video": "./videos_promocionales/STAKE_MAXIMA_SEGURIDAD_EXPLICACION.mp4",
            },
            "como_pagar": {
                "pregunta": "¿Cómo pagar?",
                "respuesta": (
                    "Puedes pagar mediante Yape, Plin o transferencia bancaria:\n"
                    "• Yape/Plin: 952903700\n"
                    "• BCP: 19402020623033\n"
                    "• SCOTIA: 1780142814\n"
                    "Envía la captura de tu transferencia a este chat y será "
                    "validada en minutos."
                ),
            },
            "link": {
                "pregunta": "¿Cómo recibo el link?",
                "respuesta": (
                    "Después de que tu pago sea validado, recibirás automáticamente "
                    "el link de invitación al grupo privado. El link es de un solo "
                    "uso y expira en 24 horas."
                ),
            },
        }

        if action in faq_respuestas:
            info = faq_respuestas[action]
            # Send video explanation if available
            if "video" in info:
                import os
                if os.path.exists(info["video"]):
                    await context.bot.send_video(
                        chat_id=query.from_user.id,
                        video=open(info["video"], "rb"),
                        caption=f"*{info['pregunta']}*\n\n{info['respuesta']}",
                        parse_mode="Markdown",
                    )
            from utils.keyboards import faq_video_keyboard

            await query.edit_message_text(
                text=f"*{info['pregunta']}*\n\n{info['respuesta']}",
                parse_mode="Markdown",
                reply_markup=faq_video_keyboard(action),
            )
        else:
            from utils.keyboards import faq_keyboard
            await query.edit_message_text(
                text="*❓ Preguntas Frecuentes*\n\nSelecciona una categoría:",
                parse_mode="Markdown",
                reply_markup=faq_keyboard(),
            )

    # ------------------------------------------------------------------
    # Volver al menú principal
    # ------------------------------------------------------------------

    async def _handle_back_to_menu(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """Retorna al usuario al menú principal."""
        from utils.keyboards import main_menu_keyboard

        query = update.callback_query
        await query.edit_message_text(
            text=(
                "🔮 *¡BIENVENIDO A MAGIC!* 🔮\n\n"
                "Selecciona una opción mi hermano:\n\n"
                "💎 *Grupo VIP* - Pronósticos exclusivos diarios\n"
                "🎲 *Stake* - Apuesta de máxima seguridad"
            ),
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )

    # ------------------------------------------------------------------
    # Compra de servicio
    # ------------------------------------------------------------------

    async def _handle_buy_service(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """Procesa la confirmación de compra y redirige al envío de captura."""
        query = update.callback_query
        user_id = query.from_user.id
        nombre_usuario = query.from_user.first_name or "Usuario"
        respuesta_compra = data[1] if len(data) > 1 else "no"
        tipo_servicio = data[2] if len(data) > 2 else ""

        image_path = f"./images/trans_{user_id}.jpeg"

        if respuesta_compra == "si":
            if os.path.exists(image_path):
                # Ya envió captura: reenviar al validador
                await self._process_existing_image(
                    update, context, user_id, nombre_usuario, tipo_servicio, image_path
                )
            else:
                # No ha enviado captura: mostrar precios
                await self._send_service_pricing(
                    update, context, user_id, tipo_servicio
                )

                # Guardar selección
                from core.database import SessionLocal
                from repositories.selected_service_repo import SelectedServiceRepository

                session = SessionLocal()
                try:
                    repo = SelectedServiceRepository(session)
                    service_name = "Grupo VIP" if tipo_servicio in ("Grupo VIP", "grupo_vip") else tipo_servicio
                    service = self.subscription_service._service_repo.get_by_name(service_name)
                    if service:
                        repo.upsert(user_telegram_id=user_id, service_id=service.service_id)
                finally:
                    session.close()

        elif respuesta_compra == "no":
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "Seguro la próxima te animas mi gato, te recomiendo seguir jugando "
                    "las apuestas gratis que enviamos por el grupo y te regalo un bono "
                    "de S/ 40 en la mejor casa de apuestas del mundo"
                )
            )
            await context.bot.send_photo(
                chat_id=user_id,
                photo=open("./imagenes_promocionales/betsafe_logo.jpeg", "rb"),
            )
            from utils.keyboards import main_menu_keyboard
            await context.bot.send_message(
                chat_id=user_id,
                text=self.settings.BETSAFE_PROMO_LINK,
                reply_markup=main_menu_keyboard(),
            )

    async def _process_existing_image(
        self, update, context, user_id, nombre_usuario, tipo_servicio, image_path
    ):
        """Procesa una imagen de comprobante ya existente."""

        await context.bot.send_message(
            chat_id=user_id,
            text="<strong>Recibi tu voucher de pago, en un minuto procedere a validar tu pago ✅</strong>",
            parse_mode="html",
        )

        # Extraer texto de la imagen
        texto_extraido = ""
        if self.vision_service:
            texto_extraido = self.vision_service.detect_text(image_path)

        # Extraer monto y fecha
        from utils.text_parser import extract_amount, extract_date
        monto = extract_amount(texto_extraido) or 0.0
        fecha = extract_date(texto_extraido)

        # Construir mensaje para el validador
        mensaje = self.payment_service.build_validation_message(
            telegram_id=user_id,
            telegram_name=nombre_usuario,
            amount=monto,
            extracted_date=fecha,
        )

        # Verificar duplicados
        if self.payment_service.check_duplicate_payment(user_id, monto):
            dup_info = self.payment_service.get_recent_purchase_info(user_id, monto)
            if dup_info:
                from utils.datetime_utils import format_date_spanish
                fecha_compra = format_date_spanish(dup_info["purchase_date"])
                from utils.keyboards import duplicate_purchase_restriction_keyboard

                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"Ya tienes una compra registrada el *{fecha_compra}*.\n"
                        f"Si tienes problemas contacta a @magic_peru."
                    ),
                    parse_mode="Markdown",
                    reply_markup=duplicate_purchase_restriction_keyboard(tipo_servicio),
                )
                return

        # Enviar al validador
        from utils.keyboards import payment_validation_keyboard

        reply_markup = payment_validation_keyboard(
            user_id=user_id, amount=monto, source="telegram", extra_data=fecha
        )

        for validator_id in self.payment_service.get_validator_ids():
            try:
                await context.bot.send_photo(
                    chat_id=int(validator_id),
                    photo=open(image_path, "rb"),
                    caption=mensaje,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
                logger.info(f"Imagen enviada al validador {validator_id}")
            except Exception as e:
                logger.error(f"Error al enviar al validador {validator_id}: {e}")

        await context.bot.send_message(
            chat_id=user_id,
            text="Para cualquier duda, consulta o problema contáctate con @magic_peru 📲",
        )

    # ------------------------------------------------------------------
    # Validación de pago
    # ------------------------------------------------------------------

    async def _handle_payment_validation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """
        Procesa la acción de validación del validador (validar, rechazar,
        monto incorrecto).
        """
        query = update.callback_query
        validator_id = query.from_user.id
        message_id = query.message.message_id

        # Parsear datos del callback
        action = data[1] if len(data) > 1 else ""
        target_user_id = int(data[2]) if len(data) > 2 else 0
        monto = float(data[3]) if len(data) > 3 else 0.0
        extra = data[4] if len(data) > 4 else ""
        source = data[5] if len(data) > 5 else "telegram"
        image_path = f"./images/trans_{target_user_id}.jpeg"

        logger.info(
            f"Validación: action={action}, validator={validator_id}, "
            f"target={target_user_id}, monto={monto}, source={source}"
        )

        # Verificar duplicados
        if self.payment_service.check_duplicate_payment(target_user_id, monto):
            dup_info = self.payment_service.get_recent_purchase_info(target_user_id, monto)
            if dup_info:
                from utils.datetime_utils import format_date_spanish
                fecha_compra = format_date_spanish(dup_info["purchase_date"])
                service_id = dup_info["service_id"]
                service_name = "Stake" if service_id == 1 else "Grupo VIP"

                await context.bot.send_message(
                    chat_id=validator_id,
                    text=(
                        f"⚠️ Compra duplicada detectada:\n"
                        f"Usuario: {target_user_id}\n"
                        f"Servicio: {service_name}\n"
                        f"Fecha: {fecha_compra}\n"
                        f"Monto: S/ {monto:.2f}"
                    ),
                    reply_to_message_id=message_id,
                )
                await self._safe_edit_message(query, text="⚠️ Compra duplicada.")
                return

        if action == "valid":
            await self._process_valid_payment(
                update, context, query, target_user_id, monto, source, extra, image_path
            )
        elif action == "not_valid":
            await self._process_rejected_payment(
                update, context, query, target_user_id, monto, image_path, message_id
            )
        elif action == "monto_no_reconocido":
            await self._process_incorrect_amount(
                update, context, query, target_user_id, monto, source, message_id
            )

    async def _process_valid_payment(
        self, update, context, query, user_id, monto, source, extra, image_path
    ):
        """Procesa un pago validado exitosamente."""
        await self._safe_edit_message(query, text="✅ ¡Venta validada con éxito!")

        # Actualizar WSP si corresponde
        if source == "wsp" and self.sheets_service:
            self.sheets_service.update_wsp_payment_review_status(telegram_id=user_id)

        # Registrar la compra
        result = self.payment_service.validate_payment(
            telegram_id=user_id,
            amount=monto,
            from_channel=source,
            purchase_date=extra if extra and extra != "wsp" else None,
        )

        if not result.success:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=f"❌ Error al registrar compra: {result.message}",
            )
            return

        # Determinar tipo de servicio
        tipo_servicio = result.service_type if result.service_type else (
            "grupo_vip" if monto > 50 else "stake"
        )

        # Obtener link de invitación
        invite_link = await self._get_invite_link(context, tipo_servicio)

        # Enviar registro a Betsafe
        from utils.keyboards import betsafe_promo_keyboard
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "✅ *¡PAGO VALIDADO EXITOSAMENTE!*\n\n"
                "Ya eres parte de la comunidad Magic 🔮"
            ),
            parse_mode="Markdown",
        )
        if invite_link:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🚀 Aquí tienes tu enlace de invitación mi gato, válido para un solo uso y expira en 24 horas:\n{invite_link}",
            )

        # Confirmar al validador
        user = self.user_service.get_user(user_id)
        user_name = user.telegram_name if user else str(user_id)

        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=(
                f"✅ Pago validado:\n"
                f"Usuario: {user_name} ({user_id})\n"
                f"Monto: S/ {monto:.2f}\n"
                f"Servicio: {tipo_servicio}"
            ),
        )

        # Limpiar
        from core.database import SessionLocal
        from repositories.selected_service_repo import SelectedServiceRepository

        session = SessionLocal()
        try:
            repo = SelectedServiceRepository(session)
            repo.delete_by_user(user_id)
        finally:
            session.close()

        if os.path.exists(image_path):
            os.remove(image_path)
            logger.debug(f"Imagen {image_path} eliminada.")

    async def _process_rejected_payment(
        self, update, context, query, user_id, monto, image_path, message_id
    ):
        """Procesa un pago rechazado."""
        user = self.user_service.get_user(user_id)
        user_name = user.telegram_name if user else str(user_id)

        await self._safe_edit_message(query, text="❌ Pago no validado.")

        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=(
                f"❌ No se validó el pago de {user_name} ({user_id}) "
                f"con monto S/ {monto:.2f}"
            ),
            reply_to_message_id=message_id,
        )

        # Mensaje al comprador
        await context.bot.send_message(
            chat_id=user_id,
            text=self.payment_service.build_rejection_message(user_id),
        )

        # Limpiar imagen
        if os.path.exists(image_path):
            os.remove(image_path)

    async def _process_incorrect_amount(
        self, update, context, query, user_id, monto, source, message_id
    ):
        """Procesa cuando el monto no es reconocido."""
        user = self.user_service.get_user(user_id)
        user_name = user.telegram_name if user else str(user_id)
        validator_id = query.from_user.id

        image_path = f"./images/trans_{user_id}.jpeg"

        if source == "telegram":
            from utils.datetime_utils import get_lima_time_formatted

            # Get PricingService from container for dynamic keyboard
            container = getattr(context, 'container', None)
            if container is None:
                from core.container import container
            pricing = container.resolve("pricing_service") if container.is_registered("pricing_service") else None

            fecha_correcta = get_lima_time_formatted()["ddmmyyyy"]

            mensaje = (
                f"🔍 <b>CONFIRMACIÓN DE PAGO</b>\n\n"
                f"👤 <a href=\"tg://user?id={user_id}\">{user_name}</a>\n"
                f"💵 <b>Monto detectado:</b> S/ {monto:.2f}\n\n"
                f"<b>✏️ Editar:</b> <code>/vm {user_id} {message_id} [monto] [fecha]</code>\n"
                f"<b>💡 Ej:</b> <code>/vm {user_id} {message_id} 125 {fecha_correcta}</code>\n\n"
                f"<i>O seleccione el servicio directamente:</i>"
            )

            # Use dynamic pricing keyboard if available
            if pricing:
                reply_markup = pricing.generate_confirmation_keyboard(user_id=user_id, amount=monto)
            else:
                from utils.keyboards import service_confirmation_keyboard
                reply_markup = service_confirmation_keyboard(
                    user_id=user_id, monto=monto, message_id=message_id, source=source
                )

            if os.path.exists(image_path):
                await context.bot.send_photo(
                    chat_id=validator_id,
                    photo=open(image_path, "rb"),
                    caption=mensaje,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )

        elif source == "wsp":
            await context.bot.send_message(
                chat_id=validator_id,
                text=(
                    f"Ingrese el monto correcto para el usuario {user_name}.\n"
                    f"El monto detectado fue S/ {monto:.2f}.\n\n"
                    f"Responda con el formato:\n"
                    f"/vm {user_id} {message_id} wsp [monto_correcto]"
                ),
            )

        await self._safe_edit_message(query, text="Se ha solicitado la validación del monto.")

    # ------------------------------------------------------------------
    # Confirmación manual de servicio
    # ------------------------------------------------------------------

    async def _handle_manual_service_confirm(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """
        Procesa la confirmación manual del servicio cuando el validador
        selecciona directamente el tipo de servicio (Stake o plan VIP).
        """
        query = update.callback_query
        action = data[1] if len(data) > 1 else ""
        target_user_id = int(data[2]) if len(data) > 2 else 0
        monto = float(data[3]) if len(data) > 3 else 0.0
        validator_id = query.from_user.id

        if action == "valid":
            # Procesar como pago validado
            image_path = f"./images/trans_{target_user_id}.jpeg"
            await self._process_valid_payment(
                update, context, query, target_user_id, monto,
                "telegram", "", image_path
            )

        elif action == "cancel":
            # Cancelar validación
            image_path = f"./images/trans_{target_user_id}.jpeg"
            user = self.user_service.get_user(target_user_id)
            user_name = user.telegram_name if user else str(target_user_id)

            await self._safe_edit_message(query, text="❌ Validación cancelada.")

            await context.bot.send_message(
                chat_id=validator_id,
                text=(
                    f"❌ No se validó el pago de {user_name} ({target_user_id}) "
                    f"con monto desconocido"
                ),
            )

            await context.bot.send_message(
                chat_id=target_user_id,
                text=self.payment_service.build_rejection_message(target_user_id),
            )

            if os.path.exists(image_path):
                os.remove(image_path)

    # ------------------------------------------------------------------
    # Calendario
    # ------------------------------------------------------------------

    async def _handle_calendar_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: list
    ) -> None:
        """Maneja los callbacks de navegación del calendario."""
        query = update.callback_query
        action = data[0]  # cal_prev, cal_next, cal_select, cal_today, cal_cancel

        from utils.keyboards import CalendarKeyboard
        cal = CalendarKeyboard()

        if action in ("cal_prev", "cal_next"):
            year = int(data[1])
            month = int(data[2])
            user_id = int(data[3]) if data[3] != "None" else None
            message_id = int(data[4]) if data[4] != "None" else None

            if action == "cal_next":
                year, month = cal.obtener_mes_siguiente(year, month)
            else:
                year, month = cal.obtener_mes_anterior(year, month)

            await query.edit_message_reply_markup(
                reply_markup=cal.crear_calendario(
                    year=year, month=month,
                    user_id=user_id, message_id=message_id,
                )
            )

        elif action == "cal_select":
            year = int(data[1])
            month = int(data[2])
            day = int(data[3])
            user_id = int(data[4]) if data[4] != "None" else None
            message_id = int(data[5]) if data[5] != "None" else None

            fecha_seleccionada = f"{day:02d}/{month:02d}/{year}"
            await query.edit_message_text(
                text=f"📅 Fecha seleccionada: {fecha_seleccionada}"
            )

        elif action == "cal_today":
            from utils.datetime_utils import get_lima_time_formatted
            fecha = get_lima_time_formatted()["dd/mm/yyyy"]
            await query.edit_message_text(
                text=f"📅 Fecha de hoy: {fecha}"
            )

        elif action == "cal_cancel":
            await query.edit_message_text(text="❌ Selección de fecha cancelada.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _register_user_interaction(
        self, user_id: int, user_name: str
    ) -> None:
        """Registra la interacción del usuario (get-or-create)."""
        try:
            self.user_service.get_or_create_user(user_id, user_name)
        except Exception as e:
            logger.error(f"Error al registrar interacción de {user_id}: {e}")

    async def _get_invite_link(
        self, context: ContextTypes.DEFAULT_TYPE, tipo_servicio: str
    ) -> str | None:
        """
        Obtiene el link de invitación para un tipo de servicio.
        Usa python-telegram-bot para crear un link de un solo uso.
        """
        if tipo_servicio in ("grupo_vip", "Grupo VIP"):
            try:
                chat_id = self.settings.TELEGRAM_VIP_GROUP_ID
                invite = await context.bot.create_chat_invite_link(
                    chat_id=chat_id,
                    expire_date=datetime.now() + __import__("datetime").timedelta(hours=24),
                    member_limit=1,
                    name=f"Link para {tipo_servicio}",
                )
                return invite.invite_link
            except Exception as e:
                logger.error(f"Error al crear invite link VIP: {e}")
                return "https://t.me/+VllSzEZ2smk2MTk5"  # Link por defecto
        else:
            # Stake: obtener link del grupo desde Google Sheets
            if self.sheets_service:
                return self.sheets_service.get_service_group_id(tipo_servicio)
            return None
