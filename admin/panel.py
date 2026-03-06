"""
🌐 GameVault Bot - Admin Web Panel
Dashboard web pour gérer le bot, le stock, les commandes
"""
import os
import sys
import json
import hashlib
import secrets
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, render_template_string, redirect, session, flash
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import ADMIN_PANEL_PORT, ADMIN_PANEL_SECRET, GAMES
from database.db import (
    init_database, get_stats, get_all_stock, add_accounts,
    get_stock_count, get_reviews, get_order, update_order_status,
    get_average_rating
)

app = Flask(__name__)
app.secret_key = ADMIN_PANEL_SECRET or secrets.token_hex(32)


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
                <label>Mot de passe admin</label>
                <input type="password" name="password" placeholder="••••••••" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%">Connexion</button>
        </form>
    </div>
    {% else %}
    <div class="header">
        <h1>🎮 GameVault Admin</h1>
        <div>
            <span style="color:var(--text-dim); margin-right:10px;">{{ now }}</span>
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
    if session.get("admin_logged_in"):
        return dashboard()
    return render_template_string(ADMIN_PANEL_HTML, logged_in=False)


@app.route("/login", methods=["POST"])
def login():
    password = request.form.get("password", "")
    if hashlib.sha256(password.encode()).hexdigest() == hashlib.sha256(ADMIN_PANEL_SECRET.encode()).hexdigest():
        session["admin_logged_in"] = True
        return redirect("/")
    flash("Mot de passe incorrect", "error")
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
        messages=messages
    )


@app.route("/restock", methods=["POST"])
@login_required
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
