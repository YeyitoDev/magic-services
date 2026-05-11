"""
Message Handlers - Magic Chatbot v2
=====================================
Handlers para mensajes de texto que no son comandos y para imágenes
(comprobantes de pago enviados por los usuarios).

Estos handlers actúan como thin controllers: reciben la interacción del
usuario, extraen la información relevante, y delegan la lógica de negocio
a los servicios correspondientes.

Flujos manejados:
- Texto genérico en chat privado → mostrar menú principal o registrar en DynamoDB.
- Imagen (comprobante de transferencia) → OCR → extraer monto → enviar a validador.
- Comando /vm (validar monto) → procesar validación con monto corregido.

Principios:
- Thin Controllers: No contienen lógica de negocio.
- Dependency Injection: Reciben servicios por constructor.
- Early return: Validaciones tempranas para evitar anidamiento profundo.

Uso:
    from handlers.messages import MessageHandlers

    msg_handler = MessageHandlers(
        user_service=user_svc,
        payment_service=payment_svc,
        vision_service=vision_svc,
        promotion_service=promo_svc,
        container=container,
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler.echo))
    app.add_handler(MessageHandler(filters.PHOTO, msg_handler.handle_image))
"""

import logging
import os

from telegram import Chat, Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class MessageHandlers:
    """
    Handlers para mensajes de texto e imágenes en el bot.

    Maneja:
    - Mensajes de texto genéricos (eco / registro).
    - Imágenes de comprobantes de pago (OCR + envío a validador).
    - Comando /vm inline para validación manual de montos.

    Dependencias:
        user_service: UserService para registro de usuarios.
        payment_service: PaymentService para validación de pagos.
        vision_service: GoogleVisionService para OCR de imágenes.
        promotion_service: PromotionService para registro en DynamoDB.
        container: Contenedor de dependencias para resolver otros servicios.
    """

    def __init__(
        self,
        user_service,
        payment_service,
        vision_service,
        promotion_service,
        container,
    ) -> None:
        """
        Inicializa los handlers de mensajes con sus dependencias.

        Args:
            user_service: Servicio de gestión de usuarios.
            payment_service: Servicio de validación de pagos.
            vision_service: Servicio de Google Vision para OCR.
            promotion_service: Servicio de pipeline de promociones.
            container: Contenedor IoC para resolver servicios bajo demanda.
        """
        self._user_service = user_service
        self._payment_service = payment_service
        self._vision_service = vision_service
        self._promotion_service = promotion_service
        self._container = container

        # Servicios que se resuelven lazy del contenedor
        self._subscription_service = None
        self._selected_service_repo = None
        self._telegram_api = None

    # ------------------------------------------------------------------
    # Propiedades lazy para dependencias opcionales
    # ------------------------------------------------------------------

    @property
    def subscription_service(self):
        """Obtiene SubscriptionService del contenedor (lazy)."""
        if self._subscription_service is None:
            self._subscription_service = self._container.resolve(
                "subscription_service"
            )
        return self._subscription_service

    @property
    def selected_service_repo(self):
        """Obtiene SelectedServiceRepository del contenedor (lazy)."""
        if self._selected_service_repo is None:
            self._selected_service_repo = self._container.resolve(
                "selected_service_repository"
            )
        return self._selected_service_repo

    @property
    def telegram_api(self):
        """Obtiene TelegramAPIService del contenedor (lazy)."""
        if self._telegram_api is None:
            from services.telegram_api import TelegramAPIService
            self._telegram_api = TelegramAPIService()
        return self._telegram_api

    # ------------------------------------------------------------------
    # Handler de texto genérico (eco)
    # ------------------------------------------------------------------

    async def echo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Maneja mensajes de texto que no son comandos en chats privados.

        Flujo:
        1. Registra al usuario en la base de datos (get_or_create).
        2. Registra al usuario en el pipeline de promociones (DynamoDB).
        3. Muestra el menú principal del bot.

        Args:
            update: Objeto Update de python-telegram-bot.
            context: Contexto de la conversación.
        """
        chat_type = update.message.chat.type
        user_id = int(update.message.from_user.id)
        user_name = update.message.chat.first_name or "Usuario"

        # Solo responder en chats privados (ignorar grupos)
        if chat_type != Chat.PRIVATE:
            return

        # Verificar si el mensaje contiene el comando /vm (validación manual)
        user_message = update.message.text or ""
        if user_message.startswith("/vm"):
            await self._handle_vm_command(update, context)
            return

        # Registrar usuario en BD
        try:
            self._user_service.register_user(
                telegram_id=user_id,
                telegram_name=user_name,
            )
            logger.debug(f"Usuario registrado/actualizado: {user_id}")
        except Exception as e:
            logger.error(f"Error al registrar usuario {user_id}: {e}")

        # Registrar en pipeline de promociones (DynamoDB)
        try:
            self._promotion_service.register_user(str(user_id))
            logger.debug(f"Usuario {user_id} registrado en pipeline de promociones")
        except Exception as e:
            logger.warning(
                f"No se pudo registrar usuario {user_id} en DynamoDB: {e}"
            )

        # Mostrar menú principal
        await self._send_main_menu(update, context, user_id)

    # ------------------------------------------------------------------
    # Handler de imágenes (comprobantes de pago)
    # ------------------------------------------------------------------

    async def handle_image(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Procesa una imagen enviada por el usuario (comprobante de transferencia).

        Flujo completo:
        1. Verificar que sea un chat privado.
        2. Descargar la imagen al sistema de archivos local.
        3. Ejecutar OCR con Google Vision para extraer texto.
        4. Extraer monto y fecha del texto mediante regex.
        5. Verificar duplicados (últimas 24h).
        6. Si es duplicado → notificar al usuario y al validador.
        7. Si no es duplicado → enviar imagen + datos al validador para aprobación.
        8. Confirmar al usuario que su pago está siendo validado.

        Args:
            update: Objeto Update con la foto.
            context: Contexto de la conversación.
        """
        chat_type = update.message.chat.type

        # Solo procesar imágenes en chats privados
        if chat_type != Chat.PRIVATE:
            logger.debug("Imagen recibida en chat no privado, ignorando.")
            return

        user_id = int(update.message.from_user.id)
        user_name = update.message.chat.first_name or "Usuario"

        logger.info(
            f"Imagen recibida de usuario {user_id} ({user_name})"
        )

        # --- Paso 1: Descargar la imagen ---
        photo = await update.message.photo[-1].get_file()
        image_path = f"./images/trans_{user_id}.jpeg"

        # Asegurar que el directorio existe
        os.makedirs("./images", exist_ok=True)

        await photo.download_to_drive(image_path)
        logger.info(f"Imagen guardada en: {image_path}")

        # --- Paso 2: OCR con Google Vision ---
        try:
            detected_text = self._vision_service.detect_text(image_path)
            logger.debug(f"Texto detectado: {detected_text[:200]}...")
        except Exception as e:
            logger.error(f"Error en OCR para user={user_id}: {e}")
            await update.message.reply_text(
                "❌ No pude leer tu comprobante. "
                "Por favor envía una imagen más clara o contacta a @magic_peru."
            )
            return

        # --- Paso 3: Extraer monto y fecha del texto ---
        from utils.datetime_utils import get_lima_time_formatted
        from utils.text_parser import extract_amount, extract_date

        monto_extraido = extract_amount(detected_text)
        fecha_extraida = extract_date(detected_text)

        if monto_extraido is None:
            logger.warning(
                f"No se pudo extraer monto del comprobante de user={user_id}"
            )
            await update.message.reply_text(
                "❌ No pude identificar el monto en tu comprobante. "
                "Asegúrate de que la imagen sea clara y muestre el monto de la transferencia.\n\n"
                "Si el problema persiste, contacta a @magic_peru."
            )
            return

        fecha_actual = get_lima_time_formatted()["fecha_completa"]

        logger.info(
            f"Comprobante user={user_id}: monto=S/ {monto_extraido:.2f}, "
            f"fecha_detectada={fecha_extraida or 'No detectada'}"
        )

        # --- Paso 4: Verificar duplicados ---
        if self._payment_service.check_duplicate_payment(user_id, monto_extraido):
            logger.info(
                f"Compra duplicada detectada para user={user_id}, "
                f"monto=S/ {monto_extraido:.2f}"
            )
            await self._handle_duplicate_payment(
                update, context, user_id, user_name, monto_extraido
            )
            return

        # --- Paso 5: Enviar al validador ---
        await self._send_to_validator(
            update=update,
            context=context,
            user_id=user_id,
            user_name=user_name,
            amount=monto_extraido,
            extracted_date=fecha_extraida or fecha_actual,
            image_path=image_path,
        )

        # --- Paso 6: Confirmar al usuario ---
        await update.message.reply_text(
            "✅ Recibí tu comprobante de pago. "
            "En un momento procederé a validar tu pago."
        )
        await update.message.reply_text(
            "📲 Para cualquier duda, consulta o problema, "
            "contáctate con @magic_peru"
        )

        logger.info(
            f"Comprobante de user={user_id} enviado al validador para revisión."
        )

    # ------------------------------------------------------------------
    # Métodos auxiliares privados
    # ------------------------------------------------------------------

    async def _send_main_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
    ) -> None:
        """
        Envía el menú principal del bot al usuario.

        Args:
            update: Update de Telegram.
            context: Contexto de la conversación.
            user_id: ID de Telegram del usuario.
        """
        from utils.keyboards import main_menu_don_gato_keyboard

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🔥 <b>¡BIENVENIDO A MAGIC BET!</b> 🔮\n\n"
                "Somos la comunidad de apuestas deportivas más rentable del Perú. "
                "Selecciona una opción para comenzar:"
            ),
            reply_markup=main_menu_don_gato_keyboard(),
            parse_mode="HTML",
        )

    async def _send_to_validator(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        user_name: str,
        amount: float,
        extracted_date: str,
        image_path: str,
    ) -> None:
        """
        Envía la imagen del comprobante y los datos extraídos a todos
        los validadores autorizados para su revisión.

        Args:
            update: Update de Telegram.
            context: Contexto de la conversación.
            user_id: ID de Telegram del comprador.
            user_name: Nombre del comprador.
            amount: Monto extraído del comprobante.
            extracted_date: Fecha extraída del comprobante.
            image_path: Ruta local a la imagen del comprobante.
        """
        from utils.keyboards import payment_validation_keyboard

        # Construir mensaje para el validador
        validation_message = self._payment_service.build_validation_message(
            telegram_id=user_id,
            telegram_name=user_name,
            amount=amount,
            extracted_date=extracted_date,
        )

        # Construir teclado de validación
        reply_markup = payment_validation_keyboard(
            user_id=user_id,
            amount=amount,
            source="telegram",
            extra_data=extracted_date,
        )

        # Obtener lista de validadores
        validator_ids = self._payment_service.get_validator_ids()

        # Enviar a cada validador
        for validator_id in validator_ids:
            try:
                await context.bot.send_photo(
                    chat_id=int(validator_id),
                    photo=open(image_path, "rb"),
                    caption=validation_message,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
                logger.info(
                    f"Comprobante enviado al validador {validator_id} "
                    f"para user={user_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error al enviar comprobante al validador {validator_id}: {e}"
                )

    async def _handle_duplicate_payment(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        user_name: str,
        amount: float,
    ) -> None:
        """
        Maneja el caso cuando se detecta una compra duplicada.

        Notifica al usuario que su compra ya fue registrada y le proporciona
        el enlace de invitación correspondiente.

        Args:
            update: Update de Telegram.
            context: Contexto de la conversación.
            user_id: ID del comprador.
            user_name: Nombre del comprador.
            amount: Monto de la compra duplicada.
        """
        # Obtener info de la compra duplicada
        purchase_info = self._payment_service.get_recent_purchase_info(
            telegram_id=user_id,
            amount=amount,
        )

        if purchase_info is None:
            await update.message.reply_text(
                "⚠️ Parece que ya procesamos tu pago recientemente. "
                "Si crees que es un error, contacta a @magic_peru."
            )
            return

        # Determinar tipo de servicio y obtener link de invitación
        service_id = purchase_info.get("service_id", 0)
        service_name = "Grupo VIP" if service_id == 2 else "Stake"

        # Obtener link de invitación
        invite_link = None
        try:
            if service_name == "Grupo VIP":
                from config.settings import settings
                chat_id = int(settings.TELEGRAM_VIP_GROUP_ID)
                invite_link = self.telegram_api.create_invite_link(
                    chat_id=chat_id,
                    member_limit=1,
                    name=f"Reenvío para {user_name}",
                )
            elif service_name == "Stake":
                # Para Stake, obtener el ID del grupo desde Google Sheets
                sheets_service = self._container.resolve("google_sheets_service") \
                    if self._container.is_registered("google_sheets_service") else None
                if sheets_service:
                    group_id = sheets_service.get_service_group_id("Stake")
                    if group_id:
                        invite_link = self.telegram_api.create_invite_link(
                            chat_id=int(group_id),
                            member_limit=1,
                        )
        except Exception as e:
            logger.error(f"Error al obtener link de invitación: {e}")
            invite_link = None

        # Formatear la fecha de compra
        from utils.datetime_utils import format_date_spanish
        purchase_date = purchase_info.get("purchase_date")
        formatted_date = format_date_spanish(purchase_date) if purchase_date else "fecha desconocida"

        # Notificar al usuario
        from utils.keyboards import duplicate_purchase_restriction_keyboard

        await update.message.reply_text(
            f"ℹ️ <b>YA TIENES UNA COMPRA REGISTRADA</b>\n\n"
            f"Detectamos que ya realizaste un pago de <b>S/ {amount:.2f}</b> "
            f"por el servicio <b>{service_name}</b> el {formatted_date}.\n\n"
            f"No es necesario que vuelvas a enviar el comprobante. "
            f"Si perdiste tu enlace de invitación, contáctanos.",
            reply_markup=duplicate_purchase_restriction_keyboard(service_name),
            parse_mode="HTML",
        )

        if invite_link:
            await update.message.reply_text(
                f"🔗 Aquí tienes tu enlace de invitación nuevamente:\n{invite_link}"
            )

    async def _handle_vm_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """
        Procesa el comando /vm (validación manual de monto).

        Formato esperado: /vm [user_id] [message_id] [monto_correcto] [fecha_opcional]

        Este comando es usado por los validadores para corregir manualmente
        el monto cuando el OCR no pudo extraerlo correctamente.

        Args:
            update: Update de Telegram.
            context: Contexto de la conversación.
        """
        business_user_id = int(update.effective_user.id)

        # Verificar que quien ejecuta el comando sea un validador autorizado
        if not self._payment_service.is_validator_authorized(business_user_id):
            await update.message.reply_text(
                "⛔ No estás autorizado para validar pagos."
            )
            return

        message_text = update.message.text
        parts = message_text.split()

        if len(parts) < 4:
            await update.message.reply_text(
                "❌ Formato incorrecto. Uso:\n"
                "<code>/vm [user_id] [message_id] [monto_correcto] [fecha_correcta]</code>\n\n"
                "Ejemplo: <code>/vm 12345 67890 125 15012025</code>",
                parse_mode="HTML",
            )
            return

        try:
            target_user_id = int(parts[1])
            parts[2]
            corrected_amount = float(parts[3])
        except (ValueError, IndexError) as e:
            await update.message.reply_text(
                f"❌ Error al parsear los datos: {e}\n"
                f"Formato: /vm [user_id] [message_id] [monto] [fecha_opcional]"
            )
            return

        # Obtener fecha opcional
        fecha_extraida = parts[4] if len(parts) >= 5 else None

        # Verificar duplicados
        if self._payment_service.check_duplicate_payment(
            target_user_id, corrected_amount
        ):
            purchase_info = self._payment_service.get_recent_purchase_info(
                telegram_id=target_user_id,
                amount=corrected_amount,
            )
            if purchase_info:
                from utils.datetime_utils import format_date_spanish
                formatted_date = format_date_spanish(
                    purchase_info.get("purchase_date")
                ) if purchase_info.get("purchase_date") else "fecha desconocida"

                await update.message.reply_text(
                    f"⚠️ Este usuario ya tiene una compra registrada por "
                    f"S/ {corrected_amount:.2f} el {formatted_date}. "
                    f"No se procesará duplicado."
                )
                return

        # Procesar el pago con el monto corregido
        result = self._payment_service.validate_with_corrected_amount(
            telegram_id=target_user_id,
            corrected_amount=corrected_amount,
            from_channel="telegram",
            purchase_date=fecha_extraida,
        )

        if result.success:
            await update.message.reply_text(
                f"✅ Pago validado correctamente para el usuario {target_user_id}.\n"
                f"Monto: S/ {corrected_amount:.2f}\n"
                f"Resultado: {result.message}"
            )

            # Notificar al comprador y enviar link de invitación
            await self._notify_purchase_success(
                context=context,
                user_id=target_user_id,
                result=result,
            )
        else:
            await update.message.reply_text(
                f"❌ No se pudo validar el pago para {target_user_id}:\n"
                f"{result.message}"
            )

    async def _notify_purchase_success(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: int,
        result,
    ) -> None:
        """
        Notifica al comprador que su pago fue validado y envía el link
        de invitación al grupo correspondiente.

        Args:
            context: Contexto de la conversación.
            user_id: ID de Telegram del comprador.
            result: PurchaseResult con info del servicio adquirido.
        """
        try:
            from config.settings import settings

            service_type = result.service_type
            invite_link = None

            if service_type == "grupo_vip":
                chat_id = int(settings.TELEGRAM_VIP_GROUP_ID)
                invite_link = self.telegram_api.create_invite_link(
                    chat_id=chat_id,
                    member_limit=1,
                    name=f"VIP para {user_id}",
                )
            elif service_type == "stake":
                # Para Stake, obtener el ID del grupo desde Google Sheets
                try:
                    sheets_service = self._container.resolve(
                        "google_sheets_service"
                    ) if self._container.is_registered("google_sheets_service") else None
                    if sheets_service:
                        group_id = sheets_service.get_service_group_id("Stake")
                        if group_id:
                            invite_link = self.telegram_api.create_invite_link(
                                chat_id=int(group_id),
                                member_limit=1,
                            )
                except Exception as e:
                    logger.warning(f"No se pudo obtener link de Stake: {e}")

            # Enviar mensaje de confirmación al comprador
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 <b>¡PAGO VALIDADO CON ÉXITO!</b>\n\n"
                    f"Servicio: <b>{service_type.upper()}</b>\n"
                    f"Monto: S/ {result.purchase_result.price:.2f}\n\n"
                    f"¡Bienvenido a la comunidad más rentable del Perú! 🔮"
                ),
                parse_mode="HTML",
            )

            if invite_link:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🔗 Aquí tienes tu enlace de invitación al grupo:\n"
                        f"{invite_link}\n\n"
                        f"⚠️ Este enlace es de <b>un solo uso</b> y expira en 24 horas."
                    ),
                    parse_mode="HTML",
                )

            # Enviar mensaje de registro a Betsafe
            from config.settings import settings
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "🎁 <b>¡TE REGALO 70 SOLES GRATIS!</b>\n\n"
                    "Regístrate en Betsafe con este link exclusivo, "
                    "haz tu primer depósito de mínimo S/ 40 y recibe "
                    "<b>S/ 70 totalmente gratis</b> para apostar."
                ),
                parse_mode="HTML",
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=settings.BETSAFE_PROMO_LINK,
            )

            # Limpiar servicio seleccionado
            try:
                self.selected_service_repo.delete_by_user(user_id)
                logger.debug(f"Servicio seleccionado eliminado para user={user_id}")
            except Exception as e:
                logger.warning(f"No se pudo limpiar selección de user={user_id}: {e}")

            # Eliminar imagen del comprobante
            image_path = f"./images/trans_{user_id}.jpeg"
            if os.path.exists(image_path):
                os.remove(image_path)
                logger.debug(f"Imagen eliminada: {image_path}")

        except Exception as e:
            logger.error(
                f"Error al notificar compra exitosa a user={user_id}: {e}",
                exc_info=True,
            )
