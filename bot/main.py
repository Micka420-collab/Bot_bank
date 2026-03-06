"""
🎮 GameVault Bot - Main Telegram Bot
Bot principal avec toutes les commandes et interactions
"""
import asyncio
import logging
import json
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    CallbackQuery, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

from config.settings import (
    BOT_TOKEN, ADMIN_IDS, SUPPORT_USERNAME, GAMES, DELIVERY_MODES,
    REFERRAL_REWARD_PERCENT, REFERRAL_COMMISSION_PERCENT
)
from database.db import (
    init_database, get_or_create_user, get_stock_count, reserve_account,
    deliver_account, create_order, update_order_payment, update_order_status,
    get_user_orders, get_order, add_review, get_reviews, get_average_rating,
    create_ticket, add_ticket_message, release_expired_reservations,
    get_all_stock, ban_user, add_accounts, get_stats, is_user_banned
)
from utils.antifraud import AntifraudEngine
from payments.handlers import PaymentRouter, PaymentError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 🏠 COMMANDES PRINCIPALES
# ══════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start - Menu principal"""
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username, user.first_name)

    # Gestion des deep links (retour de paiement, parrainage)
    if context.args:
        arg = context.args[0]
        if arg.startswith("paid_"):
            order_ref = arg.replace("paid_", "")
            return await handle_payment_return(update, context, order_ref)
        elif arg.startswith("ref_"):
            referral_code = arg.replace("ref_", "")
            context.user_data["referral_code"] = referral_code

    # Check ban
    if is_user_banned(user.id):
        await update.message.reply_text(
            "🚫 Votre compte est temporairement suspendu.\n"
            f"Contactez le SAV: {SUPPORT_USERNAME}"
        )
        return

    rating = get_average_rating()
    rating_text = f"⭐ {rating['average']}/5 ({rating['count']} avis)" if rating['count'] > 0 else "🆕 Nouveau shop"

    welcome = (
        f"🎮 **Bienvenue sur GameVault, {user.first_name}!**\n\n"
        f"Le shop N°1 de comptes gaming premium.\n"
        f"{rating_text}\n\n"
        f"🔒 Paiement sécurisé | ⚡ Livraison instantanée\n"
        f"💰 Garantie satisfait ou remboursé\n\n"
        f"Que souhaitez-vous faire ?"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Acheter un compte", callback_data="shop")],
        [InlineKeyboardButton("📦 Mes commandes", callback_data="my_orders"),
         InlineKeyboardButton("⭐ Avis clients", callback_data="reviews")],
        [InlineKeyboardButton("🎁 Parrainage", callback_data="referral"),
         InlineKeyboardButton("❓ SAV / Support", callback_data="support")],
        [InlineKeyboardButton("ℹ️ Mon compte", callback_data="account")],
    ]

    await update.message.reply_text(
        welcome,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    text = (
        "🎮 **GameVault - Aide**\n\n"
        "**Commandes disponibles:**\n"
        "/start - Menu principal\n"
        "/shop - Voir les comptes disponibles\n"
        "/orders - Mes commandes\n"
        "/referral - Mon code de parrainage\n"
        "/support - Contacter le SAV\n"
        "/reviews - Voir les avis clients\n\n"
        f"**Support:** {SUPPORT_USERNAME}\n"
        "**Livraison:** De 15 min à 24h selon le mode choisi"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ══════════════════════════════════════════════
# 🛒 SHOP & CATALOGUE
# ══════════════════════════════════════════════

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le catalogue des jeux"""
    query = update.callback_query
    if query:
        await query.answer()

    keyboard = []
    for game_id, game in GAMES.items():
        # Compter le stock total
        total_stock = sum(get_stock_count(game_id, tier) for tier in game["tiers"])
        stock_emoji = "🟢" if total_stock > 5 else "🟡" if total_stock > 0 else "🔴"
        keyboard.append([
            InlineKeyboardButton(
                f"{game['emoji']} {game['name']} {stock_emoji} ({total_stock} dispo)",
                callback_data=f"game_{game_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="home")])

    text = (
        "🛒 **SHOP - Choisissez votre jeu**\n\n"
        "🟢 En stock | 🟡 Stock limité | 🔴 Rupture\n"
    )

    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def game_tiers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les tiers d'un jeu"""
    query = update.callback_query
    await query.answer()

    game_id = query.data.replace("game_", "")
    game = GAMES.get(game_id)
    if not game:
        await query.edit_message_text("❌ Jeu introuvable.")
        return

    context.user_data["selected_game"] = game_id

    keyboard = []
    for tier_id, tier in game["tiers"].items():
        stock = get_stock_count(game_id, tier_id)
        if stock > 0:
            keyboard.append([
                InlineKeyboardButton(
                    f"{tier['name']} - {tier['price']:.2f}€ ({stock} dispo)",
                    callback_data=f"tier_{game_id}_{tier_id}"
                )
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {tier['name']} - RUPTURE",
                    callback_data=f"oos_{game_id}_{tier_id}"
                )
            ])

    keyboard.append([InlineKeyboardButton("🔙 Retour au shop", callback_data="shop")])

    text = (
        f"{game['emoji']} **{game['name']}**\n\n"
        f"Choisissez votre formule:\n"
    )
    for tier_id, tier in game["tiers"].items():
        text += f"\n**{tier['name']}** - {tier['price']:.2f}€\n{tier['description']}\n"

    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def out_of_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les clics sur produits en rupture"""
    query = update.callback_query
    await query.answer(
        "❌ Ce produit est en rupture de stock.\n"
        "🔄 Recharge prévue bientôt!\n"
        f"📞 Besoin urgent? Contactez {SUPPORT_USERNAME}\n"
        "⚠️ Les demandes exceptionnelles sont plus chères.",
        show_alert=True
    )


# ══════════════════════════════════════════════
# 🚚 LIVRAISON & COMMANDE
# ══════════════════════════════════════════════

async def select_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du mode de livraison"""
    query = update.callback_query
    await query.answer()

    parts = query.data.replace("tier_", "").split("_")
    game_id, tier_id = parts[0], parts[1]
    game = GAMES[game_id]
    tier = game["tiers"][tier_id]

    # Anti-fraude check
    fraud_check = AntifraudEngine.check_user(query.from_user.id)
    if not fraud_check["allowed"]:
        await query.edit_message_text(fraud_check["reason"])
        return

    context.user_data["selected_game"] = game_id
    context.user_data["selected_tier"] = tier_id
    context.user_data["base_price"] = tier["price"]

    keyboard = []
    for mode_id, mode in DELIVERY_MODES.items():
        final_price = tier["price"] * mode["multiplier"]
        keyboard.append([
            InlineKeyboardButton(
                f"{mode['name']} - {final_price:.2f}€",
                callback_data=f"delivery_{mode_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data=f"game_{game_id}")])

    text = (
        f"🚚 **Mode de livraison**\n\n"
        f"Produit: {game['emoji']} {game['name']} - {tier['name']}\n"
        f"Prix de base: {tier['price']:.2f}€\n\n"
        f"Choisissez votre vitesse de livraison:"
    )

    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def select_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sélection du moyen de paiement"""
    query = update.callback_query
    await query.answer()

    delivery_mode = query.data.replace("delivery_", "")
    context.user_data["delivery_mode"] = delivery_mode

    game_id = context.user_data["selected_game"]
    tier_id = context.user_data["selected_tier"]
    base_price = context.user_data["base_price"]
    multiplier = DELIVERY_MODES[delivery_mode]["multiplier"]
    final_price = base_price * multiplier

    # Appliquer réduction parrainage
    discount = 0
    referral_code = context.user_data.get("referral_code")
    if referral_code:
        discount = final_price * (REFERRAL_REWARD_PERCENT / 100)
        final_price -= discount

    context.user_data["final_price"] = final_price
    context.user_data["discount"] = discount

    game = GAMES[game_id]
    tier = game["tiers"][tier_id]
    mode = DELIVERY_MODES[delivery_mode]

    keyboard = [
        [InlineKeyboardButton("💳 Carte Bancaire", callback_data="pay_stripe")],
        [InlineKeyboardButton("🅿️ PayPal", callback_data="pay_paypal")],
        [InlineKeyboardButton("₿ Crypto (BTC/ETH/USDT)", callback_data="pay_crypto")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"tier_{game_id}_{tier_id}")],
    ]

    text = (
        f"💰 **Récapitulatif de commande**\n\n"
        f"🎮 {game['emoji']} {game['name']} - {tier['name']}\n"
        f"🚚 {mode['name']}\n"
        f"{'💸 Réduction parrainage: -' + f'{discount:.2f}€' + chr(10) if discount else ''}"
        f"\n**💶 Total: {final_price:.2f}€**\n\n"
        f"Choisissez votre moyen de paiement:"
    )

    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite le paiement"""
    query = update.callback_query
    await query.answer()

    method = query.data.replace("pay_", "")
    user_id = query.from_user.id
    game_id = context.user_data["selected_game"]
    tier_id = context.user_data["selected_tier"]
    delivery_mode = context.user_data["delivery_mode"]
    final_price = context.user_data["final_price"]
    base_price = context.user_data["base_price"]
    discount = context.user_data.get("discount", 0)
    referral_code = context.user_data.get("referral_code")

    # Vérifier le stock une dernière fois
    stock = get_stock_count(game_id, tier_id)
    if stock <= 0:
        await query.edit_message_text(
            f"❌ **Rupture de stock!**\n\n"
            f"Ce compte n'est plus disponible.\n"
            f"🔄 Recharge prévue bientôt!\n"
            f"📞 Besoin urgent? {SUPPORT_USERNAME}\n"
            f"⚠️ Demande exceptionnelle = tarif majoré + livraison prioritaire",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Réserver le compte
    account_id = reserve_account(game_id, tier_id, user_id)
    if not account_id:
        await query.edit_message_text("❌ Erreur de réservation. Réessayez.")
        return

    # Créer la commande
    order = create_order(
        user_id, game_id, tier_id, delivery_mode,
        base_price, final_price, discount, referral_code
    )
    context.user_data["current_order"] = order["order_ref"]
    context.user_data["account_id"] = account_id

    # Créer le lien de paiement
    try:
        payment = await PaymentRouter.create_payment(method, order["order_ref"], final_price)
        update_order_payment(order["order_ref"], method, payment["payment_id"], "pending")

        keyboard = [
            [InlineKeyboardButton("💳 Payer maintenant", url=payment["payment_url"])],
            [InlineKeyboardButton("✅ J'ai payé", callback_data=f"confirm_paid_{order['order_ref']}")],
            [InlineKeyboardButton("❌ Annuler", callback_data=f"cancel_order_{order['order_ref']}")],
        ]

        await query.edit_message_text(
            f"🔗 **Lien de paiement généré!**\n\n"
            f"📋 Commande: `{order['order_ref']}`\n"
            f"💶 Montant: {final_price:.2f}€\n\n"
            f"⏳ Ce lien expire dans 30 minutes.\n"
            f"Cliquez ci-dessous pour payer:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except PaymentError as e:
        logger.error(f"Payment error: {e}")
        AntifraudEngine.log_payment_failure(user_id, str(e))
        await query.edit_message_text(
            f"❌ Erreur de paiement: {e}\n\nVeuillez réessayer ou choisir un autre moyen de paiement."
        )


async def confirm_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quand l'utilisateur confirme avoir payé"""
    query = update.callback_query
    await query.answer()

    order_ref = query.data.replace("confirm_paid_", "")
    order = get_order(order_ref)

    if not order:
        await query.edit_message_text("❌ Commande introuvable.")
        return

    # En production: vérifier côté serveur que le paiement est reçu
    # Pour l'instant, on fait confiance + vérification manuelle admin

    await query.edit_message_text(
        f"⏳ **Vérification du paiement en cours...**\n\n"
        f"📋 Commande: `{order_ref}`\n\n"
        f"Votre paiement est en cours de vérification.\n"
        f"Vous recevrez vos identifiants dès confirmation.\n\n"
        f"⏱️ Délai estimé: {DELIVERY_MODES[order['delivery_mode']]['name']}\n"
        f"📞 Problème? {SUPPORT_USERNAME}",
        parse_mode=ParseMode.MARKDOWN
    )

    # Notifier les admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🔔 **Nouvelle commande à vérifier!**\n\n"
                f"📋 {order_ref}\n"
                f"👤 @{query.from_user.username or 'N/A'}\n"
                f"🎮 {GAMES[order['game']]['name']} - {order['tier']}\n"
                f"💶 {order['final_price']:.2f}€\n"
                f"💳 {order['payment_method']}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass


async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Annulation d'une commande"""
    query = update.callback_query
    await query.answer()
    order_ref = query.data.replace("cancel_order_", "")
    update_order_status(order_ref, "cancelled")
    await query.edit_message_text(
        f"❌ Commande `{order_ref}` annulée.\n\nTapez /start pour revenir au menu.",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_payment_return(update: Update, context: ContextTypes.DEFAULT_TYPE, order_ref: str):
    """Gère le retour depuis un lien de paiement"""
    order = get_order(order_ref)
    if order and order["payment_status"] == "pending":
        await update.message.reply_text(
            f"⏳ **Vérification en cours...**\n\n"
            f"Commande `{order_ref}` en cours de traitement.\n"
            f"Vous recevrez vos identifiants bientôt!",
            parse_mode=ParseMode.MARKDOWN
        )


# ══════════════════════════════════════════════
# 📦 MES COMMANDES
# ══════════════════════════════════════════════

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les commandes de l'utilisateur"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user_id = (query or update).from_user.id if query else update.effective_user.id
    orders = get_user_orders(user_id)

    if not orders:
        text = "📦 **Mes commandes**\n\nAucune commande pour le moment.\nTapez /shop pour commencer!"
        if query:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    status_emojis = {
        "pending": "⏳", "processing": "🔄", "delivered": "✅",
        "cancelled": "❌", "refunded": "💸"
    }

    text = "📦 **Mes commandes**\n\n"
    keyboard = []
    for order in orders[:10]:
        emoji = status_emojis.get(order["order_status"], "❓")
        game = GAMES.get(order["game"], {})
        text += (
            f"{emoji} `{order['order_ref']}`\n"
            f"   {game.get('emoji', '')} {order['tier']} - {order['final_price']:.2f}€\n\n"
        )
        if order["order_status"] == "delivered" and order.get("id"):
            keyboard.append([
                InlineKeyboardButton(f"⭐ Noter {order['order_ref']}", callback_data=f"review_{order['id']}")
            ])

    keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="home")])

    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════
# ⭐ REVIEWS
# ══════════════════════════════════════════════

async def show_reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les avis clients"""
    query = update.callback_query
    if query:
        await query.answer()

    reviews = get_reviews(limit=10)
    avg = get_average_rating()

    text = f"⭐ **Avis clients** - {avg['average']}/5 ({avg['count']} avis)\n\n"

    if not reviews:
        text += "Aucun avis pour le moment."
    else:
        for r in reviews:
            stars = "⭐" * r["rating"] + "☆" * (5 - r["rating"])
            username = r["username"] or "Anonyme"
            text += f"{stars}\n@{username[:3]}*** - {GAMES.get(r['game'], {}).get('name', r['game'])}\n"
            if r["comment"]:
                text += f"_{r['comment'][:100]}_\n"
            text += "\n"

    keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="home")]]

    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def ask_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Demande une note"""
    query = update.callback_query
    await query.answer()

    order_id = query.data.replace("review_", "")
    context.user_data["reviewing_order"] = int(order_id)

    keyboard = [
        [InlineKeyboardButton(f"{'⭐' * i}", callback_data=f"rate_{i}") for i in range(1, 6)]
    ]
    keyboard.append([InlineKeyboardButton("🔙 Retour", callback_data="my_orders")])

    await query.edit_message_text(
        "⭐ **Notez votre achat**\n\nChoisissez une note de 1 à 5 étoiles:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def save_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enregistre la note"""
    query = update.callback_query
    await query.answer()

    rating = int(query.data.replace("rate_", ""))
    order_id = context.user_data.get("reviewing_order")

    if order_id:
        add_review(order_id, query.from_user.id, rating)
        await query.edit_message_text(
            f"✅ Merci pour votre avis! {'⭐' * rating}\n\nTapez /start pour revenir au menu."
        )


# ══════════════════════════════════════════════
# 🎁 PARRAINAGE
# ══════════════════════════════════════════════

async def referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu de parrainage"""
    query = update.callback_query
    if query:
        await query.answer()

    user_id = query.from_user.id if query else update.effective_user.id
    user = get_or_create_user(user_id)

    bot_info = await context.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user['referral_code']}"

    text = (
        f"🎁 **Programme de parrainage**\n\n"
        f"📋 Votre code: `{user['referral_code']}`\n"
        f"🔗 Votre lien:\n{referral_link}\n\n"
        f"**Avantages:**\n"
        f"👤 Votre filleul: -{REFERRAL_REWARD_PERCENT}% sur sa 1ère commande\n"
        f"💰 Vous: {REFERRAL_COMMISSION_PERCENT}% de commission\n"
        f"\n💵 Solde commissions: {user['balance']:.2f}€"
    )

    keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="home")]]

    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════
# 📞 SAV / SUPPORT
# ══════════════════════════════════════════════

async def support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu SAV"""
    query = update.callback_query
    if query:
        await query.answer()

    keyboard = [
        [InlineKeyboardButton("📩 Ouvrir un ticket", callback_data="new_ticket")],
        [InlineKeyboardButton("📋 Mes tickets", callback_data="my_tickets")],
        [InlineKeyboardButton(f"💬 Contact direct: {SUPPORT_USERNAME}", url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton("🔙 Menu", callback_data="home")],
    ]

    text = (
        "📞 **Service Après-Vente**\n\n"
        "Choisissez une option:\n\n"
        "📩 **Ticket** - Réponse sous 24h\n"
        f"💬 **Contact direct** - Pour les urgences\n\n"
        "⚠️ Les demandes exceptionnelles (hors stock,\n"
        "livraison urgente) sont facturées en supplément."
    )

    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crée un nouveau ticket"""
    query = update.callback_query
    await query.answer()
    context.user_data["creating_ticket"] = True
    await query.edit_message_text(
        "📩 **Nouveau ticket SAV**\n\n"
        "Décrivez votre problème en un message.\n"
        "Incluez votre numéro de commande si applicable.\n\n"
        "Tapez /cancel pour annuler.",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les messages de tickets"""
    if not context.user_data.get("creating_ticket"):
        return

    user_id = update.effective_user.id
    message = update.message.text

    ticket_id = create_ticket(user_id, message[:100], priority="normal")
    add_ticket_message(ticket_id, "user", message)

    context.user_data["creating_ticket"] = False

    # Notifier admins
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🎫 **Nouveau ticket #{ticket_id}**\n"
                f"👤 @{update.effective_user.username or 'N/A'}\n"
                f"📝 {message[:200]}",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ **Ticket #{ticket_id} créé!**\n\n"
        f"Notre équipe vous répondra sous 24h.\n"
        f"📞 Urgence? Contactez {SUPPORT_USERNAME}",
        parse_mode=ParseMode.MARKDOWN
    )


# ══════════════════════════════════════════════
# 👤 MON COMPTE
# ══════════════════════════════════════════════

async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les infos du compte"""
    query = update.callback_query
    await query.answer()

    user = get_or_create_user(query.from_user.id)

    text = (
        f"👤 **Mon compte**\n\n"
        f"🆔 ID: `{user['user_id']}`\n"
        f"📋 Code parrainage: `{user['referral_code']}`\n"
        f"🛒 Commandes: {user['total_orders']}\n"
        f"💶 Total dépensé: {user['total_spent']:.2f}€\n"
        f"💰 Solde commissions: {user['balance']:.2f}€\n"
        f"📅 Membre depuis: {user['created_at'][:10]}"
    )

    keyboard = [[InlineKeyboardButton("🔙 Menu", callback_data="home")]]
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════
# 🔧 ADMIN COMMANDS
# ══════════════════════════════════════════════

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Panel admin dans Telegram"""
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Accès refusé.")
        return

    stats = get_stats()

    text = (
        f"🔧 **ADMIN PANEL**\n\n"
        f"👥 Utilisateurs: {stats['total_users']}\n"
        f"🛒 Commandes total: {stats['total_orders']}\n"
        f"💶 Revenue total: {stats['total_revenue']:.2f}€\n"
        f"📊 Aujourd'hui: {stats['orders_today']} commandes / {stats['revenue_today']:.2f}€\n"
        f"🎫 Tickets ouverts: {stats['pending_tickets']}\n"
        f"⭐ Note moyenne: {stats['avg_rating']['average']}/5\n\n"
        f"**Stock:**\n"
    )
    for item in stats["stock"]:
        text += f"  {item['game']}/{item['tier']}: {item['count']} ({item['status']})\n"

    keyboard = [
        [InlineKeyboardButton("📦 Recharger stock", callback_data="admin_restock")],
        [InlineKeyboardButton("✅ Valider commandes", callback_data="admin_validate")],
        [InlineKeyboardButton("🎫 Voir tickets", callback_data="admin_tickets")],
        [InlineKeyboardButton("🚫 Gérer bans", callback_data="admin_bans")],
    ]

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_restock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recharge le stock (admin)"""
    query = update.callback_query
    if query:
        await query.answer()
        if query.from_user.id not in ADMIN_IDS:
            return

    text = (
        "📦 **Recharger le stock**\n\n"
        "Envoyez les comptes au format:\n"
        "`/restock <jeu> <tier>`\n\n"
        "Puis envoyez les comptes, un par ligne:\n"
        "`email:password`\n\n"
        "**Jeux:** fortnite, gta5, lol, valorant\n"
        "**Tiers:** Selon le jeu (standard, premium, etc.)\n\n"
        "Exemple:\n"
        "`/restock fortnite premium`"
    )
    if query:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def restock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /restock pour ajouter des comptes"""
    if update.effective_user.id not in ADMIN_IDS:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /restock <jeu> <tier>\nPuis envoyez les comptes ligne par ligne.")
        return

    game = context.args[0].lower()
    tier = context.args[1].lower()

    if game not in GAMES or tier not in GAMES[game]["tiers"]:
        await update.message.reply_text("❌ Jeu ou tier invalide.")
        return

    context.user_data["restocking"] = {"game": game, "tier": tier}
    await update.message.reply_text(
        f"📦 Mode recharge: **{GAMES[game]['name']} - {tier}**\n\n"
        f"Envoyez les comptes, un par ligne (email:password).\n"
        f"Tapez /done quand terminé.",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_restock_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Traite les données de restock"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if "restocking" not in context.user_data:
        return

    lines = update.message.text.strip().split("\n")
    credentials = [line.strip() for line in lines if ":" in line or "@" in line]

    if credentials:
        game = context.user_data["restocking"]["game"]
        tier = context.user_data["restocking"]["tier"]
        count = add_accounts(game, tier, credentials, update.effective_user.id)
        await update.message.reply_text(
            f"✅ **{count} comptes ajoutés!**\n"
            f"🎮 {GAMES[game]['name']} - {tier}\n"
            f"📊 Stock actuel: {get_stock_count(game, tier)}",
            parse_mode=ParseMode.MARKDOWN
        )


async def done_restock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Termine le restock"""
    if "restocking" in context.user_data:
        del context.user_data["restocking"]
        await update.message.reply_text("✅ Recharge terminée!")


async def admin_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /deliver pour livrer manuellement une commande"""
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Usage: /deliver <order_ref>")
        return

    order_ref = context.args[0]
    order = get_order(order_ref)
    if not order:
        await update.message.reply_text("❌ Commande introuvable.")
        return

    # Livrer le compte
    account_id = order.get("account_id")
    if not account_id:
        account_id = reserve_account(order["game"], order["tier"], order["user_id"])
        if not account_id:
            await update.message.reply_text("❌ Pas de stock disponible!")
            return

    account = deliver_account(account_id, order["user_id"])
    update_order_status(order_ref, "delivered", account_id)
    update_order_payment(order_ref, order.get("payment_method", "manual"), "manual", "paid")

    # Envoyer les credentials au client
    try:
        await context.bot.send_message(
            order["user_id"],
            f"🎉 **Commande livrée!**\n\n"
            f"📋 Commande: `{order_ref}`\n"
            f"🎮 {GAMES[order['game']]['name']}\n\n"
            f"🔐 **Vos identifiants:**\n"
            f"```\n{account['credentials']}\n```\n"
            f"{'📝 ' + account['extra_info'] if account.get('extra_info') else ''}\n\n"
            f"⚠️ Changez le mot de passe immédiatement!\n"
            f"⭐ N'oubliez pas de laisser un avis!",
            parse_mode=ParseMode.MARKDOWN
        )
        await update.message.reply_text(f"✅ Commande {order_ref} livrée avec succès!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Livré en DB mais erreur Telegram: {e}")


async def admin_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /ban pour bannir un utilisateur"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /ban <user_id> <heures> [raison]")
        return
    user_id = int(context.args[0])
    hours = int(context.args[1])
    reason = " ".join(context.args[2:]) or "Ban admin"
    ban_user(user_id, reason, hours)
    await update.message.reply_text(f"🚫 User {user_id} banni pour {hours}h. Raison: {reason}")


# ══════════════════════════════════════════════
# 🔄 NAVIGATION
# ══════════════════════════════════════════════

async def navigate_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retour au menu principal via callback"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    rating = get_average_rating()
    rating_text = f"⭐ {rating['average']}/5 ({rating['count']} avis)" if rating['count'] > 0 else "🆕 Nouveau shop"

    text = (
        f"🎮 **GameVault**\n\n"
        f"{rating_text}\n"
        f"Que souhaitez-vous faire ?"
    )

    keyboard = [
        [InlineKeyboardButton("🛒 Acheter un compte", callback_data="shop")],
        [InlineKeyboardButton("📦 Mes commandes", callback_data="my_orders"),
         InlineKeyboardButton("⭐ Avis clients", callback_data="reviews")],
        [InlineKeyboardButton("🎁 Parrainage", callback_data="referral"),
         InlineKeyboardButton("❓ SAV / Support", callback_data="support")],
        [InlineKeyboardButton("ℹ️ Mon compte", callback_data="account")],
    ]

    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))


# ══════════════════════════════════════════════
# 🚀 MAIN
# ══════════════════════════════════════════════

async def periodic_cleanup(context: ContextTypes.DEFAULT_TYPE):
    """Tâches périodiques"""
    release_expired_reservations()
    AntifraudEngine.cleanup()


def main():
    """Lance le bot"""
    # Init DB
    init_database()

    # Build application
    app = Application.builder().token(BOT_TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("shop", shop_menu))
    app.add_handler(CommandHandler("orders", my_orders))
    app.add_handler(CommandHandler("referral", referral_menu))
    app.add_handler(CommandHandler("support", support_menu))
    app.add_handler(CommandHandler("reviews", show_reviews))
    app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ Action annulée.")))

    # Admin commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("restock", restock_command))
    app.add_handler(CommandHandler("done", done_restock))
    app.add_handler(CommandHandler("deliver", admin_deliver))
    app.add_handler(CommandHandler("ban", admin_ban_command))

    # Callback queries (boutons)
    app.add_handler(CallbackQueryHandler(navigate_home, pattern="^home$"))
    app.add_handler(CallbackQueryHandler(shop_menu, pattern="^shop$"))
    app.add_handler(CallbackQueryHandler(game_tiers, pattern="^game_"))
    app.add_handler(CallbackQueryHandler(out_of_stock, pattern="^oos_"))
    app.add_handler(CallbackQueryHandler(select_delivery, pattern="^tier_"))
    app.add_handler(CallbackQueryHandler(select_payment, pattern="^delivery_"))
    app.add_handler(CallbackQueryHandler(process_payment, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(confirm_paid, pattern="^confirm_paid_"))
    app.add_handler(CallbackQueryHandler(cancel_order, pattern="^cancel_order_"))
    app.add_handler(CallbackQueryHandler(my_orders, pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(show_reviews, pattern="^reviews$"))
    app.add_handler(CallbackQueryHandler(ask_review, pattern="^review_"))
    app.add_handler(CallbackQueryHandler(save_rating, pattern="^rate_"))
    app.add_handler(CallbackQueryHandler(referral_menu, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(support_menu, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(new_ticket, pattern="^new_ticket$"))
    app.add_handler(CallbackQueryHandler(account_info, pattern="^account$"))
    app.add_handler(CallbackQueryHandler(admin_restock, pattern="^admin_restock$"))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticket_message))

    # Periodic tasks (every 5 minutes)
    app.job_queue.run_repeating(periodic_cleanup, interval=300, first=60)

    # Run
    logger.info("🎮 GameVault Bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
