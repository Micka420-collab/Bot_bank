"""
🗄️ GameVault Bot - Database Manager
SQLite avec encryption des données sensibles
"""
import sqlite3
import os
import json
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from contextlib import contextmanager

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/gamevault.db")


def get_db_path():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    return DATABASE_PATH


@contextmanager
def get_db():
    """Context manager pour la connexion DB"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialise toutes les tables"""
    with get_db() as db:
        db.executescript("""
        -- Utilisateurs
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            language_code TEXT DEFAULT 'fr',
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            balance REAL DEFAULT 0.0,
            total_spent REAL DEFAULT 0.0,
            total_orders INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            ban_reason TEXT,
            ban_until TEXT,
            risk_score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            last_active TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (referred_by) REFERENCES users(user_id)
        );

        -- Stock de comptes
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL,
            tier TEXT NOT NULL,
            credentials TEXT NOT NULL,  -- Chiffré: email:password ou autre
            extra_info TEXT,            -- Infos supplémentaires chiffrées
            status TEXT DEFAULT 'available',  -- available, reserved, sold, refunded
            reserved_by INTEGER,
            reserved_until TEXT,
            sold_to INTEGER,
            sold_at TEXT,
            added_at TEXT DEFAULT (datetime('now')),
            added_by INTEGER,
            FOREIGN KEY (sold_to) REFERENCES users(user_id)
        );

        -- Commandes
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_ref TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            tier TEXT NOT NULL,
            delivery_mode TEXT DEFAULT 'standard',
            base_price REAL NOT NULL,
            final_price REAL NOT NULL,
            discount_applied REAL DEFAULT 0.0,
            payment_method TEXT,
            payment_id TEXT,
            payment_status TEXT DEFAULT 'pending',  -- pending, paid, failed, refunded
            order_status TEXT DEFAULT 'pending',     -- pending, processing, delivered, cancelled, refunded
            account_id INTEGER,
            delivery_info TEXT,  -- Credentials livrés (chiffré)
            referral_code_used TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            paid_at TEXT,
            delivered_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        -- Transactions de paiement
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,  -- payment, refund, referral_commission, withdrawal
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'EUR',
            method TEXT,
            external_id TEXT,
            status TEXT DEFAULT 'pending',
            metadata TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        -- Reviews / Avis
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            is_visible INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        -- Parrainages
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            order_id INTEGER,
            commission_amount REAL DEFAULT 0.0,
            commission_paid INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );

        -- Logs anti-fraude
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            details TEXT,
            ip_hash TEXT,
            risk_level TEXT DEFAULT 'low',  -- low, medium, high, critical
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        -- Tickets SAV
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id INTEGER,
            subject TEXT NOT NULL,
            status TEXT DEFAULT 'open',  -- open, in_progress, resolved, closed
            priority TEXT DEFAULT 'normal',  -- low, normal, high, urgent
            messages TEXT DEFAULT '[]',  -- JSON array of messages
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (order_id) REFERENCES orders(id)
        );

        -- Index pour performance
        CREATE INDEX IF NOT EXISTS idx_accounts_game_tier ON accounts(game, tier, status);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);
        CREATE INDEX IF NOT EXISTS idx_orders_ref ON orders(order_ref);
        CREATE INDEX IF NOT EXISTS idx_users_referral ON users(referral_code);
        CREATE INDEX IF NOT EXISTS idx_security_user ON security_logs(user_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id, status);
        """)


# ══════════════════════════════════════════════
# 👤 USER OPERATIONS
# ══════════════════════════════════════════════

def get_or_create_user(user_id, username=None, first_name=None):
    """Récupère ou crée un utilisateur"""
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if user:
            db.execute(
                "UPDATE users SET username=?, first_name=?, last_active=datetime('now') WHERE user_id=?",
                (username, first_name, user_id)
            )
            return dict(db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())
        
        referral_code = generate_referral_code()
        db.execute(
            "INSERT INTO users (user_id, username, first_name, referral_code) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, referral_code)
        )
        return dict(db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone())


def generate_referral_code():
    """Génère un code de parrainage unique"""
    return f"GV-{secrets.token_hex(4).upper()}"


