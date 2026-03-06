# 🎮 GameVault Bot

Bot Telegram complet de vente de comptes gaming avec panel admin, multi-paiement, anti-fraude et système de parrainage.

## 🏗️ Architecture

```
gamebot/
├── bot/main.py          # Bot Telegram principal
├── admin/panel.py       # Panel admin web (Flask)
├── config/settings.py   # Configuration centralisée
├── database/db.py       # SQLite + toutes les opérations DB
├── payments/handlers.py # Stripe, PayPal, Crypto
├── utils/antifraud.py   # Moteur anti-fraude
├── .env.example         # Template de configuration
├── requirements.txt     # Dépendances Python
└── run.sh              # Script de lancement
```

## ⚡ Fonctionnalités

### Client (Telegram)
- 🛒 Catalogue par jeu (Fortnite, GTA V, LoL, Valorant)
- 🏷️ Tiers multiples (Standard, Premium, OG/Modded)
- 🚚 3 modes de livraison (Standard 24h, Express 4h, Instant 15min)
- 💳 Paiement: Carte (Stripe), PayPal, Crypto (BTC/ETH/USDT)
- 🎁 Système de parrainage avec commissions
- ⭐ Avis clients
- 📞 SAV avec tickets
- 📦 Suivi de commandes

### Admin
- 📊 Dashboard web avec stats en temps réel
- 📦 Rechargement de stock (web + Telegram)
- ✅ Validation et livraison de commandes
- 🚫 Gestion des bans
- 🎫 Gestion des tickets SAV
- 📡 Webhooks Stripe & Crypto

### Sécurité
- 🛡️ Anti-fraude avec scoring de risque
- ⏱️ Rate limiting (par heure et par jour)
- 🔒 Auto-ban après échecs de paiement répétés
- 📝 Logs de sécurité complets
- 🔐 Panel admin protégé par mot de passe

## 🚀 Installation

### 1. Prérequis
- Python 3.10+
- Un serveur (VPS recommandé)

### 2. Configuration

```bash
# Cloner/copier le projet
cd gamebot

# Copier la config
cp .env.example .env

# Éditer .env avec vos clés
nano .env
```

### 3. Créer le bot Telegram

1. Ouvrir @BotFather sur Telegram
2. `/newbot` → suivre les instructions
3. Copier le token dans `.env`
4. `/setcommands` puis envoyer:
```
start - Menu principal
shop - Voir les comptes
orders - Mes commandes
referral - Parrainage
support - SAV
reviews - Avis clients
help - Aide
```

### 4. Configurer les paiements

**Stripe:**
1. Créer un compte sur stripe.com
2. Récupérer les clés API dans Dashboard > Developers
3. Configurer un webhook vers `https://votre-serveur/webhook/stripe`

**PayPal:**
1. Créer une app sur developer.paypal.com
2. Récupérer Client ID et Secret

**Crypto (NOWPayments recommandé):**
1. Créer un compte sur nowpayments.io
2. Récupérer l'API Key
3. Configurer l'IPN callback vers `https://votre-serveur/webhook/crypto`

### 5. Lancer

```bash
chmod +x run.sh

# Lancer tout
./run.sh both

# Ou séparément
./run.sh bot     # Bot uniquement
./run.sh admin   # Panel admin uniquement
```

## 🔧 Commandes Admin (Telegram)

| Commande | Description |
|----------|-------------|
| `/admin` | Panel admin avec stats |
| `/restock fortnite premium` | Recharger le stock |
| `/deliver GV-xxxxx` | Livrer une commande |
| `/ban 123456 24 raison` | Bannir un user |
| `/done` | Terminer le restock |

## 🕵️ Anonymat sur Telegram

### Recommandations
1. **Nouveau numéro:** Utilisez un numéro VoIP ou une SIM prépayée anonyme
2. **Paramètres Telegram:**
   - Settings > Privacy: masquer numéro, photo, bio, last seen
   - Activer la vérification en deux étapes
   - Utiliser un username qui ne révèle rien de personnel
3. **Compte admin séparé:** Ne pas utiliser votre compte perso comme admin
4. **VPN/Tor:** Toujours se connecter via VPN
5. **Serveur:** Utiliser un VPS payé en crypto (Njalla, 1984hosting, etc.)

## 📦 Gestion du stock

### Via Telegram (admin)
```
/restock fortnite premium
email1@test.com:password1
email2@test.com:password2
/done
```

### Via le panel web
1. Connectez-vous à `http://votre-serveur:8080`
2. Section "Recharger le stock"
3. Sélectionner jeu + tier
4. Coller les comptes

### Rupture de stock
Quand un produit est en rupture:
- Le bouton affiche ❌ RUPTURE
- Un message invite à contacter le SAV
- Les demandes exceptionnelles sont plus chères

## 💰 Tarification

Les prix sont configurés dans `config/settings.py`:
- **Standard:** prix de base
- **Express (+50%):** livraison 1-4h
- **Instant (+150%):** livraison 15min

Le système de parrainage donne:
- **Filleul:** -10% sur la première commande
- **Parrain:** 5% de commission

---

**⚠️ Disclaimer:** Ce bot est fourni à titre éducatif. Assurez-vous de respecter les conditions d'utilisation des plateformes de jeux et les lois en vigueur dans votre juridiction.
