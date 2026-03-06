"""
🛡️ GameVault Bot - Système Anti-Fraude
Détecte et bloque les comportements suspects
"""
import time
from datetime import datetime, timedelta
from config.settings import (
    MAX_ORDERS_PER_HOUR, MAX_ORDERS_PER_DAY, MAX_FAILED_PAYMENTS,
    BAN_DURATION_HOURS, ADMIN_IDS
)
from database.db import (
    get_user_order_count, get_failed_payment_count,
    log_security_event, ban_user, is_user_banned
)


class AntifraudEngine:
    """Moteur anti-fraude avec scoring de risque"""

    # Cache mémoire pour rate limiting rapide
    _order_timestamps = {}  # user_id -> [timestamps]
    _failed_payments = {}   # user_id -> count

    @classmethod
    def check_user(cls, user_id: int) -> dict:
        """
        Vérifie un utilisateur avant de traiter une commande.
        Retourne: {"allowed": bool, "reason": str, "risk_score": int}
        """
        # 1. Check ban
        if is_user_banned(user_id):
            return {"allowed": False, "reason": "🚫 Votre compte est temporairement suspendu.", "risk_score": 100}

        # 2. Admin bypass
        if user_id in ADMIN_IDS:
            return {"allowed": True, "reason": "admin", "risk_score": 0}

        risk_score = 0
        reasons = []

        # 3. Rate limiting - par heure
        hourly_count = get_user_order_count(user_id, hours=1)
        if hourly_count >= MAX_ORDERS_PER_HOUR:
            risk_score += 50
            reasons.append("Trop de commandes cette heure")
            log_security_event(user_id, "rate_limit_hourly", f"{hourly_count} commandes/h", "high")

        # 4. Rate limiting - par jour
        daily_count = get_user_order_count(user_id, hours=24)
        if daily_count >= MAX_ORDERS_PER_DAY:
            risk_score += 40
            reasons.append("Trop de commandes aujourd'hui")
            log_security_event(user_id, "rate_limit_daily", f"{daily_count} commandes/24h", "high")

        # 5. Paiements échoués
        failed = get_failed_payment_count(user_id, hours=24)
        if failed >= MAX_FAILED_PAYMENTS:
            risk_score += 60
            reasons.append("Trop de paiements échoués")
            log_security_event(user_id, "payment_failures", f"{failed} échecs/24h", "critical")
            # Auto-ban
            ban_user(user_id, "Auto-ban: paiements échoués répétés", BAN_DURATION_HOURS)
            return {
                "allowed": False,
                "reason": f"🚫 Compte suspendu {BAN_DURATION_HOURS}h suite à des paiements échoués répétés.",
                "risk_score": risk_score
            }

        # 6. Rapid ordering (mémoire)
        now = time.time()
        timestamps = cls._order_timestamps.get(user_id, [])
        timestamps = [t for t in timestamps if now - t < 300]  # 5 min window
        if len(timestamps) >= 3:
            risk_score += 30
            reasons.append("Commandes trop rapides")
            log_security_event(user_id, "rapid_ordering", f"{len(timestamps)} en 5min", "medium")

        # Décision
        if risk_score >= 80:
            ban_user(user_id, f"Auto-ban: score risque {risk_score}", BAN_DURATION_HOURS)
            return {
                "allowed": False,
                "reason": "🚫 Activité suspecte détectée. Compte temporairement suspendu.",
                "risk_score": risk_score
            }
        elif risk_score >= 50:
            return {
                "allowed": False,
                "reason": "⚠️ Veuillez patienter avant de passer une nouvelle commande.",
                "risk_score": risk_score
            }

        # Enregistrer le timestamp
        timestamps.append(now)
        cls._order_timestamps[user_id] = timestamps

        return {"allowed": True, "reason": "ok", "risk_score": risk_score}

    @classmethod
    def log_payment_failure(cls, user_id: int, details: str = ""):
        """Enregistre un échec de paiement"""
        cls._failed_payments[user_id] = cls._failed_payments.get(user_id, 0) + 1
        log_security_event(user_id, "payment_failed", details, "medium")

    @classmethod
    def log_successful_order(cls, user_id: int, order_ref: str):
        """Enregistre une commande réussie (reset les compteurs négatifs)"""
        cls._failed_payments.pop(user_id, None)
        log_security_event(user_id, "order_success", order_ref, "low")

    @classmethod
    def cleanup(cls):
        """Nettoyage périodique des caches"""
        now = time.time()
        for user_id in list(cls._order_timestamps.keys()):
            cls._order_timestamps[user_id] = [
                t for t in cls._order_timestamps[user_id] if now - t < 3600
            ]
            if not cls._order_timestamps[user_id]:
                del cls._order_timestamps[user_id]
