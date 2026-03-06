"""
🌐 GameVault Bot - Admin Web Panel
Dashboard web pour gérer le bot, le stock, les commandes
"""
import os
import sys
import json
import hashlib
import secrets
import base64
import hmac
import struct
import time
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, render_template_string, redirect, session, flash
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import ADMIN_PANEL_PORT, ADMIN_PANEL_SECRET, GAMES
from database.db import (
    init_database, get_stats, get_all_stock, add_accounts,
    get_stock_count, get_reviews, get_order, update_order_status,
    get_average_rating, emergency_purge_all_data,
    get_admin_by_username, list_admins, create_admin, update_admin_last_login, disable_admin
)

app = Flask(__name__)
app.secret_key = ADMIN_PANEL_SECRET or secrets.token_hex(32)

VALID_ROLES = {"owner", "manager", "support"}


def hash_password(password: str) -> str:
    """Hash mot de passe admin (PBKDF2-SHA256)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe hashé."""
    try:
        salt, expected = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def generate_mfa_secret() -> str:
    """Génère un secret MFA TOTP (base32)."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode().rstrip("=")


def _totp(secret: str, for_time: int, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    counter = int(for_time // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret: str, otp_code: str, window: int = 1) -> bool:
    """Valide un OTP TOTP avec petite fenêtre de tolérance."""
    if not otp_code or not otp_code.isdigit():
        return False
    now = int(time.time())
    for w in range(-window, window + 1):
        if hmac.compare_digest(_totp(secret, now + w * 30), otp_code):
            return True
    return False


def require_role(*roles):
    """Décorateur de rôle pour le panel web."""
    allowed = set(roles)

    def _decorator(f):
        @wraps(f)
        def _wrapped(*args, **kwargs):
            role = session.get("admin_role")
            if role not in allowed:
                flash("Permissions insuffisantes.", "error")
                return redirect("/")
            return f(*args, **kwargs)
        return _wrapped
    return _decorator


def ensure_admin_bootstrap():
    """Conserve le point d'extension bootstrap (désormais piloté par /setup-owner)."""
    return None


def build_otpauth_uri(username: str, secret: str) -> str:
    """Construit une URI otpauth pour apps Authenticator."""
    account = f"GameVault:{username}"
    issuer = "GameVault"
    return f"otpauth://totp/{account}?secret={secret}&issuer={issuer}&digits=6&period=30"


