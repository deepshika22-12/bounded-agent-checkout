import requests

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_BASE_URL, RAZORPAY_CONFIGURED


def create_test_order(amount: int, currency: str, receipt_id: str) -> dict:
    """
    Create an order in Razorpay TEST MODE.

    Args:
        amount: amount in the SMALLEST currency unit (e.g. paise for INR).
                So INR 799.00 -> amount=79900.
        currency: e.g. "INR"
        receipt_id: your own internal reference string for this order

    Returns:
        dict with the order details Razorpay returns (id, amount, currency,
        receipt, status, etc.)

    Note: this only ever creates an ORDER (a payment intent). No money moves
    until a payment is actually made and captured against this order id --
    which in test mode would be done with Razorpay's published test card
    numbers, never a real card.
    """
    if not RAZORPAY_CONFIGURED:
        # No real keys set yet -- return a clearly-labelled mock response so
        # the rest of the app (and a demo) can still run end-to-end.
        return {
            "id": f"order_MOCK_{receipt_id}",
            "amount": amount,
            "currency": currency,
            "receipt": receipt_id,
            "status": "created",
            "note": (
                "MOCK ORDER -- RAZORPAY_KEY_ID/SECRET not configured. "
                "Set real test-mode keys in a .env file to hit the actual API."
            ),
        }

    url = f"{RAZORPAY_BASE_URL}/orders"
    payload = {
        "amount": amount,
        "currency": currency,
        "receipt": receipt_id,
        "payment_capture": 1,  # auto-capture once payment is authorized
    }

    response = requests.post(
        url,
        json=payload,
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        timeout=10,
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Razorpay order creation failed: {response.status_code} {response.text}"
        )

    return response.json()


def verify_payment(order_id: str, payment_id: str, signature: str) -> bool:
    """
    STUB -- real signature verification comes later.

    In the real flow, Razorpay sends back (order_id, payment_id, signature)
    after checkout, and you verify `signature` was generated using your
    key_secret + order_id + payment_id (HMAC-SHA256), to prove the payment
    response actually came from Razorpay and wasn't forged client-side.

    For now this just logs the inputs and always returns True, so the rest
    of the flow (order -> "payment" -> audit log) can be wired up and
    demoed before real signature verification is implemented.
    """
    print(
        f"[verify_payment STUB] order_id={order_id} payment_id={payment_id} "
        f"signature={signature} -> treating as verified (not real verification yet)"
    )
    return True
