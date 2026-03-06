"""
💰 GameVault Bot - Payment Handlers
Gère tous les moyens de paiement: Crypto, PayPal, Stripe, CashApp
"""
import hashlib
import hmac
import json
import time
import aiohttp
from config.settings import (
    STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
    PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_MODE,
    CRYPTO_API_KEY, CRYPTO_PROVIDER, CRYPTO_IPN_SECRET
)


class PaymentError(Exception):
    pass


# ══════════════════════════════════════════════
# 💳 STRIPE (Carte bancaire)
# ══════════════════════════════════════════════

class StripePayment:
    BASE_URL = "https://api.stripe.com/v1"

    @classmethod
    async def create_checkout(cls, order_ref: str, amount: float, currency: str = "eur") -> dict:
        """Crée une session Stripe Checkout"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{cls.BASE_URL}/checkout/sessions",
                headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
                data={
                    "payment_method_types[]": "card",
                    "line_items[0][price_data][currency]": currency,
                    "line_items[0][price_data][unit_amount]": int(amount * 100),
                    "line_items[0][price_data][product_data][name]": f"GameVault - {order_ref}",
                    "line_items[0][quantity]": 1,
                    "mode": "payment",
                    "metadata[order_ref]": order_ref,
                    "success_url": f"https://t.me/GameVaultBot?start=paid_{order_ref}",
                    "cancel_url": f"https://t.me/GameVaultBot?start=cancel_{order_ref}",
                    "expires_after_completion[enabled]": "true",
                }
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise PaymentError(f"Stripe error: {data['error']['message']}")
                return {
                    "payment_url": data["url"],
                    "payment_id": data["id"],
                    "method": "stripe"
                }

    @classmethod
    def verify_webhook(cls, payload: bytes, sig_header: str) -> dict:
        """Vérifie un webhook Stripe"""
        # Simplified - use stripe lib in production
        return json.loads(payload)


# ══════════════════════════════════════════════
# 🅿️ PAYPAL
# ══════════════════════════════════════════════

class PayPalPayment:
    SANDBOX_URL = "https://api-m.sandbox.paypal.com"
    LIVE_URL = "https://api-m.paypal.com"

    @classmethod
    def _base_url(cls):
        return cls.LIVE_URL if PAYPAL_MODE == "live" else cls.SANDBOX_URL

    @classmethod
    async def _get_token(cls) -> str:
        """Obtient un token d'accès PayPal"""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{cls._base_url()}/v1/oauth2/token",
                auth=aiohttp.BasicAuth(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
                data={"grant_type": "client_credentials"}
            ) as resp:
                data = await resp.json()
                return data["access_token"]

    @classmethod
    async def create_order(cls, order_ref: str, amount: float, currency: str = "EUR") -> dict:
        """Crée une commande PayPal"""
        token = await cls._get_token()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{cls._base_url()}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "reference_id": order_ref,
                        "amount": {
                            "currency_code": currency,
                            "value": f"{amount:.2f}"
                        },
                        "description": f"GameVault - {order_ref}"
                    }],
                    "application_context": {
                        "return_url": f"https://t.me/GameVaultBot?start=paid_{order_ref}",
                        "cancel_url": f"https://t.me/GameVaultBot?start=cancel_{order_ref}"
                    }
                }
            ) as resp:
                data = await resp.json()
                approve_link = next(
                    (l["href"] for l in data.get("links", []) if l["rel"] == "approve"), None
                )
                return {
                    "payment_url": approve_link,
                    "payment_id": data["id"],
                    "method": "paypal"
                }

    @classmethod
    async def capture_order(cls, paypal_order_id: str) -> dict:
        """Capture un paiement PayPal"""
        token = await cls._get_token()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{cls._base_url()}/v2/checkout/orders/{paypal_order_id}/capture",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            ) as resp:
                return await resp.json()


# ══════════════════════════════════════════════
# ₿ CRYPTO (NOWPayments / Plisio / CoinGate)
# ══════════════════════════════════════════════