OWNER_SETUP_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Setup Owner - GameVault</title>
    <style>
        body { font-family: Arial, sans-serif; background:#0a0a0f; color:#dfe6e9; }
        .box { max-width:560px; margin:40px auto; background:#12121a; padding:24px; border-radius:12px; border:1px solid #2d3436; }
        input { width:100%; padding:10px; margin:8px 0 14px; background:#1a1a25; color:#fff; border:1px solid #2d3436; border-radius:8px; }
        button { padding:10px 16px; border:none; border-radius:8px; background:#6c5ce7; color:white; font-weight:bold; cursor:pointer; }
        .flash{padding:10px; border-radius:8px; margin-bottom:12px;}
        .error{background:#3b1f1f;color:#ff9f9f;} .success{background:#123126;color:#9ef0c5;}
        code{word-break:break-all;}
    </style>
</head>
<body>
<div class="box">
    <h2>🛡️ Première configuration owner + MFA</h2>
    {% for msg in messages %}<div class="flash {{ msg.type }}">{{ msg.text }}</div>{% endfor %}
    <p>1) Ajoute ce secret dans Google Authenticator / Aegis / 2FAS.</p>
    <p><strong>Secret MFA:</strong> <code>{{ setup_secret }}</code></p>
    <p><strong>URI Authenticator:</strong> <code>{{ otpauth_uri }}</code></p>
    <form method="POST" action="/setup-owner">
        <label>Username owner</label>
        <input type="text" name="username" value="owner" required>
        <label>Mot de passe (10+ chars)</label>
        <input type="password" name="password" required>
        <label>Confirmer mot de passe</label>
        <input type="password" name="password_confirm" required>
        <label>Code MFA (6 chiffres)</label>
        <input type="text" name="otp" maxlength="6" required>
        <button type="submit">Créer le compte owner</button>
    </form>
</div>
</body>
</html>
"""


ADMIN_PANEL_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GameVault Admin</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg: #0a0a0f; --surface: #12121a; --surface2: #1a1a25;
            --accent: #6c5ce7; --accent2: #a29bfe; --success: #00b894;
            --danger: #e17055; --warning: #fdcb6e; --text: #dfe6e9;
            --text-dim: #636e72; --border: #2d3436;
        }
        body { font-family: 'SF Mono', 'Fira Code', monospace; background: var(--bg); color: var(--text); min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid var(--border); margin-bottom: 30px; }
        .header h1 { font-size: 24px; background: linear-gradient(135deg, var(--accent), var(--accent2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }
        .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
        .stat-card .label { font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
        .stat-card .value { font-size: 28px; font-weight: bold; margin-top: 8px; }
        .stat-card .value.revenue { color: var(--success); }
        .stat-card .value.orders { color: var(--accent2); }
        .stat-card .value.tickets { color: var(--warning); }
        .section { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 20px; }
        .section h2 { font-size: 18px; margin-bottom: 16px; color: var(--accent2); }
        .stock-table { width: 100%; border-collapse: collapse; }
        .stock-table th, .stock-table td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
        .stock-table th { color: var(--text-dim); font-size: 12px; text-transform: uppercase; }
        .badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
        .badge.green { background: rgba(0,184,148,0.15); color: var(--success); }
        .badge.yellow { background: rgba(253,203,110,0.15); color: var(--warning); }
        .badge.red { background: rgba(225,112,85,0.15); color: var(--danger); }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 13px; color: var(--text-dim); margin-bottom: 6px; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%; padding: 10px 14px; background: var(--surface2); border: 1px solid var(--border);
            border-radius: 8px; color: var(--text); font-family: inherit; font-size: 14px;
        }
        .form-group textarea { min-height: 120px; resize: vertical; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; font-family: inherit; font-size: 14px; cursor: pointer; font-weight: bold; transition: all 0.2s; }
        .btn-primary { background: var(--accent); color: white; }
        .btn-primary:hover { background: var(--accent2); }
        .btn-success { background: var(--success); color: white; }
        .btn-danger { background: var(--danger); color: white; }
        .flash { padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 14px; }
        .flash.success { background: rgba(0,184,148,0.15); color: var(--success); border: 1px solid var(--success); }
        .flash.error { background: rgba(225,112,85,0.15); color: var(--danger); border: 1px solid var(--danger); }
        .login-box { max-width: 400px; margin: 100px auto; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 8px 16px; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; cursor: pointer; color: var(--text-dim); text-decoration: none; }
        .tab.active { background: var(--accent); color: white; border-color: var(--accent); }
    </style>
</head>
<body>
<div class="container">
    {% if not logged_in %}
    <div class="login-box section">
        <h2>🔐 GameVault Admin</h2>
        <form method="POST" action="/login">
            <div class="form-group">
                <label>Username admin</label>
                <input type="text" name="username" placeholder="owner" required>
            </div>
            <div class="form-group">
                <label>Mot de passe admin</label>
                <input type="password" name="password" placeholder="••••••••" required>
            </div>
            <div class="form-group">
                <label>Code MFA (TOTP 6 chiffres)</label>
                <input type="text" name="otp" placeholder="123456" maxlength="6" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%">Connexion</button>
        </form>
    </div>
    {% else %}
    <div class="header">
        <h1>🎮 GameVault Admin</h1>
        <div>
            <span style="color:var(--text-dim); margin-right:10px;">{{ now }} | {{ admin_username }} ({{ admin_role }})</span>
            <a href="/logout" class="btn btn-danger" style="font-size:12px;">Déconnexion</a>
        </div>
    </div>

    {% for msg in messages %}
    <div class="flash {{ msg.type }}">{{ msg.text }}</div>
    {% endfor %}

    <!-- Stats -->
    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Revenue Total</div>
            <div class="value revenue">{{ "%.2f"|format(stats.total_revenue) }}€</div>
        </div>
        <div class="stat-card">
            <div class="label">Commandes</div>
            <div class="value orders">{{ stats.total_orders }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Aujourd'hui</div>
            <div class="value">{{ stats.orders_today }} / {{ "%.2f"|format(stats.revenue_today) }}€</div>
        </div>
        <div class="stat-card">
            <div class="label">Utilisateurs</div>
            <div class="value">{{ stats.total_users }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Tickets ouverts</div>
            <div class="value tickets">{{ stats.pending_tickets }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Note moyenne</div>
            <div class="value">⭐ {{ stats.avg_rating.average }}/5</div>
        </div>
    </div>

    <!-- Stock -->
    <div class="section">
        <h2>📦 Stock</h2>
        <table class="stock-table">
            <tr><th>Jeu</th><th>Tier</th><th>Disponible</th><th>Statut</th></tr>
            {% for game_id, game in games.items() %}
                {% for tier_id, tier in game.tiers.items() %}
                <tr>
                    <td>{{ game.emoji }} {{ game.name }}</td>
                    <td>{{ tier.name }}</td>
                    <td>
                        {% set count = stock_counts.get(game_id ~ '_' ~ tier_id, 0) %}
                        {{ count }}
                    </td>
                    <td>
                        {% set count = stock_counts.get(game_id ~ '_' ~ tier_id, 0) %}
                        {% if count > 5 %}
                        <span class="badge green">En stock</span>
                        {% elif count > 0 %}
                        <span class="badge yellow">Stock faible</span>
                        {% else %}
                        <span class="badge red">Rupture</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            {% endfor %}
        </table>
    </div>

    <!-- Recharger stock -->
    <div class="section">
        <h2>📦 Recharger le stock</h2>
        <form method="POST" action="/restock">
            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
                <div class="form-group">
                    <label>Jeu</label>
                    <select name="game">
                        {% for game_id, game in games.items() %}
                        <option value="{{ game_id }}">{{ game.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label>Tier</label>
                    <select name="tier" id="tier-select">
                        <option value="standard">Standard</option>
                        <option value="premium">Premium</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label>Comptes (un par ligne, format email:password)</label>
                <textarea name="accounts" placeholder="user1@email.com:password123&#10;user2@email.com:password456"></textarea>
            </div>
            <button type="submit" class="btn btn-success">📦 Ajouter au stock</button>
        </form>
    </div>


    {% if admin_role == 'owner' %}
    <div class="section">
        <h2>👤 Gestion admins</h2>
        <form method="POST" action="/admins/create" style="margin-bottom:16px;">
            <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap:12px;">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" name="username" placeholder="newadmin" required>
                </div>
                <div class="form-group">
                    <label>Rôle</label>
                    <select name="role">
                        <option value="owner">owner</option>
                        <option value="manager">manager</option>
                        <option value="support">support</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Mot de passe</label>
                    <input type="password" name="password" placeholder="motdepasse" required>
                </div>
            </div>
            <button type="submit" class="btn btn-primary">➕ Créer admin</button>
        </form>
        <table class="stock-table">
            <tr><th>ID</th><th>Username</th><th>Rôle</th><th>Statut</th><th>Dernier login</th><th>Action</th></tr>
            {% for adm in admins %}
            <tr>
                <td>{{ adm.id }}</td>
                <td>{{ adm.username }}</td>
                <td>{{ adm.role }}</td>
                <td>{% if adm.is_active %}<span class="badge green">Actif</span>{% else %}<span class="badge red">Désactivé</span>{% endif %}</td>
                <td>{{ adm.last_login_at or '-' }}</td>
                <td>
                    {% if adm.is_active and adm.id != admin_id %}
                    <form method="POST" action="/admins/{{ adm.id }}/disable">
                        <button type="submit" class="btn btn-danger" style="font-size:12px;">Désactiver</button>
                    </form>
                    {% else %}-{% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}


    {% if admin_role == 'owner' %}
    <!-- Mode urgence -->
    <div class="section" style="border-color: var(--danger);">
        <h2>🚨 Mode urgence</h2>
        <p style="color:var(--text-dim); margin-bottom:12px;">Supprime toute la base (users, commandes, stock, tickets, logs). Action irréversible.</p>
        <form method="POST" action="/emergency-wipe">
            <div class="form-group">
                <label>Confirmez en tapant <strong>SUPPRIMER TOUT</strong></label>
                <input type="text" name="confirm_text" placeholder="SUPPRIMER TOUT" required>
            </div>
            <button type="submit" class="btn btn-danger">💥 Tout supprimer maintenant</button>
        </form>
    </div>
    {% endif %}
    {% endif %}
</div>
</body>
</html>
"""


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect("/")
        return f(*args, **kwargs)
    return decorated


@app.route("/", methods=["GET"])
def index():
    if not list_admins():
        return redirect("/setup-owner")
    if session.get("admin_logged_in"):
        return dashboard()
    return render_template_string(ADMIN_PANEL_HTML, logged_in=False)




@app.route("/setup-owner", methods=["GET"])
def setup_owner_get():
    if list_admins():
        return redirect("/")

    setup_secret = session.get("setup_owner_secret")
    if not setup_secret:
        env_secret = os.getenv("ADMIN_BOOTSTRAP_MFA_SECRET", "").strip().upper()
        setup_secret = env_secret if env_secret else generate_mfa_secret()
        session["setup_owner_secret"] = setup_secret

    setup_username = os.getenv("ADMIN_BOOTSTRAP_USERNAME", "owner").strip().lower() or "owner"
    messages = [{"type": m[0], "text": m[1]} for m in (session.pop("_flashes", None) or [])]
    return render_template_string(
        OWNER_SETUP_HTML,
        setup_secret=setup_secret,
        otpauth_uri=build_otpauth_uri(setup_username, setup_secret),
        messages=messages,
    )


@app.route("/setup-owner", methods=["POST"])
def setup_owner_post():
    if list_admins():
        return redirect("/")

    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")
    otp = request.form.get("otp", "").strip()
    setup_secret = session.get("setup_owner_secret", "")

    if not username:
        flash("Username requis.", "error")
        return redirect("/setup-owner")
    if len(password) < 10:
        flash("Mot de passe trop court (10+ chars).", "error")
        return redirect("/setup-owner")
    if password != password_confirm:
        flash("La confirmation mot de passe ne correspond pas.", "error")
        return redirect("/setup-owner")
    if not setup_secret:
        flash("Secret MFA manquant, rechargez la page setup.", "error")
        return redirect("/setup-owner")
    if not verify_totp(setup_secret, otp):
        flash("Code MFA invalide.", "error")
        return redirect("/setup-owner")

    create_admin(username, hash_password(password), "owner", setup_secret)
    session.pop("setup_owner_secret", None)
    flash("✅ Owner créé. Connectez-vous.", "success")
    return redirect("/")


@app.route("/login", methods=["POST"])
def login():
    if not list_admins():
        flash("Aucun admin configuré. Lancez d'abord la configuration owner.", "error")
        return redirect("/setup-owner")

    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    otp = request.form.get("otp", "").strip()

    admin = get_admin_by_username(username)
    if not admin or not admin.get("is_active"):
        flash("Identifiants invalides.", "error")
        return redirect("/")

    if not verify_password(password, admin["password_hash"]):
        flash("Identifiants invalides.", "error")
        return redirect("/")

    if not verify_totp(admin["mfa_secret"], otp):
        flash("Code MFA invalide.", "error")
        return redirect("/")

    session["admin_logged_in"] = True
    session["admin_id"] = admin["id"]
    session["admin_username"] = admin["username"]
    session["admin_role"] = admin["role"]
    update_admin_last_login(admin["id"])
    return redirect("/")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
@login_required
def dashboard():
    stats = get_stats()
    stock_counts = {}
    for game_id in GAMES:
        for tier_id in GAMES[game_id]["tiers"]:
            stock_counts[f"{game_id}_{tier_id}"] = get_stock_count(game_id, tier_id)

    messages = []
    for msg in (session.pop("_flashes", None) or []):
        messages.append({"type": msg[0], "text": msg[1]})

    return render_template_string(
        ADMIN_PANEL_HTML,
        logged_in=True,
        stats=stats,
        games=GAMES,
        stock_counts=stock_counts,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        messages=messages,
        admin_username=session.get("admin_username", "?"),
        admin_role=session.get("admin_role", "support"),
        admin_id=session.get("admin_id"),
        admins=list_admins()
    )


@app.route("/restock", methods=["POST"])
@login_required
@require_role("owner", "manager")
def restock():
    game = request.form.get("game")
    tier = request.form.get("tier")
    accounts_text = request.form.get("accounts", "")

    if not game or not tier or not accounts_text.strip():
        flash("Tous les champs sont requis", "error")
        return redirect("/")

    lines = [l.strip() for l in accounts_text.strip().split("\n") if l.strip()]
    count = add_accounts(game, tier, lines, 0)
    flash(f"✅ {count} comptes ajoutés pour {game}/{tier}!", "success")
    return redirect("/")


@app.route("/emergency-wipe", methods=["POST"])
@login_required
@require_role("owner")
def emergency_wipe():
    confirm_text = request.form.get("confirm_text", "").strip().upper()
    if confirm_text != "SUPPRIMER TOUT":
        flash("Confirmation invalide. Tapez exactement SUPPRIMER TOUT.", "error")
        return redirect("/")

    emergency_purge_all_data()
    flash("🚨 Purge d'urgence exécutée: base totalement vidée.", "success")
    return redirect("/")


@app.route("/admins/create", methods=["POST"])
@login_required
@require_role("owner")
def admins_create():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "manager").strip().lower()

    if not username or len(password) < 10 or role not in VALID_ROLES:
        flash("Paramètres admin invalides (password min 10 chars).", "error")
        return redirect("/")

    if get_admin_by_username(username):
        flash("Username admin déjà utilisé.", "error")
        return redirect("/")

    secret = generate_mfa_secret()
    create_admin(username, hash_password(password), role, secret)
    flash(f"✅ Admin {username} créé (role={role}). Secret MFA: {secret}", "success")
    return redirect("/")


@app.route("/admins/<int:admin_id>/disable", methods=["POST"])
@login_required
@require_role("owner")
def admins_disable(admin_id):
    if session.get("admin_id") == admin_id:
        flash("Impossible de se désactiver soi-même.", "error")
        return redirect("/")

    disable_admin(admin_id)
    flash(f"✅ Admin #{admin_id} désactivé.", "success")
    return redirect("/")


# API endpoints for external integrations
@app.route("/api/stats", methods=["GET"])
@login_required
def api_stats():
    return jsonify(get_stats())


@app.route("/api/stock", methods=["GET"])
@login_required
def api_stock():
    result = {}
    for game_id in GAMES:
        result[game_id] = {}
        for tier_id in GAMES[game_id]["tiers"]:
            result[game_id][tier_id] = get_stock_count(game_id, tier_id)
    return jsonify(result)


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Webhook Stripe pour confirmer les paiements"""
    payload = request.data
    sig = request.headers.get("Stripe-Signature", "")
    # En production: vérifier la signature avec stripe.Webhook.construct_event
    try:
        event = json.loads(payload)
        if event["type"] == "checkout.session.completed":
            order_ref = event["data"]["object"]["metadata"].get("order_ref")
            if order_ref:
                from database.db import update_order_payment
                update_order_payment(order_ref, "stripe", event["data"]["object"]["id"], "paid")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/webhook/crypto", methods=["POST"])
def crypto_webhook():
    """Webhook pour les paiements crypto"""
    data = request.json or request.form.to_dict()
    # Vérifier IPN
    order_ref = data.get("order_id") or data.get("order_number")
    status = data.get("payment_status") or data.get("status")
    if order_ref and status in ["finished", "confirmed", "completed"]:
        from database.db import update_order_payment
        update_order_payment(order_ref, "crypto", data.get("payment_id", ""), "paid")
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    init_database()
    app.run(host="0.0.0.0", port=ADMIN_PANEL_PORT, debug=False)
