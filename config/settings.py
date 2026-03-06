"""
🎮 GameVault Bot - Configuration
Toutes les variables d'environnement et paramètres
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════
# 🤖 TELEGRAM BOT
# ══════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@GameVault_SAV")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")  # Canal de logs

# ══════════════════════════════════════════════
# 💰 PAIEMENTS
# ══════════════════════════════════════════════
# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# PayPal
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox / live

# Crypto - CoinGate / NOWPayments / Plisio
CRYPTO_API_KEY = os.getenv("CRYPTO_API_KEY", "")
CRYPTO_PROVIDER = os.getenv("CRYPTO_PROVIDER", "nowpayments")  # nowpayments / plisio / coingate
CRYPTO_IPN_SECRET = os.getenv("CRYPTO_IPN_SECRET", "")

# ══════════════════════════════════════════════
# 🎮 PRODUITS & PRIX
# ══════════════════════════════════════════════
GAMES = {
    "fortnite": {
        "name": "🎯 Fortnite",
        "emoji": "🎯",
        "tiers": {
            "standard": {"name": "Standard", "price": 5.00, "description": "Compte avec skins basiques"},
            "premium": {"name": "Premium", "price": 15.00, "description": "Compte 50+ skins"},
            "og": {"name": "OG Rare", "price": 35.00, "description": "Compte avec skins OG rares"},
        }
    },
    "gta5": {
        "name": "🚗 GTA V / Rockstar",
        "emoji": "🚗",
        "tiers": {
            "standard": {"name": "Standard", "price": 8.00, "description": "Compte Online niveau 100+"},
            "premium": {"name": "Premium", "price": 20.00, "description": "Compte Online 200+ all unlocked"},
            "modded": {"name": "Modded", "price": 40.00, "description": "Compte full modded + cash"},
        }
    },
    "lol": {
        "name": "⚔️ League of Legends",
        "emoji": "⚔️",
        "tiers": {
            "smurf": {"name": "Smurf Lvl 30", "price": 4.00, "description": "Unranked niveau 30"},
            "ranked": {"name": "Ranked", "price": 12.00, "description": "Gold/Plat avec champions"},
            "premium": {"name": "Premium", "price": 30.00, "description": "Diamond+ 100+ skins"},
        }
    },
    "valorant": {
        "name": "🔫 Valorant",
        "emoji": "🔫",
        "tiers": {
            "standard": {"name": "Standard", "price": 6.00, "description": "Compte avec agents débloqués"},
            "ranked": {"name": "Ranked", "price": 15.00, "description": "Compte Gold+ avec skins"},
            "premium": {"name": "Premium", "price": 35.00, "description": "Immortal+ skins rares"},
        }
    },
}

# ══════════════════════════════════════════════
# ⏰ LIVRAISON
# ══════════════════════════════════════════════
DELIVERY_MODES = {
    "standard": {
        "name": "📦 Standard (1-24h)",
        "multiplier": 1.0,
        "max_hours": 24,
        "description": "Livraison sous 1 à 24 heures"
    },
    "express": {
        "name": "⚡ Express (1-4h)",
        "multiplier": 1.5,  # +50%
        "max_hours": 4,
        "description": "Livraison express sous 4 heures"
    },
    "instant": {
        "name": "🚀 Instant (15 min)",
        "multiplier": 2.5,  # +150%
        "max_hours": 0.25,
        "description": "Livraison immédiate sous 15 minutes"
    },
}

# ══════════════════════════════════════════════
# 🎁 PARRAINAGE
# ══════════════════════════════════════════════
REFERRAL_REWARD_PERCENT = 10  # 10% de réduction pour le filleul
REFERRAL_COMMISSION_PERCENT = 5  # 5% de commission pour le parrain
MIN_WITHDRAWAL = 10.00  # Minimum pour retirer les commissions

# ══════════════════════════════════════════════
# 🛡️ ANTI-FRAUDE
# ══════════════════════════════════════════════
MAX_ORDERS_PER_HOUR = 5
MAX_ORDERS_PER_DAY = 15
MAX_FAILED_PAYMENTS = 3  # Ban temporaire après X échecs
BAN_DURATION_HOURS = 24
SUSPICIOUS_PATTERNS = ["multiple_accounts", "rapid_orders", "payment_failures"]

# ══════════════════════════════════════════════
# 🗄️ DATABASE
# ══════════════════════════════════════════════
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/gamevault.db")
BACKUP_INTERVAL_HOURS = 6

# ══════════════════════════════════════════════
# 🌐 ADMIN PANEL
# ══════════════════════════════════════════════
ADMIN_PANEL_PORT = int(os.getenv("ADMIN_PANEL_PORT", "8080"))
ADMIN_PANEL_SECRET = os.getenv("ADMIN_PANEL_SECRET", "change-me-in-production")