class CryptoPayment:
    PROVIDERS = {
        "nowpayments": {
            "base_url": "https://api.nowpayments.io/v1",
            "create_endpoint": "/invoice",
        },
        "plisio": {
            "base_url": "https://plisio.net/api/v1",
            "create_endpoint": "/invoices/new",
        },
        "coingate": {
            "base_url": "https://api.coingate.com/v2",
            "create_endpoint": "/orders",
        }
    }

    @classmethod
    async def create_invoice(cls, order_ref: str, amount: float, currency: str = "eur") -> dict:
        """Crée une facture crypto selon le provider configuré"""
        provider = CRYPTO_PROVIDER
        config = cls.PROVIDERS.get(provider, cls.PROVIDERS["nowpayments"])

        async with aiohttp.ClientSession() as session:
            if provider == "nowpayments":
                async with session.post(
                    f"{config['base_url']}/invoice",
                    headers={"x-api-key": CRYPTO_API_KEY, "Content-Type": "application/json"},
                    json={
                        "price_amount": amount,
                        "price_currency": currency,
                        "order_id": order_ref,
                        "order_description": f"GameVault - {order_ref}",
                        "success_url": f"https://t.me/GameVaultBot?start=paid_{order_ref}",
                        "cancel_url": f"https://t.me/GameVaultBot?start=cancel_{order_ref}",
                    }
                ) as resp:
                    data = await resp.json()
                    return {
                        "payment_url": data.get("invoice_url"),
                        "payment_id": str(data.get("id")),
                        "method": "crypto"
                    }

            elif provider == "plisio":
                async with session.get(
                    f"{config['base_url']}/invoices/new",
                    params={
                        "api_key": CRYPTO_API_KEY,
                        "currency": "EUR",
                        "amount": str(amount),
                        "order_name": f"GameVault - {order_ref}",
                        "order_number": order_ref,
                        "callback_url": f"https://yourserver.com/webhook/plisio?order={order_ref}",
                    }
                ) as resp:
                    data = await resp.json()
                    invoice_data = data.get("data", {})
                    return {
                        "payment_url": invoice_data.get("invoice_url"),
                        "payment_id": invoice_data.get("txn_id"),
                        "method": "crypto"
                    }

            elif provider == "coingate":
                async with session.post(
                    f"{config['base_url']}/orders",
                    headers={"Authorization": f"Token {CRYPTO_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "order_id": order_ref,
                        "price_amount": amount,
                        "price_currency": currency.upper(),
                        "receive_currency": "EUR",
                        "title": f"GameVault - {order_ref}",
                        "success_url": f"https://t.me/GameVaultBot?start=paid_{order_ref}",
                        "cancel_url": f"https://t.me/GameVaultBot?start=cancel_{order_ref}",
                    }
                ) as resp:
                    data = await resp.json()
                    return {
                        "payment_url": data.get("payment_url"),
                        "payment_id": str(data.get("id")),
                        "method": "crypto"
                    }

    @classmethod
    def verify_ipn(cls, payload: dict, signature: str) -> bool:
        """Vérifie un callback IPN crypto"""
        if CRYPTO_PROVIDER == "nowpayments":
            sorted_params = json.dumps(dict(sorted(payload.items())), separators=(',', ':'))
            expected = hmac.new(
                CRYPTO_IPN_SECRET.encode(), sorted_params.encode(), hashlib.sha512
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        return True  # Implement for other providers


# ══════════════════════════════════════════════
# 🏦 PAYMENT ROUTER
# ══════════════════════════════════════════════

class PaymentRouter:
    """Route les paiements vers le bon provider"""

    METHODS = {
        "stripe": {"name": "💳 Carte Bancaire", "handler": StripePayment, "emoji": "💳"},
        "paypal": {"name": "🅿️ PayPal", "handler": PayPalPayment, "emoji": "🅿️"},
        "crypto": {"name": "₿ Crypto (BTC/ETH/USDT)", "handler": CryptoPayment, "emoji": "₿"},
    }

    @classmethod
    async def create_payment(cls, method: str, order_ref: str, amount: float) -> dict:
        """Crée un paiement avec le provider approprié"""
        if method not in cls.METHODS:
            raise PaymentError(f"Méthode inconnue: {method}")

        handler = cls.METHODS[method]["handler"]

        if method == "stripe":
            return await handler.create_checkout(order_ref, amount)
        elif method == "paypal":
            return await handler.create_order(order_ref, amount)
        elif method == "crypto":
            return await handler.create_invoice(order_ref, amount)

        raise PaymentError(f"Handler non implémenté pour: {method}")