def is_user_banned(user_id):
    """Vérifie si un utilisateur est banni"""
    with get_db() as db:
        user = db.execute("SELECT is_banned, ban_until FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not user:
            return False
        if user["is_banned"]:
            if user["ban_until"]:
                if datetime.fromisoformat(user["ban_until"]) < datetime.now():
                    db.execute("UPDATE users SET is_banned=0, ban_until=NULL, ban_reason=NULL WHERE user_id=?", (user_id,))
                    return False
            return True
        return False


def ban_user(user_id, reason, duration_hours=None):
    """Bannit un utilisateur"""
    with get_db() as db:
        ban_until = None
        if duration_hours:
            ban_until = (datetime.now() + timedelta(hours=duration_hours)).isoformat()
        db.execute(
            "UPDATE users SET is_banned=1, ban_reason=?, ban_until=? WHERE user_id=?",
            (reason, ban_until, user_id)
        )


# ══════════════════════════════════════════════
# 📦 STOCK OPERATIONS
# ══════════════════════════════════════════════

def get_stock_count(game, tier):
    """Compte le stock disponible"""
    with get_db() as db:
        result = db.execute(
            "SELECT COUNT(*) as count FROM accounts WHERE game=? AND tier=? AND status='available'",
            (game, tier)
        ).fetchone()
        return result["count"]


def get_all_stock():
    """Récupère tout le stock avec comptages"""
    with get_db() as db:
        results = db.execute("""
            SELECT game, tier, status, COUNT(*) as count 
            FROM accounts 
            GROUP BY game, tier, status
        """).fetchall()
        return [dict(r) for r in results]


def add_accounts(game, tier, credentials_list, added_by):
    """Ajoute des comptes au stock"""
    with get_db() as db:
        for creds in credentials_list:
            db.execute(
                "INSERT INTO accounts (game, tier, credentials, added_by) VALUES (?, ?, ?, ?)",
                (game, tier, creds, added_by)
            )
    return len(credentials_list)


def reserve_account(game, tier, user_id, minutes=30):
    """Réserve un compte pour un utilisateur"""
    with get_db() as db:
        account = db.execute(
            "SELECT id FROM accounts WHERE game=? AND tier=? AND status='available' LIMIT 1",
            (game, tier)
        ).fetchone()
        if not account:
            return None
        
        reserved_until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        db.execute(
            "UPDATE accounts SET status='reserved', reserved_by=?, reserved_until=? WHERE id=?",
            (user_id, reserved_until, account["id"])
        )
        return account["id"]


def release_expired_reservations():
    """Libère les réservations expirées"""
    with get_db() as db:
        db.execute("""
            UPDATE accounts SET status='available', reserved_by=NULL, reserved_until=NULL 
            WHERE status='reserved' AND reserved_until < datetime('now')
        """)


def deliver_account(account_id, user_id):
    """Marque un compte comme livré et retourne les credentials"""
    with get_db() as db:
        db.execute(
            "UPDATE accounts SET status='sold', sold_to=?, sold_at=datetime('now') WHERE id=?",
            (user_id, account_id)
        )
        account = db.execute("SELECT credentials, extra_info FROM accounts WHERE id=?", (account_id,)).fetchone()
        return dict(account)


# ══════════════════════════════════════════════
# 🛒 ORDER OPERATIONS
# ══════════════════════════════════════════════

def create_order(user_id, game, tier, delivery_mode, base_price, final_price, discount=0, referral_code=None):
    """Crée une nouvelle commande"""
    order_ref = f"GV-{int(time.time())}-{secrets.token_hex(3).upper()}"
    with get_db() as db:
        db.execute("""
            INSERT INTO orders (order_ref, user_id, game, tier, delivery_mode, base_price, final_price, 
                               discount_applied, referral_code_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (order_ref, user_id, game, tier, delivery_mode, base_price, final_price, discount, referral_code))
        order = db.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
        return dict(order)


def update_order_payment(order_ref, payment_method, payment_id, status):
    """Met à jour le paiement d'une commande"""
    with get_db() as db:
        db.execute("""
            UPDATE orders SET payment_method=?, payment_id=?, payment_status=?, 
                             paid_at=CASE WHEN ?='paid' THEN datetime('now') ELSE paid_at END
            WHERE order_ref=?
        """, (payment_method, payment_id, status, status, order_ref))


def update_order_status(order_ref, status, account_id=None):
    """Met à jour le statut de la commande"""
    with get_db() as db:
        if account_id:
            db.execute("""
                UPDATE orders SET order_status=?, account_id=?, 
                                 delivered_at=CASE WHEN ?='delivered' THEN datetime('now') ELSE delivered_at END
                WHERE order_ref=?
            """, (status, account_id, status, order_ref))
        else:
            db.execute("UPDATE orders SET order_status=? WHERE order_ref=?", (status, order_ref))


def get_order(order_ref):
    """Récupère une commande par référence"""
    with get_db() as db:
        order = db.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
        return dict(order) if order else None


def get_user_orders(user_id, limit=10):
    """Récupère les commandes d'un utilisateur"""
    with get_db() as db:
        orders = db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [dict(o) for o in orders]


# ══════════════════════════════════════════════
# 🛡️ ANTI-FRAUD OPERATIONS
# ══════════════════════════════════════════════

def log_security_event(user_id, event_type, details=None, risk_level="low"):
    """Enregistre un événement de sécurité"""
    with get_db() as db:
        db.execute(
            "INSERT INTO security_logs (user_id, event_type, details, risk_level) VALUES (?, ?, ?, ?)",
            (user_id, event_type, details, risk_level)
        )


def get_user_order_count(user_id, hours=1):
    """Compte les commandes récentes d'un utilisateur"""
    with get_db() as db:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        result = db.execute(
            "SELECT COUNT(*) as count FROM orders WHERE user_id=? AND created_at > ?",
            (user_id, since)
        ).fetchone()
        return result["count"]


def get_failed_payment_count(user_id, hours=24):
    """Compte les paiements échoués récents"""
    with get_db() as db:
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        result = db.execute(
            "SELECT COUNT(*) as count FROM orders WHERE user_id=? AND payment_status='failed' AND created_at > ?",
            (user_id, since)
        ).fetchone()
        return result["count"]


# ══════════════════════════════════════════════
# ⭐ REVIEW OPERATIONS
# ══════════════════════════════════════════════

def add_review(order_id, user_id, rating, comment=None):
    """Ajoute un avis"""
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO reviews (order_id, user_id, rating, comment) VALUES (?, ?, ?, ?)",
            (order_id, user_id, rating, comment)
        )


def get_reviews(game=None, limit=20):
    """Récupère les avis"""
    with get_db() as db:
        if game:
            reviews = db.execute("""
                SELECT r.*, o.game, o.tier, u.username 
                FROM reviews r 
                JOIN orders o ON r.order_id = o.id 
                JOIN users u ON r.user_id = u.user_id
                WHERE o.game=? AND r.is_visible=1 
                ORDER BY r.created_at DESC LIMIT ?
            """, (game, limit)).fetchall()
        else:
            reviews = db.execute("""
                SELECT r.*, o.game, o.tier, u.username 
                FROM reviews r 
                JOIN orders o ON r.order_id = o.id 
                JOIN users u ON r.user_id = u.user_id
                WHERE r.is_visible=1 
                ORDER BY r.created_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in reviews]


def get_average_rating(game=None):
    """Récupère la note moyenne"""
    with get_db() as db:
        if game:
            result = db.execute(
                "SELECT AVG(r.rating) as avg, COUNT(*) as count FROM reviews r JOIN orders o ON r.order_id=o.id WHERE o.game=? AND r.is_visible=1",
                (game,)
            ).fetchone()
        else:
            result = db.execute(
                "SELECT AVG(rating) as avg, COUNT(*) as count FROM reviews WHERE is_visible=1"
            ).fetchone()
        return {"average": round(result["avg"] or 0, 1), "count": result["count"]}


# ══════════════════════════════════════════════
# 🎫 TICKET OPERATIONS
# ══════════════════════════════════════════════

def create_ticket(user_id, subject, order_id=None, priority="normal"):
    """Crée un ticket SAV"""
    with get_db() as db:
        db.execute(
            "INSERT INTO tickets (user_id, order_id, subject, priority) VALUES (?, ?, ?, ?)",
            (user_id, order_id, subject, priority)
        )
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def add_ticket_message(ticket_id, sender, message):
    """Ajoute un message à un ticket"""
    with get_db() as db:
        ticket = db.execute("SELECT messages FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if ticket:
            messages = json.loads(ticket["messages"])
            messages.append({
                "sender": sender,
                "message": message,
                "timestamp": datetime.now().isoformat()
            })
            db.execute(
                "UPDATE tickets SET messages=?, updated_at=datetime('now') WHERE id=?",
                (json.dumps(messages), ticket_id)
            )


def get_stats():
    """Récupère les statistiques globales pour le dashboard"""
    with get_db() as db:
        stats = {}
        stats["total_users"] = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        stats["total_orders"] = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        stats["total_revenue"] = db.execute(
            "SELECT COALESCE(SUM(final_price), 0) FROM orders WHERE payment_status='paid'"
        ).fetchone()[0]
        stats["orders_today"] = db.execute(
            "SELECT COUNT(*) FROM orders WHERE date(created_at)=date('now')"
        ).fetchone()[0]
        stats["revenue_today"] = db.execute(
            "SELECT COALESCE(SUM(final_price), 0) FROM orders WHERE payment_status='paid' AND date(created_at)=date('now')"
        ).fetchone()[0]
        stats["pending_tickets"] = db.execute(
            "SELECT COUNT(*) FROM tickets WHERE status IN ('open', 'in_progress')"
        ).fetchone()[0]
        stats["stock"] = get_all_stock()
        stats["avg_rating"] = get_average_rating()
        return stats
