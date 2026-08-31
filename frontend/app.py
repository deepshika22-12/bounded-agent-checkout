from datetime import datetime
from html import escape
from pathlib import Path
from PIL import Image, ImageOps
from urllib.parse import quote
import uuid
import csv
import json
import io

import requests
import streamlit as st
from requests.exceptions import ConnectionError, Timeout


def utcnow():
    from datetime import datetime as _dt, timezone as _tz
    return _dt.now(_tz.utc).replace(tzinfo=None)



BASE_URL = st.secrets.get(
    "BACKEND_URL",
    "http://127.0.0.1:8000",
)

# Fast, purely local endpoints: catalog, mandate, metrics, audit, trace.
TIMEOUT_SECONDS = 8

# POST /agent/plan invokes the local Ollama model. A cold start alone
# takes 5-30 seconds, and CPU inference on a 3B model adds several more,
# so this must be generous or the UI will report a false failure.
PLANNER_TIMEOUT_SECONDS = 180
PROJECT_ROOT = Path(__file__).resolve().parent.parent


st.set_page_config(
    page_title="Bounded Agent Checkout",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --blue: #2563EB;
        --blue-dark: #1D4ED8;
        --cream: #F9F7F2;
        --card: #FFFFFF;
        --border: #E7E5E4;
        --text: #1C1917;
        --muted: #78716C;
        --green: #15803D;
        --green-soft: #DCFCE7;
        --red: #B91C1C;
        --red-soft: #FEE2E2;
        --amber: #B45309;
        --amber-soft: #FEF3C7;
        --purple-soft: #F3E8FF;
        --purple-text: #6B21A8;
    }

    #MainMenu,
    footer,
    header {
        visibility: hidden;
    }

    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"] {
        background-color: var(--cream) !important;
    }

    html,
    body,
    [class*="css"] {
        font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: var(--text);
    }

    .block-container {
        max-width: 1240px;
        padding-top: 1.75rem;
        padding-bottom: 2.5rem;
    }

    div[data-testid="stMarkdownContainer"] p {
        color: var(--muted);
    }

    /* Primary Streamlit buttons */
    div.stButton > button {
        min-height: 44px !important;
        width: 100% !important;
        border: 0 !important;
        border-radius: 10px !important;
        background-color: #2563EB !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        text-shadow: none !important;
        transition: background-color 0.15s ease, transform 0.15s ease;
    }

    /* Forces nested text and icons inside buttons to stay visible */
    div.stButton > button *,
    div.stButton > button p,
    div.stButton > button span {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
        opacity: 1 !important;
    }

    div.stButton > button:hover {
        background-color: #1D4ED8 !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
    }

    div.stButton > button:hover *,
    div.stButton > button:hover p,
    div.stButton > button:hover span {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
    }

    div.stButton > button:focus,
    div.stButton > button:focus-visible {
        color: #FFFFFF !important;
        outline: 3px solid rgba(37, 99, 235, 0.3) !important;
        outline-offset: 2px !important;
    }

    div[data-testid="stMetric"] {
        min-height: 122px;
        padding: 1rem 1.1rem;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: var(--card);
        box-shadow: 0 2px 8px rgba(41, 37, 36, 0.05);
    }

    div[data-testid="stMetricLabel"] {
        color: var(--muted);
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    div[data-testid="stMetricValue"] {
        color: var(--text);
        font-weight: 700;
    }

    div[data-baseweb="tab-list"] {
        gap: 0.35rem;
        padding: 0.35rem;
        border-radius: 12px;
        background: #F1EFEC;
    }

    button[data-baseweb="tab"] {
        height: 42px;
        padding: 0 1rem;
        border-radius: 9px;
        color: var(--muted);
        font-weight: 600;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        background: #FFFFFF;
        color: var(--blue);
        box-shadow: 0 1px 4px rgba(41, 37, 36, 0.1);
    }

    .page-hero {
        padding: 0.9rem 0 1.55rem;
    }

    .page-hero h1 {
        margin: 0;
        color: var(--text);
        font-size: clamp(1.8rem, 3vw, 2.45rem);
        font-weight: 700;
        letter-spacing: -0.04em;
    }

    .page-hero p {
        margin: 0.5rem 0 0;
        color: var(--muted);
        font-size: 1rem;
    }

    .section-title {
        margin: 1.8rem 0 0.25rem;
        color: var(--text);
        font-size: 1.25rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .section-copy {
        margin: 0 0 1rem;
        color: var(--muted);
        font-size: 0.92rem;
        line-height: 1.5;
    }

    .info-card {
        min-height: 122px;
        padding: 1rem 1.1rem;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: var(--card);
        box-shadow: 0 2px 8px rgba(41, 37, 36, 0.05);
    }

    .info-label {
        margin-bottom: 0.8rem;
        color: var(--muted);
        font-size: 0.78rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    .info-value {
        color: var(--text);
        font-size: 1rem;
        font-weight: 600;
        line-height: 1.5;
        overflow-wrap: anywhere;
    }

    .chip {
        display: inline-block;
        margin: 0.15rem 0.25rem 0.15rem 0;
        padding: 0.25rem 0.6rem;
        border: 1px solid #DDD6FE;
        border-radius: 999px;
        background: var(--purple-soft);
        color: var(--purple-text);
        font-size: 0.78rem;
        font-weight: 600;
    }

    .owner-control-card {
        margin: 1rem 0 0;
        padding: 1rem 1.1rem;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: var(--card);
        box-shadow: 0 2px 8px rgba(41, 37, 36, 0.05);
    }

    .owner-control-card h3 {
        margin: 0 0 0.4rem;
        color: var(--text);
        font-size: 1rem;
    }

    .status-badge {
        display: inline-block;
        margin: 0.15rem 0 0.55rem;
        padding: 0.3rem 0.65rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 700;
    }

    .status-active {
        border: 1px solid #BBF7D0;
        background: var(--green-soft);
        color: #166534;
    }

    .status-paused {
        border: 1px solid #FDE68A;
        background: var(--amber-soft);
        color: var(--amber);
    }

    .status-revoked {
        border: 1px solid #FECACA;
        background: var(--red-soft);
        color: #991B1B;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        min-height: 430px;
        border-radius: 16px;
        background: var(--card);
        border-color: var(--border);
        box-shadow: 0 2px 10px rgba(41, 37, 36, 0.06);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stImage"] {
        width: 100%;
        height: 155px;
        overflow: hidden;
        border-radius: 11px;
        background: #F5F5F4;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] div[data-testid="stImage"] img {
        display: block;
        width: 100%;
        height: 155px;
        object-fit: cover;
        border-radius: 11px;
    }

    .product-name {
        min-height: 46px;
        margin: 0.8rem 0 0.15rem;
        color: var(--text);
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.4;
    }

    .product-meta {
        min-height: 20px;
        color: var(--muted);
        font-size: 0.76rem;
    }

    .category-badge,
    .stock-badge,
    .mode-badge,
    .confidence-badge {
        display: inline-block;
        margin: 0.55rem 0.2rem 0 0;
        padding: 0.24rem 0.55rem;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 600;
    }

    .category-badge {
        border: 1px solid #DDD6FE;
        background: var(--purple-soft);
        color: var(--purple-text);
    }

    .stock-available {
        border: 1px solid #BBF7D0;
        background: var(--green-soft);
        color: #166534;
    }

    .stock-unavailable {
        border: 1px solid #FECACA;
        background: var(--red-soft);
        color: #991B1B;
    }

    .mode-badge {
        border: 1px solid #E7E5E4;
        background: #F5F5F4;
        color: #57534E;
    }

    .confidence-high {
        border: 1px solid #BBF7D0;
        background: var(--green-soft);
        color: #166534;
    }

    .confidence-medium {
        border: 1px solid #FDE68A;
        background: var(--amber-soft);
        color: var(--amber);
    }

    .confidence-low {
        border: 1px solid #FECACA;
        background: var(--red-soft);
        color: #991B1B;
    }

    .product-description {
        min-height: 42px;
        margin: 0.7rem 0;
        color: #57534E;
        font-size: 0.83rem;
        line-height: 1.45;
    }

    .product-price {
        margin: 0.5rem 0 0.8rem;
        color: #1E3A8A;
        font-size: 1.2rem;
        font-weight: 700;
    }

    .reference-note {
        margin-top: 0.35rem;
        color: var(--muted);
        font-size: 0.72rem;
        text-align: center;
    }

    .proposal-card,
    .trace-card {
        margin: 0.85rem 0;
        padding: 1.1rem;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: var(--card);
        box-shadow: 0 2px 8px rgba(41, 37, 36, 0.05);
    }

    .proposal-card h3,
    .trace-card h3 {
        margin: 0 0 0.65rem;
        color: var(--text);
        font-size: 1rem;
    }

    .confidence-track {
        width: 100%;
        height: 8px;
        margin-top: 0.65rem;
        border-radius: 999px;
        overflow: hidden;
        background: #E7E5E4;
    }

    .confidence-fill {
        height: 100%;
        border-radius: 999px;
    }

    .confidence-fill.high {
        background: #16A34A;
    }

    .confidence-fill.medium {
        background: #D97706;
    }

    .confidence-fill.low {
        background: #DC2626;
    }

    @media (max-width: 640px) {
        .block-container {
            padding: 1rem 0.8rem 2rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: auto;
        }

        button[data-baseweb="tab"] {
            padding: 0 0.7rem;
            font-size: 0.84rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def backend_get(path: str, timeout: float = TIMEOUT_SECONDS):
    try:
        response = requests.get(f"{BASE_URL}{path}", timeout=timeout)
        response.raise_for_status()
        return response.json(), None
    except ConnectionError:
        return None, "unreachable"
    except Timeout:
        return None, "timeout"
    except requests.HTTPError as error:
        return None, f"HTTP error: {error.response.status_code}"
    except Exception as error:
        return None, f"Unexpected error: {error}"

def backend_put(
    path: str,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: float = TIMEOUT_SECONDS,
):
    try:
        response = requests.put(
            f"{BASE_URL}{path}",
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json(), None
    except ConnectionError:
        return None, "unreachable"
    except Timeout:
        return None, "timeout"
    except requests.HTTPError as error:
        try:
            return error.response.json(), f"http_error_{error.response.status_code}"
        except Exception:
            return None, f"http_error_{error.response.status_code}"
    except Exception as error:
        return None, f"Unexpected error: {error}"
    
def backend_post(
    path: str,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: float = TIMEOUT_SECONDS,
):
    try:
        response = requests.post(
            f"{BASE_URL}{path}",
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json(), None
    except ConnectionError:
        return None, "unreachable"
    except Timeout:
        return None, "timeout"
    except requests.HTTPError as error:
        try:
            return error.response.json(), f"http_error_{error.response.status_code}"
        except Exception:
            return None, f"http_error_{error.response.status_code}"
    except Exception as error:
        return None, f"Unexpected error: {error}"

def backend_put(
    path: str,
    json_body: dict | None = None,
    headers: dict | None = None,
    timeout: float = TIMEOUT_SECONDS,
):
    try:
        response = requests.put(
            f"{BASE_URL}{path}",
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json(), None
    except ConnectionError:
        return None, "unreachable"
    except Timeout:
        return None, "timeout"
    except requests.HTTPError as error:
        try:
            return error.response.json(), f"http_error_{error.response.status_code}"
        except Exception:
            return None, f"http_error_{error.response.status_code}"
    except Exception as error:
        return None, f"Unexpected error: {error}"

def show_backend_unreachable():
    st.error(
        f"Backend not reachable at `{BASE_URL}`. "
        "Start both services with `python run_all.py`, then refresh the page."
    )


def show_planner_timeout():
    st.error(
        f"The backend is running, but the planner did not answer within "
        f"{PLANNER_TIMEOUT_SECONDS} seconds."
    )
    st.caption(
        "This is a slow local model, not a connection problem. Check the "
        "backend terminal for a line starting with `[planner]`. To bypass "
        "the model entirely, restart with `$env:OLLAMA_ENABLED = \"0\"` "
        "and the deterministic rule-based planner will answer instantly."
    )

def get_budget_metrics():
    data, error = backend_get("/metrics/budget")
    if error:
        return None
    return data

def update_mandate_settings(payload: dict):
    return backend_put("/mandate", json_body=payload)

def get_notification_preferences():
    return backend_get("/notifications/preferences")


def get_notifications(limit: int = 20):
    return backend_get(f"/notifications?limit={limit}")


def update_notification_preferences(payload: dict):
    return backend_put(
        "/notifications/preferences",
        json_body=payload,
    )


def get_pending_orders():
    data, error = backend_get("/orders/pending")

    if error:
        return [], error

    return data.get("pending_orders", []), None


def request_pending_approval(item_id: str, source: str):
    return backend_post(
        "/orders/pending",
        json_body={
            "item_id": item_id,
            "source": source,
        },
    )

def find_alternatives(
    catalog: list,
    mandate: dict,
    exclude_item_id: str,
    max_suggestions: int = 2,
) -> list:
    if not catalog or not mandate:
        return []

    candidates = [
        item
        for item in catalog
        if item["item_id"] != exclude_item_id
        and item.get("in_stock", True)
        and item["category"] in mandate["allowed_categories"]
        and item["price"] <= mandate["spending_cap"]
    ]
    return sorted(candidates, key=lambda item: item["price"])[:max_suggestions]


def load_product_image(image_path: str, width: int = 600, height: int = 360):
    try:
        path = Path(image_path)

        if not path.is_absolute():
            path = PROJECT_ROOT / path

        if not path.exists() or not path.is_file():
            return None

        image = Image.open(path).convert("RGB")
        return ImageOps.fit(
            image,
            (width, height),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    except Exception:
        return None


def confidence_style(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def render_section(title: str, copy: str = ""):
    st.markdown(
        f'<div class="section-title">{escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if copy:
        st.markdown(
            f'<div class="section-copy">{escape(copy)}</div>',
            unsafe_allow_html=True,
        )


def unpack_order_response(result: dict) -> tuple[dict | None, bool]:
    if not isinstance(result, dict):
        return None, False

    if isinstance(result.get("order"), dict):
        return result["order"], bool(result.get("idempotent_replay", False))

    if result.get("id"):
        return result, False

    return None, False


def render_order(order: dict, idempotent_replay: bool = False):
    if idempotent_replay:
        st.info("This request was already processed. Showing the original order.")

    st.success("Order created successfully.")
    left, right = st.columns(2)
    left.metric("Order ID", order.get("id", "—"))
    right.metric("Amount", f"₹{order.get('amount', 0) / 100:,.2f}")

    with st.expander("Order response"):
        st.json(order)

    if order.get("note", "").startswith("MOCK ORDER"):
        st.caption("Mock order: Razorpay test keys are not configured.")
    else:
        st.caption("Razorpay test-mode order. No real money is charged.")

def render_owner_control(mandate: dict):
    status = mandate.get("status", "active")
    version = mandate.get("mandate_version", 1)

    status_labels = {
        "active": "Active",
        "paused": "Paused",
        "revoked": "Revoked",
    }

    status_classes = {
        "active": "status-active",
        "paused": "status-paused",
        "revoked": "status-revoked",
    }

    status_label = status_labels.get(status, "Unknown")
    status_class = status_classes.get(status, "status-paused")

    st.markdown(
        f"""
        <div class="owner-control-card">
            <h3>Agent purchasing status</h3>
            <span class="status-badge {status_class}">{status_label}</span>
            <div class="section-copy">
                Only the mandate owner can pause, resume, or revoke agent purchasing.
                The AI cannot modify its own permissions.
            </div>
            <div class="section-copy" style="margin-top: 0.5rem;">
                <strong>Policy version:</strong> v{version}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if status == "revoked":
        st.error(
            "This mandate has been permanently revoked. Agent purchasing is "
            "disabled and cannot be resumed from this dashboard."
        )
        return

    owner_password = st.text_input(
        "Confirm your password",
        type="password",
        key="mandate_owner_password",
        help="Required to pause, resume, or permanently revoke purchasing.",
    )

    if status == "active":
        button_label = "Pause agent purchasing"
        endpoint = "/mandate/pause"
        success_message = "Agent purchasing paused successfully."
    else:
        button_label = "Resume agent purchasing"
        endpoint = "/mandate/resume"
        success_message = "Agent purchasing resumed successfully."

    if st.button(button_label, key="mandate_status_button"):
        if not owner_password:
            st.warning("Enter your password to confirm this mandate change.")
        else:
            result, error = backend_post(
                endpoint,
                json_body={"owner_password": owner_password},
            )

            if error == "unreachable":
                show_backend_unreachable()
            elif error and error.startswith("http_error"):
                message = (
                    result.get("detail", "The mandate could not be changed.")
                    if result
                    else "The mandate could not be changed."
                )
                st.error(message)
            elif error:
                st.warning(f"Could not update mandate status: {error}")
            else:
                st.success(result.get("message", success_message))
                st.rerun()

    st.divider()

    with st.expander("Danger zone: permanently revoke mandate"):
        st.warning(
            "Revoking is permanent for this running mandate. The agent will be "
            "blocked from creating all future orders, and it cannot be resumed."
        )

        revoke_confirmed = st.checkbox(
            "I understand that this permanently disables agent purchasing.",
            key="revoke_mandate_confirmed",
        )

        if st.button(
            "Permanently revoke mandate",
            key="revoke_mandate_button",
            type="secondary",
        ):
            if not revoke_confirmed:
                st.warning(
                    "Select the confirmation checkbox before revoking the mandate."
                )
            elif not owner_password:
                st.warning("Enter your password to permanently revoke the mandate.")
            else:
                result, error = backend_post(
                    "/mandate/revoke",
                    json_body={"owner_password": owner_password},
                )

                if error == "unreachable":
                    show_backend_unreachable()
                elif error and error.startswith("http_error"):
                    message = (
                        result.get("detail", "The mandate could not be revoked.")
                        if result
                        else "The mandate could not be revoked."
                    )
                    st.error(message)
                elif error:
                    st.warning(f"Could not revoke mandate: {error}")
                else:
                    st.success(
                        result.get(
                            "message",
                            "Mandate permanently revoked.",
                        )
                    )
                    st.rerun()

def render_decision_receipt(plan: dict, mandate: dict):
    """Render a downloadable decision receipt after policy evaluation."""
    if plan.get("requested_item_id") is None or plan.get("item") is None:
        return

    item = plan["item"]
    decision = plan.get("decision", "block")
    reason = plan.get("reason", "No reason provided")
    explanation = plan.get("explanation", "")

    receipt_data = {
        "timestamp": utcnow().isoformat(),
        "item_id": item["item_id"],
        "item_name": item["name"],
        "price": item["price"],
        "category": item["category"],
        "decision": decision.upper(),
        "policy_reason": reason,
        "explanation": explanation,
        "mandate_version": mandate.get("mandate_version", 1),
        "mandate_status": mandate.get("status", "active"),
        "spending_cap": mandate.get("spending_cap", 0),
        "allowed_categories": mandate.get("allowed_categories", []),
    }

    receipt_json = json.dumps(receipt_data, indent=2, default=str)

    st.download_button(
        label="Download decision receipt (JSON)",
        data=receipt_json,
        file_name=f"decision_receipt_{item['item_id']}_{utcnow().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
        width="stretch",
    )


def render_decision_receipt_pdf(plan: dict, mandate: dict):
    """
    Generate a professional, human-readable PDF receipt for a single decision.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
    )
    from io import BytesIO

    if plan.get("requested_item_id") is None or plan.get("item") is None:
        return

    item = plan["item"]
    decision = plan.get("decision", "block").upper()
    reason = plan.get("reason", "No reason provided")
    explanation = plan.get("explanation", "")

    timestamp = utcnow().strftime("%Y-%m-%d %H:%M")
    mandate_version = mandate.get("mandate_version", 1)
    mandate_status = mandate.get("status", "active").title()
    spending_cap = mandate.get("spending_cap", 0)
    allowed_categories = ", ".join(
        c.title() for c in mandate.get("allowed_categories", [])
    )

    decision_color = colors.green if decision == "BUY" else colors.red
    decision_label = "Approved" if decision == "BUY" else "Blocked"

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=colors.HexColor("#1C1917"),
        spaceAfter=12,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#1C1917"),
        spaceAfter=10,
        spaceBefore=6,
    )

    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#1C1917"),
        leading=16,
    )

    elements = []

    # Title
    elements.append(Paragraph("Bounded Agent Checkout — Decision Receipt", title_style))
    elements.append(Spacer(1, 0.15 * inch))

    # Summary table
    summary_data = [
        ["Timestamp", timestamp],
        ["Item", f"{item['name']} ({item['item_id']})"],
        ["Price", f"INR {item['price']:,.2f}"],
        ["Category", item["category"].title()],
        ["Decision", f"{decision_label} ({decision})"],
        ["Mandate version", f"v{mandate_version}"],
        ["Mandate status", mandate_status],
        ["Spending cap", f"INR {spending_cap:,.2f}"],
        ["Allowed categories", allowed_categories],
    ]

    summary_table = Table(summary_data, colWidths=[2.2 * inch, 3.3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 4), (-1, 4), decision_color),
                ("TEXTCOLOR", (0, 4), (-1, 4), colors.white),
            ]
        )
    )

    elements.append(summary_table)
    elements.append(Spacer(1, 0.25 * inch))

    # Policy reason
    elements.append(Paragraph("Policy reason", heading_style))
    elements.append(Paragraph(reason, normal_style))
    elements.append(Spacer(1, 0.15 * inch))

    # Explanation
    elements.append(Paragraph("Explanation", heading_style))
    elements.append(Paragraph(explanation, normal_style))
    elements.append(Spacer(1, 0.15 * inch))

    # What this means
    if decision == "BUY":
        meaning_text = (
            "This purchase is within your current mandate. The agent was permitted "
            "to create exactly one idempotent test order for this item. The owner "
            "may review the order and audit trail at any time."
        )
    else:
        meaning_text = (
            "This purchase was blocked by the mandate. The agent is not allowed to "
            "create an order for this request. The owner can review the reason and "
            "audit trail, and if needed adjust the mandate or choose a different item."
        )

    elements.append(Paragraph("What this means", heading_style))
    elements.append(Paragraph(meaning_text, normal_style))

    # Footer
    elements.append(Spacer(1, 0.25 * inch))
    footer_text = (
        "This receipt is generated by the Bounded Agent Checkout system. "
        "It is intended for user review and audit purposes."
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#78716C"),
        alignment=1,  # center
    )
    elements.append(Paragraph(footer_text, footer_style))

    doc.build(elements)

    buffer.seek(0)

    file_name = (
        f"decision_receipt_{item['item_id']}_{utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    )

    st.download_button(
        label="Download decision receipt (PDF)",
        data=buffer.getvalue(),
        file_name=file_name,
        mime="application/pdf",
        width="stretch",
    )

def select_template(request_text: str, template_name: str):
    """
    The callback runs before widgets render on the next Streamlit execution.
    This lets it safely populate the text input using its widget key.
    """
    st.session_state["nl_request_input"] = request_text
    st.session_state["template_message"] = (
        f"Template selected: {template_name}"
    )

    st.session_state.pop("last_plan", None)
    st.session_state.pop("last_plan_order", None)
    st.session_state.pop("last_plan_order_replay", None)
    st.session_state.pop("last_decision", None)
    st.session_state.pop("last_item_id", None)
    st.session_state.pop("last_order", None)
    st.session_state.pop("last_order_replay", None)


def render_request_templates():
    st.markdown(
        """
        <div class="section-copy">
            Use a starter request to demonstrate common agent scenarios.
            Selecting a template fills the request field only. It does not
            contact the planner, create an order, or bypass the policy gate.
        </div>
        """,
        unsafe_allow_html=True,
    )

    templates = [
        (
            "Work essentials",
            "I need a useful work accessory under ₹1000",
            "Expected: an eligible product under the stated budget.",
        ),
        (
            "Study supplies",
            "I need study supplies under ₹500",
            "Expected: a stationery product.",
        ),
        (
            "Weekly planner",
            "I need a weekly desk planner",
            "Expected: Weekly Desk Planner.",
        ),
        (
            "Video meetings",
            "I need an accessory for video meetings",
            "Expected: Full-HD Webcam.",
        ),
        (
            "Desk organisation",
            "I need something to organise my desk cables",
            "Expected: Cable Organizer Set.",
        ),
        (
            "Laptop protection",
            "I need a protective laptop sleeve",
            "Expected: Laptop Sleeve.",
        ),
        (
            "Budget block",
            "I need a mechanical keyboard",
            "Expected: policy block because the price exceeds the cap.",
        ),
        (
            "Category block",
            "I need an office chair",
            "Expected: policy block because furniture is not allowed.",
        ),
        (
            "Unavailable item",
            "I need Bluetooth headphones",
            "Expected: policy block because the item is unavailable.",
        ),
    ]

    columns = st.columns(3)

    for index, (label, request_text, help_text) in enumerate(templates):
        with columns[index % 3]:
            st.button(
                label,
                key=f"template_{index}",
                help=help_text,
                width="stretch",
                on_click=select_template,
                args=(request_text, label),
            )

    if st.session_state.get("template_message"):
        st.info(st.session_state["template_message"])


def render_agent_execution_plan(plan: dict, mandate: dict):
    """
    Displays the bounded workflow behind an agent decision.

    The LLM can recommend an item, but the deterministic backend policy gate
    independently decides whether an order may be created.
    """
    if plan.get("requested_item_id") is None or plan.get("item") is None:
        return

    item = plan["item"]
    decision_is_buy = plan.get("decision") == "buy"

    mandate_active = mandate.get("status") == "active"
    item_in_stock = item.get("in_stock", True)
    category_allowed = item.get("category") in mandate.get(
        "allowed_categories",
        [],
    )
    merchant_allowed = item.get("merchant_name", "Bounded Demo Store") in mandate.get(
        "allowed_merchants",
        [],
    )
    within_cap = item.get("price", 0) <= mandate.get("spending_cap", 0)

    def check_line(passed: bool, text: str) -> str:
        icon = "✓" if passed else "✕"
        color = "#15803D" if passed else "#B91C1C"

        return (
            f'<div style="margin: 0.35rem 0; color: {color};">'
            f"<strong>{icon}</strong> {escape(text)}"
            "</div>"
        )

    checks = [
        check_line(
            True,
            (
                "Interpret request: "
                f"{plan.get('intent_summary', 'Request interpreted.')}"
            ),
        ),
        check_line(
            True,
            (
                "Select trusted catalog item: "
                f"{item['name']} ({item['item_id']})"
            ),
        ),
        check_line(
            mandate_active,
            (
                f"Mandate status: {mandate.get('status', 'unknown').title()} "
                f"(policy version v{mandate.get('mandate_version', 1)})"
            ),
        ),
        check_line(
            item_in_stock,
            (
                "Inventory check: item is in stock"
                if item_in_stock
                else "Inventory check: item is unavailable"
            ),
        ),
        check_line(
            category_allowed,
            (
                f"Category check: '{item['category']}' is allowed"
                if category_allowed
                else f"Category check: '{item['category']}' is not allowed"
            ),
        ),

                check_line(
            merchant_allowed,
            (
                f"Merchant trust check: '{item.get('merchant_name', 'Bounded Demo Store')}' is approved"
                if merchant_allowed
                else f"Merchant trust check: '{item.get('merchant_name', 'Bounded Demo Store')}' is not approved"
            ),
        ),

        check_line(
            within_cap,
            (
                f"Per-order cap check: ₹{item['price']:,.2f} is within "
                f"₹{mandate.get('spending_cap', 0):,.2f}"
                if within_cap
                else f"Per-order cap check: ₹{item['price']:,.2f} exceeds "
                f"₹{mandate.get('spending_cap', 0):,.2f}"
            ),
        ),
        check_line(
            decision_is_buy,
            (
                "Final deterministic decision: BUY"
                if decision_is_buy
                else "Final deterministic decision: BLOCK"
            ),
        ),
    ]

    outcome_color = "#15803D" if decision_is_buy else "#B91C1C"

    outcome = (
        "Policy gate approved the action. The owner may execute exactly one "
        "idempotent test order."
        if decision_is_buy
        else "Policy gate blocked the action. The agent must stop and cannot "
        "create an order for this request."
    )

    st.markdown(
        f"""
        <div class="proposal-card" style="border-left: 4px solid {outcome_color};">
            <h3>Agent execution plan</h3>
            <div class="section-copy" style="margin-bottom: 0.6rem;">
                The LLM can recommend an item, but the deterministic policy gate
                independently checks whether the agent has permission to act.
            </div>
            {''.join(checks)}
            <div style="margin-top: 0.85rem; color: {outcome_color}; font-weight: 600;">
                {escape(outcome)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def format_notification_details(event_type: str, details: dict) -> str:
    """
    Convert audit-event dictionaries into short, readable notification text.
    Avoids showing raw JSON/Python dictionary output in the UI.
    """
    if not isinstance(details, dict):
        return str(details)

    item_id = details.get("item_id", "")
    item_name = details.get("item_name", "")
    item_price = details.get("item_price")
    reason = details.get("reason", "")
    message = details.get("message", "")

    item_label = item_name or item_id or "the selected item"

    if event_type in {"order_created", "pending_order_approved"}:
        order = details.get("order", {})
        order_id = order.get("id", "—") if isinstance(order, dict) else "—"

        price = (
            float(item_price)
            if item_price is not None
            else (
                float(order.get("amount", 0)) / 100
                if isinstance(order, dict)
                else 0.0
            )
        )

        total_spent = details.get("total_spent")
        remaining_budget = details.get("remaining_budget")

        text = (
            f"Order {order_id} was created for {item_label} "
            f"for ₹{price:,.2f}."
        )

        if total_spent is not None and remaining_budget is not None:
            text += (
                f" Total spent: ₹{float(total_spent):,.2f}. "
                f"Remaining budget: ₹{float(remaining_budget):,.2f}."
            )

        return text

    if event_type == "approval_requested":
        price = float(details.get("price", 0))
        threshold = float(details.get("approval_threshold", 0))

        text = (
            f"{item_label} requires owner approval before checkout."
        )

        if price:
            text += f" Item price: ₹{price:,.2f}."

        if threshold:
            text += f" Approval threshold: ₹{threshold:,.2f}."

        return text

    if event_type == "pending_order_cancelled":
        return (
            f"The owner cancelled the pending approval request for "
            f"{item_label}."
        )

    if event_type in {
        "order_blocked",
        "pending_order_blocked",
        "order_direct_creation_blocked",
        "pending_order_approval_blocked",
    }:
        return (
            f"Purchase for {item_label} was blocked. "
            f"Reason: {reason or message or 'It did not meet the current mandate rules.'}"
        )

    if event_type == "mandate_paused":
        return (
            f"Agent purchasing was paused. Policy version changed from "
            f"v{details.get('previous_version', '—')} to "
            f"v{details.get('new_version', '—')}."
        )

    if event_type == "mandate_resumed":
        return (
            f"Agent purchasing was resumed. Policy version changed from "
            f"v{details.get('previous_version', '—')} to "
            f"v{details.get('new_version', '—')}."
        )

    if event_type == "mandate_revoked":
        return (
            "The owner permanently revoked the mandate. "
            "Agent purchasing is disabled until a new mandate is created."
        )

    if event_type == "mandate_updated":
        changed_fields = details.get("changed_fields", {})

        if isinstance(changed_fields, dict) and changed_fields:
            readable_fields = {
                "spending_cap": "per-order cap",
                "total_budget": "total budget",
                "approval_threshold": "approval threshold",
                "allowed_categories": "allowed categories",
                "allowed_merchants": "trusted merchants",
            }

            fields = [
                readable_fields.get(field, field.replace("_", " "))
                for field in changed_fields.keys()
            ]

            return (
                f"The owner updated the mandate: {', '.join(fields)}. "
                f"The new policy version is v{details.get('mandate_version', '—')}."
            )

        return "The owner updated the mandate rules."

    if event_type == "notification_preferences_updated":
        return "Notification preferences were updated by the mandate owner."

    if message:
        return str(message)

    if reason:
        return str(reason)

    return "An auditable system event occurred."

def format_audit_details(event_type: str, details) -> str:
    """
    Convert raw audit dictionaries into short, readable table text.
    Raw details remain available in CSV/JSON export if needed.
    """
    if not isinstance(details, dict):
        return str(details)

    item_id = details.get("item_id", "")
    item_name = details.get("item_name", "")
    item_price = details.get("item_price")
    reason = details.get("reason", "")
    message = details.get("message", "")

    item_label = item_name or item_id or "the selected item"

    if event_type == "planner_request":
        return (
            f"User requested: {details.get('user_request', 'a purchase recommendation')}."
        )

    if event_type == "planner_proposal":
        proposed_item = details.get("requested_item_id")

        if proposed_item:
            return (
                f"Planner proposed {proposed_item}. "
                f"Confidence: {float(details.get('confidence', 0)):.0%}. "
                f"Reason: {details.get('selection_reason', 'No reason supplied.')}"
            )

        return (
            "Planner did not find a confident matching catalog item. "
            f"Reason: {details.get('selection_reason', 'No reason supplied.')}"
        )

    if event_type in {"policy_decision", "agent_decision", "agent_explanation"}:
        decision = str(details.get("decision", "")).upper()

        if decision:
            return (
                f"Policy decision: {decision} for {item_label}. "
                f"Reason: {reason or 'No reason supplied.'}"
            )

        return reason or message or "A policy decision was evaluated."

    if event_type in {"order_created", "pending_order_approved"}:
        order = details.get("order", {})

        if item_price is None and isinstance(order, dict):
            item_price = float(order.get("amount", 0)) / 100

        order_id = (
            order.get("id", "—")
            if isinstance(order, dict)
            else "—"
        )

        price_text = (
            f"INR {float(item_price):,.2f}"
            if item_price is not None
            else "an unspecified amount"
        )

        result = (
            f"Order created for {item_label} at {price_text}. "
            f"Order ID: {order_id}."
        )

        if (
            details.get("total_spent") is not None
            and details.get("remaining_budget") is not None
        ):
            result += (
                f" Total spent: INR {float(details['total_spent']):,.2f}. "
                f"Remaining budget: INR {float(details['remaining_budget']):,.2f}."
            )

        return result

    if event_type == "approval_requested":
        price = details.get("price", item_price)
        threshold = details.get("approval_threshold")

        result = (
            f"Owner approval requested for {item_label}."
        )

        if price is not None:
            result += f" Price: INR {float(price):,.2f}."

        if threshold is not None:
            result += f" Approval threshold: INR {float(threshold):,.2f}."

        return result

    if event_type == "pending_order_cancelled":
        return f"Owner cancelled the pending approval request for {item_label}."

    if event_type in {
        "order_blocked",
        "pending_order_blocked",
        "order_direct_creation_blocked",
        "pending_order_approval_blocked",
    }:
        return (
            f"Purchase blocked for {item_label}. "
            f"Reason: {reason or message or 'It did not meet the mandate rules.'}"
        )

    if event_type == "order_replay_returned":
        return (
            f"Duplicate request detected for {item_label}. "
            "The original idempotent order response was returned."
        )

    if event_type == "mandate_paused":
        return (
            "Owner paused agent purchasing. "
            f"Policy version changed from v{details.get('previous_version', '—')} "
            f"to v{details.get('new_version', '—')}."
        )

    if event_type == "mandate_resumed":
        return (
            "Owner resumed agent purchasing. "
            f"Policy version changed from v{details.get('previous_version', '—')} "
            f"to v{details.get('new_version', '—')}."
        )

    if event_type == "mandate_revoked":
        return (
            "Owner permanently revoked the mandate. "
            "Agent purchasing is disabled."
        )

    if event_type == "mandate_updated":
        changed_fields = details.get("changed_fields", {})

        readable_names = {
            "spending_cap": "per-order spending cap",
            "total_budget": "total budget",
            "approval_threshold": "approval threshold",
            "allowed_categories": "allowed categories",
            "allowed_merchants": "trusted merchants",
        }

        if isinstance(changed_fields, dict) and changed_fields:
            changed = [
                readable_names.get(
                    key,
                    key.replace("_", " "),
                )
                for key in changed_fields.keys()
            ]

            return (
                f"Owner updated: {', '.join(changed)}. "
                f"Policy version: v{details.get('mandate_version', '—')}."
            )

        return "Owner updated mandate rules."

    if event_type == "notification_preferences_updated":
        return "Owner updated in-app notification preferences."

    if "denied" in event_type:
        return (
            "Protected action was denied because owner verification failed."
        )

    if message:
        return str(message)

    if reason:
        return str(reason)

    return "System event recorded."

st.markdown(
    """
    <div class="page-hero">
        <h1>Bounded Agent Checkout</h1>
        <p>Safe agentic commerce with a trusted catalog, explicit spending rules, and an auditable decision trail.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


tab_mandate, tab_agent, tab_trace, tab_metrics, tab_notifications, tab_audit = st.tabs(
    [
        "Catalog",
        "Agent demo",
        "Agent trace",
        "Metrics",
        "Notifications",
        "Audit trail",
    ]
)

with tab_mandate:
    render_section(
        "Current mandate",
        (
            "The agent can propose products, but the backend authorizes only "
            "purchases within these owner-defined rules."
        ),
    )

    mandate, mandate_error = backend_get("/mandate")
    catalog, catalog_error = backend_get("/catalog")

    if mandate_error == "unreachable" or catalog_error == "unreachable":
        show_backend_unreachable()
    elif mandate_error:
        st.warning(f"Could not load mandate: {mandate_error}")
    elif catalog_error:
        st.warning(f"Could not load catalog: {catalog_error}")
    elif not catalog:
        st.info("Catalog is empty.")
    else:
        cap_column, category_column, merchant_column, expiry_column = st.columns(4)

        with cap_column:
            st.metric(
                "Per-order cap",
                f"₹{mandate['spending_cap']:,.2f}",
            )

        with category_column:
            categories = "".join(
                f'<span class="chip">{escape(category.title())}</span>'
                for category in mandate.get("allowed_categories", [])
            )

            st.markdown(
                f"""
                <div class="info-card">
                    <div class="info-label">Allowed categories</div>
                    <div class="info-value">
                        {categories or "No categories configured"}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with merchant_column:
            merchants = "".join(
                f'<span class="chip">{escape(merchant)}</span>'
                for merchant in mandate.get("allowed_merchants", [])
            )

            st.markdown(
                f"""
                <div class="info-card">
                    <div class="info-label">Trusted merchants</div>
                    <div class="info-value">
                        {merchants or "No merchants configured"}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with expiry_column:
            expiry_display = mandate["expiry"].replace(
                "T",
                " · ",
            ).split(".")[0]

            st.markdown(
                f"""
                <div class="info-card">
                    <div class="info-label">Mandate expires</div>
                    <div class="info-value">{escape(expiry_display)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        render_owner_control(mandate)

        st.divider()
        st.subheader("Mandate dashboard")

        budget = get_budget_metrics()

        if budget is None:
            st.warning("Could not load budget metrics.")
        else:
            total = budget["total_budget"]
            spent = budget["total_spent"]
            remaining = budget["remaining_budget"]
            per_order_cap = budget["per_order_cap"]
            approval_threshold = budget.get("approval_threshold", 2000.0)
            status = budget["mandate_status"].title()
            version = budget["mandate_version"]

            status_color = "#166534" if status == "Active" else "#92400E"
            status_bg = "#DCFCE7" if status == "Active" else "#FEF3C7"

            if status == "Revoked":
                status_color = "#991B1B"
                status_bg = "#FEE2E2"

            st.markdown(
                f"""
                <div class="owner-control-card">
                    <h3>Mandate overview</h3>
                    <span class="status-badge"
                        style="border: 1px solid #E7E5E4;
                        background: {status_bg};
                        color: {status_color};">
                        {escape(status)} · v{version}
                    </span>
                    <div class="section-copy" style="margin-top: 0.5rem;">
                        The agent must pass category, merchant, stock, per-order
                        cap, total-budget, and approval controls before it can act.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            row_one = st.columns(3)

            row_one[0].metric(
                "Per-order cap",
                f"₹{per_order_cap:,.2f}",
            )
            row_one[1].metric(
                "Total budget",
                f"₹{total:,.2f}",
            )
            row_one[2].metric(
                "Remaining budget",
                f"₹{remaining:,.2f}",
            )

            row_two = st.columns(3)

            row_two[0].metric(
                "Spent so far",
                f"₹{spent:,.2f}",
            )
            row_two[1].metric(
                "Owner approval threshold",
                f"₹{approval_threshold:,.2f}",
            )

            usage_pct = (spent / total * 100) if total > 0 else 0.0

            row_two[2].metric(
                "Budget usage",
                f"{usage_pct:.1f}%",
            )

            st.caption(
                "The effective order limit is the lower of the per-order cap "
                "and the remaining total budget."
            )

        st.divider()
        st.subheader("Manage mandate")
        st.caption(
            "Only the owner can change these rules. Each successful update "
            "creates a new policy version and an audit entry."
        )

        if mandate.get("status") == "revoked":
            st.error(
                "This mandate has been permanently revoked and cannot be edited. "
                "Create a new mandate to resume agent purchasing."
            )
        else:
            with st.expander("Edit mandate rules"):
                all_categories = sorted(
                    {item["category"] for item in catalog}
                )

                all_merchants = sorted(
                    {
                        item.get(
                            "merchant_name",
                            "Bounded Demo Store",
                        )
                        for item in catalog
                    }
                )

                current_categories = mandate.get(
                    "allowed_categories",
                    [],
                )
                current_merchants = mandate.get(
                    "allowed_merchants",
                    [],
                )

                edit_left, edit_right = st.columns(2)

                with edit_left:
                    edited_spending_cap = st.number_input(
                        "Per-order spending cap (₹)",
                        min_value=1.0,
                        value=float(
                            mandate.get("spending_cap", 2500.0)
                        ),
                        step=100.0,
                        key="edit_mandate_spending_cap",
                    )

                    edited_total_budget = st.number_input(
                        "Total mandate budget (₹)",
                        min_value=1.0,
                        value=float(
                            mandate.get("total_budget", 10000.0)
                        ),
                        step=500.0,
                        key="edit_mandate_total_budget",
                    )

                    edited_approval_threshold = st.number_input(
                        "Owner approval threshold (₹)",
                        min_value=1.0,
                        value=float(
                            mandate.get(
                                "approval_threshold",
                                2000.0,
                            )
                        ),
                        step=100.0,
                        key="edit_mandate_approval_threshold",
                        help=(
                            "Purchases at or above this amount become "
                            "pending owner approval requests."
                        ),
                    )

                with edit_right:
                    edited_categories = st.multiselect(
                        "Allowed categories",
                        options=all_categories,
                        default=current_categories,
                        key="edit_mandate_categories",
                    )

                    edited_merchants = st.multiselect(
                        "Trusted merchants",
                        options=all_merchants,
                        default=current_merchants,
                        key="edit_mandate_merchants",
                        help=(
                            "The backend blocks a purchase if its merchant "
                            "is outside this allowlist."
                        ),
                    )

                    edit_owner_password = st.text_input(
                        "Owner password to save changes",
                        type="password",
                        key="edit_mandate_owner_password",
                    )

                if st.button(
                    "Save mandate changes",
                    key="save_mandate_changes",
                ):
                    if not edit_owner_password:
                        st.warning(
                            "Enter the owner password to save mandate changes."
                        )
                    elif not edited_categories:
                        st.warning("Select at least one allowed category.")
                    elif not edited_merchants:
                        st.warning("Select at least one trusted merchant.")
                    elif edited_approval_threshold > edited_spending_cap:
                        st.warning(
                            "Approval threshold cannot be greater than the "
                            "per-order spending cap."
                        )
                    else:
                        payload = {
                            "owner_password": edit_owner_password,
                            "spending_cap": edited_spending_cap,
                            "total_budget": edited_total_budget,
                            "approval_threshold": edited_approval_threshold,
                            "allowed_categories": edited_categories,
                            "allowed_merchants": edited_merchants,
                        }

                        result, error = update_mandate_settings(payload)

                        if error == "unreachable":
                            show_backend_unreachable()
                        elif error and error.startswith("http_error"):
                            message = (
                                result.get(
                                    "detail",
                                    "Could not update mandate.",
                                )
                                if result
                                else "Could not update mandate."
                            )
                            st.error(message)
                        elif error:
                            st.warning(
                                f"Could not update mandate: {error}"
                            )
                        else:
                            st.success(
                                result.get(
                                    "message",
                                    "Mandate updated successfully.",
                                )
                            )
                            st.rerun()

    st.divider()

    render_section(
        "Demo merchant catalog",
        (
            "Fixed catalog data makes every decision reproducible. External "
            "reference links are informational only."
        ),
    )

    if catalog_error == "unreachable":
        show_backend_unreachable()
    elif catalog_error:
        st.warning(f"Could not load catalog: {catalog_error}")
    elif not catalog:
        st.info("Catalog is empty.")
    else:
        for start_index in range(0, len(catalog), 3):
            columns = st.columns(3)

            for column, item in zip(
                columns,
                catalog[start_index:start_index + 3],
            ):
                with column:
                    image_path = item.get("image_url")
                    product_image = (
                        load_product_image(image_path)
                        if image_path
                        else None
                    )

                    name = escape(item["name"])
                    category = escape(
                        item["category"].replace("_", " ").title()
                    )
                    merchant = escape(
                        item.get(
                            "merchant_name",
                            "Bounded Demo Store",
                        )
                    )
                    item_id = escape(item["item_id"])
                    description = escape(
                        item.get(
                            "description",
                            "No description available.",
                        )
                    )

                    stock_class = (
                        "stock-available"
                        if item.get("in_stock", True)
                        else "stock-unavailable"
                    )

                    stock_label = (
                        "In stock"
                        if item.get("in_stock", True)
                        else "Out of stock"
                    )

                    with st.container(border=True):
                        if product_image is not None:
                            st.image(product_image, width="stretch")

                        st.markdown(
                            f'<div class="product-name">{name}</div>',
                            unsafe_allow_html=True,
                        )

                        st.markdown(
                            (
                                f'<div class="product-meta">'
                                f"{merchant} · {item_id}"
                                f"</div>"
                            ),
                            unsafe_allow_html=True,
                        )

                        st.markdown(
                            (
                                f'<span class="category-badge">{category}</span>'
                                f'<span class="stock-badge {stock_class}">'
                                f"{stock_label}"
                                f"</span>"
                            ),
                            unsafe_allow_html=True,
                        )

                        st.markdown(
                            f'<div class="product-description">{description}</div>',
                            unsafe_allow_html=True,
                        )

                        st.markdown(
                            (
                                f'<div class="product-price">'
                                f'₹{item["price"]:,.2f}'
                                f"</div>"
                            ),
                            unsafe_allow_html=True,
                        )

                        if item.get("reference_url"):
                            st.link_button(
                                "View reference",
                                item["reference_url"],
                                width="stretch",
                            )

                            st.markdown(
                                (
                                    '<div class="reference-note">'
                                    "External reference only"
                                    "</div>"
                                ),
                                unsafe_allow_html=True,
                            )

with tab_agent:
    render_section(
        "Ask the agent",
        (
            "Describe what you need. The planner may suggest an item, but the "
            "deterministic mandate gate makes the final decision."
        ),
    )

    catalog, catalog_error = backend_get("/catalog")
    mandate, mandate_error = backend_get("/mandate")

    if catalog_error == "unreachable" or mandate_error == "unreachable":
        show_backend_unreachable()
    elif catalog_error:
        st.warning(f"Could not load catalog: {catalog_error}")
    elif mandate_error:
        st.warning(f"Could not load mandate: {mandate_error}")
    elif not catalog:
        st.info("Catalog is empty.")
    else:
        st.subheader("Quick demo scenarios")
        render_request_templates()

        st.subheader("Describe your need")
        nl_request = st.text_input(
            "For example: I need something for work under ₹1000",
            key="nl_request_input",
            label_visibility="collapsed",
            placeholder="I need something for work under ₹1000",
        )

        if st.button("Plan purchase", key="plan_purchase_button"):
            if not nl_request.strip():
                st.warning("Enter a request first.")
            else:
                with st.spinner(
                    "The planner is reasoning about your request. "
                    "A cold local model can take up to a minute."
                ):
                    plan_result, plan_error = backend_post(
                        f"/agent/plan?request={quote(nl_request)}",
                        timeout=PLANNER_TIMEOUT_SECONDS,
                    )

                if plan_error == "unreachable":
                    show_backend_unreachable()
                elif plan_error == "timeout":
                    show_planner_timeout()
                elif plan_error and not plan_result:
                    st.warning(f"Could not create a plan: {plan_error}")
                elif plan_result:
                    st.session_state["last_plan"] = plan_result
                    st.session_state.pop("last_plan_order", None)
                    st.session_state.pop("last_plan_order_replay", None)

        plan = st.session_state.get("last_plan")

        if plan:
            confidence = float(plan["confidence"])
            style = confidence_style(confidence)

            st.markdown(
                f"""
                <div class="proposal-card">
                    <h3>Agent proposal</h3>
                    <p><strong>Interpretation:</strong> {escape(plan["intent_summary"])}</p>
                    <span class="mode-badge">{escape(plan["planner_mode"].replace("_", " "))}</span>
                    <span class="confidence-badge confidence-{style}">Confidence {confidence:.0%}</span>
                    <div class="confidence-track">
                        <div class="confidence-fill {style}" style="width: {max(0, min(confidence * 100, 100))}%;"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if plan["requested_item_id"] is None:
                st.warning(
                    "No confident catalog match was found. "
                    "Try selecting an item directly."
                )
            else:
                item = plan["item"]

                st.markdown(
                    f"**Proposed item:** {item['name']} — "
                    f"₹{item['price']:,.2f} · {item['category'].title()}"
                )

                st.caption(
                    "The planner proposes. The deterministic mandate gate authorizes."
                )

                render_agent_execution_plan(plan, mandate)

                if plan["decision"] == "buy":
                    st.success("Purchase is within the current mandate.")
                    st.write(plan["explanation"])

                    with st.expander("Policy reason"):
                        st.code(plan["reason"])

                    render_decision_receipt(plan, mandate)
                    render_decision_receipt_pdf(plan, mandate)

                    requires_approval = bool(
                        plan.get(
                            "requires_approval",
                            item["price"]
                            >= mandate.get("approval_threshold", 2000),
                        )
                    )

                    if requires_approval:
                        st.info(
                            "This purchase is eligible but requires owner approval "
                            f"because it is at or above the ₹"
                            f"{mandate.get('approval_threshold', 2000):,.0f} threshold."
                        )

                        if st.button(
                            "Create approval request",
                            key="request_approval_from_plan",
                        ):
                            pending_result, pending_error = (
                                request_pending_approval(
                                    plan["requested_item_id"],
                                    "planner",
                                )
                            )

                            if pending_error == "unreachable":
                                show_backend_unreachable()
                            elif (
                                pending_error
                                and pending_error.startswith("http_error")
                            ):
                                message = (
                                    pending_result.get(
                                        "detail",
                                        "Could not create approval request.",
                                    )
                                    if pending_result
                                    else "Could not create approval request."
                                )
                                st.error(message)
                            elif pending_error:
                                st.warning(
                                    "Could not create approval request: "
                                    f"{pending_error}"
                                )
                            else:
                                pending = pending_result.get("pending_order", {})

                                st.success(
                                    pending_result.get(
                                        "message",
                                        "Approval request created.",
                                    )
                                )

                                if pending:
                                    st.session_state[
                                        "selected_pending_order_id"
                                    ] = pending.get("pending_id")

                                st.rerun()

                    else:
                        if st.button(
                            "Create test order",
                            key="buy_from_plan",
                        ):
                            idempotency_key = str(uuid.uuid4())

                            order_result, order_error = backend_post(
                                f"/order/create?item_id={plan['requested_item_id']}",
                                headers={
                                    "Idempotency-Key": idempotency_key
                                },
                            )

                            if order_error == "unreachable":
                                show_backend_unreachable()
                            elif (
                                order_error
                                and order_error.startswith("http_error")
                            ):
                                reason = (
                                    order_result.get(
                                        "detail",
                                        "Order was blocked.",
                                    )
                                    if order_result
                                    else "Order was blocked."
                                )
                                st.error(reason)
                            elif order_error:
                                st.warning(
                                    f"Could not create order: {order_error}"
                                )
                            else:
                                order, replay = unpack_order_response(
                                    order_result
                                )

                                if order is None:
                                    st.error(
                                        "The backend returned an invalid "
                                        "order response."
                                    )
                                else:
                                    st.session_state[
                                        "last_plan_order"
                                    ] = order
                                    st.session_state[
                                        "last_plan_order_replay"
                                    ] = replay

                    last_plan_order = st.session_state.get(
                        "last_plan_order"
                    )

                    if last_plan_order:
                        render_order(
                            last_plan_order,
                            st.session_state.get(
                                "last_plan_order_replay",
                                False,
                            ),
                        )

                else:
                    st.error("Purchase blocked by mandate.")
                    st.write(plan["explanation"])

                    with st.expander("Policy reason"):
                        st.code(plan["reason"])

                    render_decision_receipt(plan, mandate)
                    render_decision_receipt_pdf(plan, mandate)

                    alternatives = find_alternatives(
                        catalog,
                        mandate,
                        exclude_item_id=plan["requested_item_id"],
                    )

                    if alternatives:
                        st.markdown("**Alternatives within the mandate**")

                        for alternative in alternatives:
                            st.write(
                                f"• {alternative['name']} — "
                                f"₹{alternative['price']:,.2f} · "
                                f"{alternative['category'].title()}"
                            )

        st.divider()
        st.subheader("Evaluate a catalog item directly")

        options = {
            (
                f"{item['name']} — ₹{item['price']:,.2f} · "
                f"{item['category'].title()}"
            ): item["item_id"]
            for item in catalog
        }

        selected_label = st.selectbox(
            "Choose an item",
            list(options.keys()),
        )
        selected_item_id = options[selected_label]

        if st.button("Evaluate item", key="evaluate_item"):
            decision, decision_error = backend_post(
                f"/agent/explain?item_id={selected_item_id}"
            )

            if decision_error == "unreachable":
                show_backend_unreachable()
            elif decision_error and not decision:
                st.warning(f"Could not evaluate item: {decision_error}")
            elif decision:
                st.session_state["last_decision"] = decision
                st.session_state["last_item_id"] = selected_item_id
                st.session_state.pop("last_order", None)
                st.session_state.pop("last_order_replay", None)

        decision = st.session_state.get("last_decision")

        if (
            decision
            and st.session_state.get("last_item_id") == selected_item_id
        ):
            direct_item = next(
                (
                    item
                    for item in catalog
                    if item["item_id"] == selected_item_id
                ),
                None,
            )

            if direct_item is None:
                st.error("The selected item could not be found in the catalog.")
            else:
                direct_plan = {
                    "requested_item_id": selected_item_id,
                    "item": direct_item,
                    "decision": decision["decision"],
                    "reason": decision["reason"],
                    "explanation": decision["explanation"],
                    "intent_summary": (
                        f"Direct evaluation requested for {selected_item_id}."
                    ),
                }

                render_agent_execution_plan(direct_plan, mandate)

                if decision["decision"] == "buy":
                    st.success("Purchase is within the current mandate.")
                    st.write(decision["explanation"])

                    with st.expander("Policy reason"):
                        st.code(decision["reason"])

                    render_decision_receipt(direct_plan, mandate)
                    render_decision_receipt_pdf(direct_plan, mandate)

                    requires_approval = bool(
                        decision.get(
                            "requires_approval",
                            direct_item["price"]
                            >= mandate.get("approval_threshold", 2000),
                        )
                    )

                    if requires_approval:
                        st.info(
                            "This purchase is eligible but requires owner approval "
                            f"because it is at or above the ₹"
                            f"{mandate.get('approval_threshold', 2000):,.0f} threshold."
                        )

                        if st.button(
                            "Create approval request",
                            key="request_approval_direct",
                        ):
                            pending_result, pending_error = (
                                request_pending_approval(
                                    selected_item_id,
                                    "direct",
                                )
                            )

                            if pending_error == "unreachable":
                                show_backend_unreachable()
                            elif (
                                pending_error
                                and pending_error.startswith("http_error")
                            ):
                                message = (
                                    pending_result.get(
                                        "detail",
                                        "Could not create approval request.",
                                    )
                                    if pending_result
                                    else "Could not create approval request."
                                )
                                st.error(message)
                            elif pending_error:
                                st.warning(
                                    "Could not create approval request: "
                                    f"{pending_error}"
                                )
                            else:
                                pending = pending_result.get("pending_order", {})

                                st.success(
                                    pending_result.get(
                                        "message",
                                        "Approval request created.",
                                    )
                                )

                                if pending:
                                    st.session_state[
                                        "selected_pending_order_id"
                                    ] = pending.get("pending_id")

                                st.rerun()

                    else:
                        if st.button(
                            "Create test order",
                            key="buy_direct",
                        ):
                            idempotency_key = str(uuid.uuid4())

                            order_result, order_error = backend_post(
                                f"/order/create?item_id={selected_item_id}",
                                headers={
                                    "Idempotency-Key": idempotency_key
                                },
                            )

                            if order_error == "unreachable":
                                show_backend_unreachable()
                            elif (
                                order_error
                                and order_error.startswith("http_error")
                            ):
                                reason = (
                                    order_result.get(
                                        "detail",
                                        "Order was blocked.",
                                    )
                                    if order_result
                                    else "Order was blocked."
                                )
                                st.error(reason)
                            elif order_error:
                                st.warning(
                                    f"Could not create order: {order_error}"
                                )
                            else:
                                order, replay = unpack_order_response(
                                    order_result
                                )

                                if order is None:
                                    st.error(
                                        "The backend returned an invalid "
                                        "order response."
                                    )
                                else:
                                    st.session_state["last_order"] = order
                                    st.session_state[
                                        "last_order_replay"
                                    ] = replay

                    last_order = st.session_state.get("last_order")

                    if last_order:
                        render_order(
                            last_order,
                            st.session_state.get(
                                "last_order_replay",
                                False,
                            ),
                        )

                else:
                    st.error("Purchase blocked by mandate.")
                    st.write(decision["explanation"])

                    with st.expander("Policy reason"):
                        st.code(decision["reason"])

                    render_decision_receipt(direct_plan, mandate)
                    render_decision_receipt_pdf(direct_plan, mandate)

                    alternatives = find_alternatives(
                        catalog,
                        mandate,
                        exclude_item_id=selected_item_id,
                    )

                    if alternatives:
                        st.markdown("**Alternatives within the mandate**")

                        for alternative in alternatives:
                            st.write(
                                f"• {alternative['name']} — "
                                f"₹{alternative['price']:,.2f} · "
                                f"{alternative['category'].title()}"
                            )

        st.divider()
        st.subheader("Pending owner approvals")
        st.caption(
            "High-value purchases never create an order automatically. "
            "The owner can explicitly approve or cancel each pending request."
        )

        pending_orders, pending_error = get_pending_orders()

        if pending_error == "unreachable":
            show_backend_unreachable()
        elif pending_error:
            st.warning(
                f"Could not load pending approval requests: {pending_error}"
            )
        elif not pending_orders:
            st.info("No pending approval requests.")
        else:
            active_pending_orders = [
                pending
                for pending in pending_orders
                if pending.get("status") == "pending"
            ]

            if not active_pending_orders:
                st.info("No approval requests are currently waiting for action.")
            else:
                pending_options = {
                    (
                        f"{pending['item_name']} — ₹{pending['price']:,.2f} "
                        f"· {pending['pending_id']}"
                    ): pending["pending_id"]
                    for pending in active_pending_orders
                }

                selected_pending_label = st.selectbox(
                    "Select a pending approval request",
                    list(pending_options.keys()),
                    key="pending_order_selector",
                )

                selected_pending_id = pending_options[selected_pending_label]

                selected_pending = next(
                    (
                        pending
                        for pending in active_pending_orders
                        if pending["pending_id"] == selected_pending_id
                    ),
                    None,
                )

                if selected_pending:
                    st.markdown(
                        f"""
                        <div class="proposal-card">
                            <h3>Pending approval request</h3>
                            <p><strong>Item:</strong> {escape(selected_pending["item_name"])}</p>
                            <p><strong>Price:</strong> ₹{selected_pending["price"]:,.2f}</p>
                            <p><strong>Category:</strong> {escape(selected_pending["category"].title())}</p>
                            <p><strong>Merchant:</strong> {escape(selected_pending["merchant_name"])}</p>
                            <p><strong>Requested:</strong> {escape(selected_pending["created_at"])}</p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    pending_password = st.text_input(
                        "Owner password for this pending request",
                        type="password",
                        key="pending_order_owner_password",
                    )

                    approve_column, cancel_column = st.columns(2)

                    with approve_column:
                        if st.button(
                            "Approve and create order",
                            key="approve_pending_order",
                        ):
                            if not pending_password:
                                st.warning(
                                    "Enter the owner password before approval."
                                )
                            else:
                                result, error = backend_post(
                                    f"/orders/pending/{selected_pending_id}/approve",
                                    json_body={
                                        "owner_password": pending_password
                                    },
                                )

                                if error == "unreachable":
                                    show_backend_unreachable()
                                elif (
                                    error
                                    and error.startswith("http_error")
                                ):
                                    message = (
                                        result.get(
                                            "detail",
                                            "Could not approve the request.",
                                        )
                                        if result
                                        else "Could not approve the request."
                                    )
                                    st.error(message)
                                elif error:
                                    st.warning(
                                        f"Could not approve request: {error}"
                                    )
                                else:
                                    order, _ = unpack_order_response(result)

                                    if order:
                                        st.session_state[
                                            "last_pending_order_result"
                                        ] = order

                                    st.success(
                                        "Owner approval recorded. "
                                        "Test order created."
                                    )
                                    st.rerun()

                    with cancel_column:
                        if st.button(
                            "Cancel pending request",
                            key="cancel_pending_order",
                        ):
                            if not pending_password:
                                st.warning(
                                    "Enter the owner password before cancellation."
                                )
                            else:
                                result, error = backend_post(
                                    f"/orders/pending/{selected_pending_id}/cancel",
                                    json_body={
                                        "owner_password": pending_password
                                    },
                                )

                                if error == "unreachable":
                                    show_backend_unreachable()
                                elif (
                                    error
                                    and error.startswith("http_error")
                                ):
                                    message = (
                                        result.get(
                                            "detail",
                                            "Could not cancel the request.",
                                        )
                                        if result
                                        else "Could not cancel the request."
                                    )
                                    st.error(message)
                                elif error:
                                    st.warning(
                                        f"Could not cancel request: {error}"
                                    )
                                else:
                                    st.success(
                                        result.get(
                                            "message",
                                            "Pending request cancelled.",
                                        )
                                    )
                                    st.rerun()

        last_pending_order_result = st.session_state.get(
            "last_pending_order_result"
        )

        if last_pending_order_result:
            st.divider()
            st.subheader("Latest approved pending order")
            render_order(last_pending_order_result)

with tab_trace:
    render_section(
        "Agent trace",
        "A readable sequence of requests, proposals, policy decisions, and order outcomes.",
    )

    limit = st.number_input(
        "Events to show",
        min_value=1,
        value=10,
        step=5,
    )

    if st.button("Refresh trace"):
        st.session_state["trace_limit"] = int(limit)

    trace_limit = st.session_state.get("trace_limit", int(limit))
    trace, trace_error = backend_get(f"/agent/trace?limit={trace_limit}")

    if trace_error == "unreachable":
        show_backend_unreachable()
    elif trace_error:
        st.warning(f"Could not load trace: {trace_error}")
    elif not trace:
        st.info("No activity yet. Run a planner request or evaluate an item first.")
    else:
        for step in trace:
            details = str(step.get("details", ""))
            event_type = step.get("event_type", "")
            is_block = event_type == "order_blocked" or "BLOCK" in details
            is_success = event_type == "order_created" or "BUY" in details

            accent = (
                "#B91C1C"
                if is_block
                else "#15803D"
                if is_success
                else "#2563EB"
            )

            st.markdown(
                f"""
                <div class="trace-card" style="border-left: 4px solid {accent};">
                    <h3>Step {escape(str(step.get("step", "—")))} · {escape(str(step.get("action", "Event")))}</h3>
                    <p>{escape(details)}</p>
                    <div class="product-meta">{escape(str(step.get("timestamp", "")))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


with tab_metrics:
    render_section(
        "Metrics",
        "All figures are synthetic engineering-validation results, not real-user, revenue, or conversion results.",
    )

    if st.button("Refresh metrics"):
        st.rerun()

    st.subheader("1. Runtime decisions")
    runtime_metrics, runtime_error = backend_get("/metrics")

    if runtime_error == "unreachable":
        show_backend_unreachable()
    elif runtime_error:
        st.warning(f"Could not load runtime metrics: {runtime_error}")
    elif runtime_metrics:
        first_row = st.columns(3)

        first_row[0].metric(
            "Purchase attempts",
            runtime_metrics["total_purchase_attempts"],
        )
        first_row[1].metric("Buy decisions", runtime_metrics["buy_count"])
        first_row[2].metric("Block decisions", runtime_metrics["block_count"])

        second_row = st.columns(3)
        block_rate = runtime_metrics["block_rate_percent"]
        latency = runtime_metrics["avg_gate_latency_ms"]

        second_row[0].metric(
            "Block rate",
            f"{block_rate}%" if block_rate is not None else "No attempts yet",
        )
        second_row[1].metric(
            "Average gate latency",
            f"{latency} ms" if latency is not None else "Not available",
        )
        second_row[2].metric(
            "Decision previews",
            runtime_metrics["decision_preview_count"],
        )

        st.caption(runtime_metrics["methodology_note"])

    st.divider()
    st.subheader("2. Policy validation")
    st.caption(
        "Past decisions are independently re-checked against a separate policy implementation."
    )

    policy_metrics, policy_error = backend_get("/metrics/policy")

    if policy_error == "unreachable":
        show_backend_unreachable()
    elif policy_error:
        st.warning(f"Could not load policy metrics: {policy_error}")
    elif policy_metrics:
        policy_columns = st.columns(3)

        policy_columns[0].metric(
            "Decisions validated",
            policy_metrics["total_validated"],
        )
        policy_columns[1].metric(
            "Correct decisions",
            policy_metrics["correct_decisions"],
        )

        policy_accuracy = policy_metrics["policy_accuracy_percent"]

        policy_columns[2].metric(
            "Policy accuracy",
            (
                f"{policy_accuracy}%"
                if policy_accuracy is not None
                else "No data yet"
            ),
        )

        if policy_metrics["mismatches"]:
            st.error(f"{len(policy_metrics['mismatches'])} mismatch(es) found.")
            st.json(policy_metrics["mismatches"])
        else:
            st.success("No mismatches found in validated decisions.")

    st.divider()
    st.subheader("3. Security validation")
    st.caption(
        "Counts deliberate adversarial test runs only, not ordinary planner misses."
    )

    adversarial_metrics, adversarial_error = backend_get("/metrics/adversarial")

    if adversarial_error == "unreachable":
        show_backend_unreachable()
    elif adversarial_error:
        st.warning(f"Could not load adversarial metrics: {adversarial_error}")
    elif adversarial_metrics:
        if adversarial_metrics["total_attempts"] == 0:
            st.info(
                "No adversarial test run recorded yet. "
                "Run `python run_adversarial_tests.py`."
            )
        else:
            security_columns = st.columns(3)

            security_columns[0].metric(
                "Adversarial attempts",
                adversarial_metrics["total_attempts"],
            )
            security_columns[1].metric(
                "Blocked",
                adversarial_metrics["blocked_count"],
            )

            attack_rate = adversarial_metrics["attack_success_rate_percent"]

            security_columns[2].metric(
                "Attack success rate",
                f"{attack_rate}%" if attack_rate is not None else "—",
            )

            if adversarial_metrics["success_count"] > 0:
                st.error(
                    f"{adversarial_metrics['success_count']} "
                    "adversarial attempt(s) succeeded."
                )

    st.divider()
    st.subheader("4. Validation suite")
    st.caption(
        "Named test cases cover allowed purchases, blocks, planner safety, "
        "adversarial input, and recovery."
    )

    validation_results, validation_error = backend_get("/validation/results")

    if validation_error == "unreachable":
        show_backend_unreachable()
    elif validation_error:
        st.warning(f"Could not load validation results: {validation_error}")
    elif validation_results and not validation_results.get("available"):
        st.info(validation_results.get("message", "No validation results yet."))
    elif validation_results:
        validation_columns = st.columns(3)

        validation_columns[0].metric(
            "Total cases",
            validation_results["total_cases"],
        )
        validation_columns[1].metric("Passed", validation_results["passed"])
        validation_columns[2].metric("Failed", validation_results["failed"])

        st.caption(f"Last run: {validation_results['timestamp']}")

        if validation_results["failed"] > 0:
            st.error(f"{validation_results['failed']} case(s) are failing.")
        else:
            st.success("All named validation cases are passing.")

        with st.expander("By category"):
            for category, stats in validation_results["by_category"].items():
                st.write(
                    f"**{category}:** {stats['passed']}/{stats['total']} passed"
                )

        with st.expander(
            "Case-by-case results",
            expanded=validation_results["failed"] > 0,
        ):
            rows = [
                {
                    "ID": result["id"],
                    "Name": result["name"],
                    "Category": result["category"],
                    "Status": result["status"],
                    "Reason": result["reason"],
                }
                for result in validation_results["results"]
            ]

            st.dataframe(rows, width="stretch", hide_index=True)

with tab_notifications:
    render_section(
        "Notifications",
        (
            "Review important agent, approval, order, and mandate events. "
            "These are generated from the auditable backend event trail."
        ),
    )

    refresh_left, refresh_right = st.columns(2)

    with refresh_left:
        if st.button(
            "Refresh notifications",
            key="refresh_notifications",
        ):
            st.rerun()

    with refresh_right:
        notification_limit = st.selectbox(
            "Events to show",
            options=[10, 20, 50],
            index=1,
            key="notification_limit",
        )

    notification_data, notification_error = get_notifications(
        int(notification_limit)
    )

    if notification_error == "unreachable":
        show_backend_unreachable()
    elif notification_error:
        st.warning(
            f"Could not load notifications: {notification_error}"
        )
    elif not notification_data:
        st.info("No notifications are available yet.")
    else:
        preferences = notification_data.get("preferences", {})
        notifications = notification_data.get("notifications", [])

        if not notifications:
            st.info(
                "No notifications match the current preferences yet. "
                "Run an agent request, create an approval request, create "
                "an order, or update the mandate."
            )
        else:
            for notification in notifications:
                event_type = notification.get("event_type", "event")
                timestamp = notification.get("timestamp", "")
                details = notification.get("details", {})

                details_text = format_notification_details(
                    event_type,
                    details,
                )
                is_block = (
                    "blocked" in event_type
                    or "denied" in event_type
                    or "revoked" in event_type
                    or "cancelled" in event_type
                )

                is_approval = event_type == "approval_requested"

                is_success = (
                    "created" in event_type
                    or "approved" in event_type
                    or "resumed" in event_type
                    or "updated" in event_type
                )

                is_paused = event_type == "mandate_paused"

                if is_block:
                    icon = "🔴"
                elif is_approval or is_paused:
                    icon = "🟡"
                elif is_success:
                    icon = "🟢"
                else:
                    icon = "🔵"
                is_approval = (
                    event_type == "approval_requested"
                )
                is_success = (
                    "created" in event_type
                    or "approved" in event_type
                    or "resumed" in event_type
                    or "updated" in event_type
                )

                icon = "🔴" if is_block else "🟡" if is_approval else "🟢" if is_success else "🔵"

                event_label = event_type.replace("_", " ").title()

                st.markdown(
                    f"""
                    <div class="trace-card">
                        <h3>{icon} {escape(event_label)}</h3>
                        <p>{escape(details_text)}</p>
                        <div class="product-meta">{escape(timestamp)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.divider()
    st.subheader("Notification preferences")
    st.caption(
        "Choose which audit events should appear in this in-app notification feed. "
        "Only the mandate owner can change these preferences."
    )

    preferences, preferences_error = get_notification_preferences()

    if preferences_error == "unreachable":
        show_backend_unreachable()
    elif preferences_error:
        st.warning(
            f"Could not load notification preferences: {preferences_error}"
        )
    elif preferences:
        with st.expander("Edit notification preferences"):
            preference_left, preference_right = st.columns(2)

            with preference_left:
                notify_on_block = st.checkbox(
                    "Notify when a purchase is blocked",
                    value=bool(
                        preferences.get("notify_on_block", True)
                    ),
                    key="notify_on_block",
                )

                notify_on_approval_required = st.checkbox(
                    "Notify when owner approval is required",
                    value=bool(
                        preferences.get(
                            "notify_on_approval_required",
                            True,
                        )
                    ),
                    key="notify_on_approval_required",
                )

            with preference_right:
                notify_on_order_created = st.checkbox(
                    "Notify when an order is created",
                    value=bool(
                        preferences.get("notify_on_order_created", True)
                    ),
                    key="notify_on_order_created",
                )

                notify_on_mandate_changes = st.checkbox(
                    "Notify when mandate rules change",
                    value=bool(
                        preferences.get(
                            "notify_on_mandate_changes",
                            True,
                        )
                    ),
                    key="notify_on_mandate_changes",
                )

                notification_owner_password = st.text_input(
                    "Owner password to save notification preferences",
                    type="password",
                    key="notification_preferences_owner_password",
                )

            if st.button(
                "Save notification preferences",
                key="save_notification_preferences",
            ):
                if not notification_owner_password:
                    st.warning(
                        "Enter the owner password to save notification preferences."
                    )
                else:
                    payload = {
                        "owner_password": notification_owner_password,
                        "notify_on_block": notify_on_block,
                        "notify_on_approval_required": (
                            notify_on_approval_required
                        ),
                        "notify_on_order_created": (
                            notify_on_order_created
                        ),
                        "notify_on_mandate_changes": (
                            notify_on_mandate_changes
                        ),
                    }

                    result, save_error = update_notification_preferences(
                        payload
                    )

                    if save_error == "unreachable":
                        show_backend_unreachable()
                    elif (
                        save_error
                        and save_error.startswith("http_error")
                    ):
                        message = (
                            result.get(
                                "detail",
                                "Could not update notification preferences.",
                            )
                            if result
                            else "Could not update notification preferences."
                        )
                        st.error(message)
                    elif save_error:
                        st.warning(
                            "Could not update notification preferences: "
                            f"{save_error}"
                        )
                    else:
                        st.success(
                            result.get(
                                "message",
                                "Notification preferences updated.",
                            )
                        )
                        st.rerun()

with tab_audit:
    render_section(
        "Audit trail",
        "Every planner request, policy decision, and order action is recorded here.",
    )

    if st.button("Refresh audit trail"):
        st.rerun()

    audit_log, audit_error = backend_get("/audit")

    if audit_error == "unreachable":
        show_backend_unreachable()
    elif audit_error:
        st.warning(f"Could not load audit trail: {audit_error}")
    elif not audit_log:
        st.info("No audit events yet.")
    else:
        st.markdown(
            """
            <div class="section-copy">
                Filter the audit trail to focus on specific events, decisions, items, or time ranges.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Build a list of distinct event types
        event_types = sorted(
            {entry.get("event_type", "unknown") for entry in audit_log}
        )

        # Date range helpers
        def parse_ts(entry: dict):
            ts = entry.get("timestamp", "")
            if not ts:
                return None
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return None

        timestamps = [parse_ts(e) for e in audit_log]
        timestamps = [t for t in timestamps if t is not None]

        min_date = min(timestamps).date() if timestamps else None
        max_date = max(timestamps).date() if timestamps else None

        filters_left, filters_right = st.columns(2)

        with filters_left:
            selected_event_types = st.multiselect(
                "Event type",
                options=event_types,
                default=event_types,
                help="Filter by one or more event types.",
            )

            decision_options = ["All", "BUY", "BLOCK"]
            selected_decision = st.selectbox(
                "Decision",
                options=decision_options,
                index=0,
                help="Filter by BUY or BLOCK decisions (where applicable).",
            )

        with filters_right:
            search_text = st.text_input(
                "Search item ID or name",
                value="",
                help="Case-insensitive search in event details.",
            )

            date_cols = st.columns(2)

            with date_cols[0]:
                date_from = st.date_input(
                    "From",
                    value=min_date,
                    min_value=min_date,
                    max_value=max_date,
                    help="Start date for the audit filter.",
                )

            with date_cols[1]:
                date_to = st.date_input(
                    "To",
                    value=max_date,
                    min_value=min_date,
                    max_value=max_date,
                    help="End date for the audit filter.",
                )

        # Apply filters
        filtered = []

        for entry in audit_log:
            event_type = entry.get("event_type", "unknown")

            if event_type not in selected_event_types:
                continue

            details_str = str(entry.get("details", ""))

            if selected_decision != "All":
                if selected_decision not in details_str.upper():
                    continue

            if search_text.strip():
                if search_text.lower() not in details_str.lower():
                    continue

            ts = parse_ts(entry)
            if ts is not None:
                event_date = ts.date()
                if event_date < date_from or event_date > date_to:
                    continue

            filtered.append(entry)

        # Show active filter summary
        active_filters = []

        if set(selected_event_types) != set(event_types):
            active_filters.append(
                f"event types: {', '.join(selected_event_types)}"
            )

        if selected_decision != "All":
            active_filters.append(f"decision: {selected_decision}")

        if search_text.strip():
            active_filters.append(f"search: {search_text}")

        if date_from != min_date or date_to != max_date:
            active_filters.append(
                f"date range: {date_from} to {date_to}"
            )

        if active_filters:
            st.caption(
                "Active filters: " + "; ".join(active_filters)
            )

        st.divider()

        st.markdown(
            """
            <div class="section-copy">
                Download the filtered audit trail for external review.
            </div>
            """,
            unsafe_allow_html=True,
        )

        csv_buffer = io.StringIO()

        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=["timestamp", "event_type", "details"],
        )
        writer.writeheader()

        for entry in filtered:
            writer.writerow(
                {
                    "timestamp": entry.get("timestamp", ""),
                    "event_type": entry.get("event_type", ""),
                    "details": str(entry.get("details", "")),
                }
            )

        export_timestamp = utcnow().strftime("%Y%m%d_%H%M%S")

        export_left, export_right = st.columns(2)

        with export_left:
            st.download_button(
                label="Download filtered audit log as CSV",
                data=csv_buffer.getvalue(),
                file_name=f"bounded_agent_audit_filtered_{export_timestamp}.csv",
                mime="text/csv",
                width="stretch",
            )

        with export_right:
            st.download_button(
                label="Download filtered audit log as JSON",
                data=json.dumps(filtered, indent=2, default=str),
                file_name=f"bounded_agent_audit_filtered_{export_timestamp}.json",
                mime="application/json",
                width="stretch",
            )

        st.divider()

        if not filtered:
            st.info("No audit events match the current filters.")
        else:
            audit_rows = [
                {
                    "Timestamp": entry.get("timestamp", ""),
                    "Event type": entry.get("event_type", "")
                    .replace("_", " ")
                    .title(),
                    "Details": format_audit_details(
                        entry.get("event_type", ""),
                        entry.get("details", {}),
                    ),
                }
                for entry in reversed(filtered)
            ]

            st.dataframe(audit_rows, width="stretch", hide_index=True)