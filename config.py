import os

from dotenv import load_dotenv


# Load variables from a .env file if one exists.
# This is a safe no-op when .env is absent.
load_dotenv()


# --- Razorpay credentials (test mode only) ---
RAZORPAY_KEY_ID = os.getenv(
    "RAZORPAY_KEY_ID",
    "rzp_test_placeholder_key_id",
)
RAZORPAY_KEY_SECRET = os.getenv(
    "RAZORPAY_KEY_SECRET",
    "placeholder_test_secret",
)


# --- Mandate owner confirmation ---
# Demo-only owner confirmation secret. Keep the real value in .env.
# Never send this value to the frontend or audit log.
MANDATE_OWNER_PASSWORD = os.getenv("MANDATE_OWNER_PASSWORD", "")


# --- Razorpay API base URL ---
# Same base URL is used for both test mode and live mode.
# Which one you hit depends entirely on whether your KEY_ID/KEY_SECRET
# are test keys (rzp_test_...) or live keys (rzp_live_...).
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


# --- App-wide constants ---
DEFAULT_CURRENCY = "INR"


# Simple flag so the rest of the app can tell if real keys are configured,
# instead of silently trying (and failing) real API calls with placeholders.
RAZORPAY_CONFIGURED = not RAZORPAY_KEY_ID.startswith(
    "rzp_test_placeholder"
)