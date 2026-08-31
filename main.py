from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional
import hmac
import json
import time
import uuid

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import adversarial_tests
import agent_explainer
import agent_trace
import audit_store
import metrics
import policy_simulator
import shopping_planner

from config import (
    DEFAULT_CURRENCY,
    MANDATE_OWNER_PASSWORD,
    RAZORPAY_CONFIGURED,
    RAZORPAY_KEY_ID,
)
from razorpay_client import create_test_order


def utcnow() -> datetime:
    from datetime import datetime as _dt, timezone as _tz

    return _dt.now(_tz.utc).replace(tzinfo=None)


app = FastAPI(
    title="Bounded Agent Checkout",
    description=(
        "A bounded agent checkout system with deterministic mandate enforcement."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Mandate(BaseModel):
    spending_cap: float
    allowed_categories: list[str]
    allowed_merchants: list[str]
    expiry: datetime
    status: Literal["active", "paused", "revoked"] = "active"
    mandate_version: int = 1
    total_budget: float = 10000.0
    approval_threshold: float = 2000.0


class OwnerConfirmationRequest(BaseModel):
    owner_password: str = Field(..., min_length=1)


class MandateUpdateRequest(BaseModel):
    owner_password: str = Field(..., min_length=1)
    spending_cap: float = Field(..., gt=0)
    total_budget: float = Field(..., gt=0)
    approval_threshold: float = Field(..., gt=0)
    allowed_categories: list[str] = Field(..., min_length=1)
    allowed_merchants: list[str] = Field(..., min_length=1)


class MandateStatusResponse(BaseModel):
    mandate: Mandate
    message: str


class IdempotentOrderResponse(BaseModel):
    order: dict
    idempotent_replay: bool


class CatalogItem(BaseModel):
    item_id: str
    name: str
    price: float
    category: str
    description: str
    image_url: Optional[str] = None
    reference_url: Optional[str] = None
    in_stock: bool = True
    merchant_name: str = "Bounded Demo Store"


class AgentDecision(BaseModel):
    item_id: str
    decision: Literal["buy", "block"]
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentExplanation(BaseModel):
    item_id: str
    decision: Literal["buy", "block"]
    reason: str
    explanation: str
    requires_approval: bool = False
    approval_threshold: float = 2000.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentPlanResponse(BaseModel):
    user_request: str
    requested_item_id: Optional[str]
    intent_summary: str
    selection_reason: str
    planner_mode: Literal["ollama", "rule_based_fallback"]
    confidence: float
    item: Optional[CatalogItem] = None
    decision: Optional[Literal["buy", "block"]] = None
    reason: Optional[str] = None
    explanation: Optional[str] = None
    requires_approval: bool = False
    approval_threshold: float = 2000.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PendingOrderRequest(BaseModel):
    item_id: str
    source: Literal["planner", "direct"] = "direct"


class PendingOrderActionRequest(BaseModel):
    owner_password: str = Field(..., min_length=1)


class PendingOrderResponse(BaseModel):
    pending_order: dict
    message: str


class PendingOrderListResponse(BaseModel):
    pending_orders: list[dict]


class NotificationPreferences(BaseModel):
    notify_on_block: bool = True
    notify_on_approval_required: bool = True
    notify_on_order_created: bool = True
    notify_on_mandate_changes: bool = True


class NotificationPreferencesUpdateRequest(BaseModel):
    owner_password: str = Field(..., min_length=1)
    notify_on_block: bool
    notify_on_approval_required: bool
    notify_on_order_created: bool
    notify_on_mandate_changes: bool


class NotificationPreferencesResponse(BaseModel):
    preferences: NotificationPreferences
    message: str


CATALOG = [
    CatalogItem(
        item_id="ITM001",
        name="Wireless Mouse",
        price=799.0,
        category="electronics",
        description="Compact wireless mouse for everyday work and study.",
        image_url="frontend/assets/wireless-mouse.jpeg",
        reference_url="https://www.amazon.in/s?k=wireless+mouse",
    ),
    CatalogItem(
        item_id="ITM002",
        name="USB-C Multiport Hub",
        price=1299.0,
        category="electronics",
        description="HDMI, USB-A, and USB-C expansion for a work laptop.",
        image_url="frontend/assets/usb-c-hub.jpeg",
        reference_url="https://www.amazon.in/s?k=usb+c+hub",
    ),
    CatalogItem(
        item_id="ITM003",
        name="Laptop Sleeve, 14-inch",
        price=699.0,
        category="electronics",
        description="Protective laptop sleeve with a soft inner lining.",
        image_url="frontend/assets/laptop-sleeve.jpeg",
        reference_url="https://www.flipkart.com/search?q=14+inch+laptop+sleeve",
    ),
    CatalogItem(
        item_id="ITM004",
        name="Wireless Charging Pad",
        price=899.0,
        category="electronics",
        description="Compact wireless charger for a compatible phone.",
        image_url="frontend/assets/wireless-charger.jpeg",
        reference_url="https://www.amazon.in/s?k=wireless+charging+pad",
    ),
    CatalogItem(
        item_id="ITM005",
        name="Full-HD Webcam",
        price=1899.0,
        category="electronics",
        description="1080p webcam for meetings, classes, and remote work.",
        image_url="frontend/assets/webcam.jpeg",
        reference_url="https://www.amazon.in/s?k=1080p+webcam",
    ),
    CatalogItem(
        item_id="ITM006",
        name="Notebook Set, Pack of 3",
        price=249.0,
        category="stationery",
        description="Three ruled notebooks for notes, sketches, and planning.",
        image_url="frontend/assets/notebook-set.jpeg",
        reference_url="https://www.amazon.in/s?k=notebook+set+pack+of+3",
    ),
    CatalogItem(
        item_id="ITM007",
        name="Gel Pen Set",
        price=299.0,
        category="stationery",
        description="Smooth-writing black and blue gel pens for daily use.",
        image_url="frontend/assets/gel-pen-set.jpeg",
        reference_url="https://www.flipkart.com/search?q=gel+pen+set",
    ),
    CatalogItem(
        item_id="ITM008",
        name="Weekly Desk Planner",
        price=349.0,
        category="stationery",
        description="Undated weekly planner for work priorities and tasks.",
        image_url="frontend/assets/weekly-planner.jpeg",
        reference_url="https://www.amazon.in/s?k=weekly+desk+planner",
    ),
    CatalogItem(
        item_id="ITM009",
        name="LED Desk Lamp",
        price=599.0,
        category="lifestyle",
        description="Adjustable LED desk lamp with warm and cool light modes.",
        image_url="frontend/assets/desk-lamp.jpeg",
        reference_url="https://www.amazon.in/s?k=led+desk+lamp",
    ),
    CatalogItem(
        item_id="ITM010",
        name="Insulated Water Bottle",
        price=349.0,
        category="lifestyle",
        description="Stainless-steel bottle for daily work and travel.",
        image_url="frontend/assets/water-bottle.jpeg",
        reference_url="https://www.blinkit.com/s/?q=water+bottle",
    ),
    CatalogItem(
        item_id="ITM011",
        name="Cable Organizer Set",
        price=299.0,
        category="lifestyle",
        description="Reusable cable ties and clips for a tidy desk.",
        image_url="frontend/assets/cable-organizer.jpeg",
        reference_url="https://www.amazon.in/s?k=cable+organizer",
    ),
    CatalogItem(
        item_id="ITM012",
        name="Ergonomic Mouse Pad",
        price=449.0,
        category="lifestyle",
        description="Wrist-support mouse pad for comfortable desk work.",
        image_url="frontend/assets/mouse-pad.jpeg",
        reference_url="https://www.flipkart.com/search?q=ergonomic+mouse+pad",
    ),
    CatalogItem(
        item_id="ITM013",
        name="Mechanical Keyboard",
        price=3499.0,
        category="electronics",
        description="Price exceeds the current mandate cap.",
        image_url="frontend/assets/mechanical-keyboard.jpeg",
        reference_url="https://www.amazon.in/s?k=mechanical+keyboard",
    ),
    CatalogItem(
        item_id="ITM014",
        name="Portable SSD, 1TB",
        price=4999.0,
        category="electronics",
        description="High-value item that exceeds the current mandate cap.",
        image_url="frontend/assets/portable-ssd.jpeg",
        reference_url="https://www.amazon.in/s?k=portable+ssd+1tb",
    ),
    CatalogItem(
        item_id="ITM015",
        name="Office Chair",
        price=8999.0,
        category="furniture",
        description="Furniture is outside the current mandate.",
        image_url="frontend/assets/office-chair.jpeg",
        reference_url="https://www.flipkart.com/search?q=office+chair",
    ),
    CatalogItem(
        item_id="ITM016",
        name="Smartwatch",
        price=2299.0,
        category="wearables",
        description="Wearables are not an allowed category.",
        image_url="frontend/assets/smartwatch.jpeg",
        reference_url="https://www.amazon.in/s?k=smartwatch",
    ),
    CatalogItem(
        item_id="ITM017",
        name="Bluetooth Headphones",
        price=2199.0,
        category="electronics",
        description="Currently unavailable.",
        image_url="frontend/assets/bluetooth-headphones.jpeg",
        reference_url="https://www.amazon.in/s?k=bluetooth+headphones",
        in_stock=False,
    ),
    CatalogItem(
        item_id="ITM018",
        name="Ergonomic Laptop Stand",
        price=2199.0,
        category="electronics",
        description="Adjustable aluminium laptop stand for a healthier desk setup.",
        image_url="frontend/assets/Ergonomic Laptop Stand.jpeg",
        reference_url="https://www.amazon.in/s?k=ergonomic+laptop+stand",
    ),
]


TOTAL_BUDGET = 10000.0
APPROVAL_THRESHOLD = 2000.0

_SPENT_STORE: dict[str, float] = {
    "total_spent": 0.0,
}

_IDEMPOTENCY_STORE: dict[str, dict] = {}

_PENDING_ORDERS: dict[str, dict] = {}

_NOTIFICATION_PREFERENCES = NotificationPreferences()


CURRENT_MANDATE = Mandate(
    spending_cap=2500.0,
    allowed_categories=["electronics", "stationery", "lifestyle"],
    allowed_merchants=["Bounded Demo Store"],
    expiry=utcnow() + timedelta(days=7),
    total_budget=TOTAL_BUDGET,
    approval_threshold=APPROVAL_THRESHOLD,
)


def get_remaining_budget() -> float:
    total = float(CURRENT_MANDATE.total_budget)
    spent = float(_SPENT_STORE.get("total_spent", 0.0))
    return max(0.0, total - spent)


def log_audit(event_type: str, details: dict) -> None:
    audit_store.append_audit_entry(
        event_type,
        {
            "mandate_version": CURRENT_MANDATE.mandate_version,
            "mandate_status": CURRENT_MANDATE.status,
            **details,
        },
    )


def find_item(item_id: str) -> Optional[CatalogItem]:
    return next(
        (item for item in CATALOG if item.item_id == item_id),
        None,
    )


def verify_owner(owner_password: str, denied_event: str) -> None:
    valid = bool(MANDATE_OWNER_PASSWORD) and hmac.compare_digest(
        owner_password,
        MANDATE_OWNER_PASSWORD,
    )

    if valid:
        return

    log_audit(
        denied_event,
        {
            "message": "Owner verification failed. No protected change was made.",
        },
    )

    raise HTTPException(
        status_code=401,
        detail="Owner verification failed. No protected change was made.",
    )


def requires_approval(item_id: str) -> bool:
    item = find_item(item_id)

    if item is None:
        return False

    return item.price >= CURRENT_MANDATE.approval_threshold


def evaluate_mandate(item_id: str) -> AgentDecision:
    item = find_item(item_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No such item: {item_id}",
        )

    mandate = CURRENT_MANDATE

    if utcnow() > mandate.expiry:
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=f"Mandate expired at {mandate.expiry.isoformat()}.",
        )

    if mandate.status == "paused":
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason="Agent purchasing is currently paused.",
        )

    if mandate.status == "revoked":
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=(
                "This mandate has been permanently revoked. "
                "Create a new mandate before agent purchasing can resume."
            ),
        )

    if not item.in_stock:
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=f"'{item.name}' is currently unavailable.",
        )

    if item.category not in mandate.allowed_categories:
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=f"Category '{item.category}' is not allowed.",
        )

    if item.merchant_name not in mandate.allowed_merchants:
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=(
                f"Merchant '{item.merchant_name}' is not on the trusted "
                "merchant allowlist."
            ),
        )

    if item.price > mandate.spending_cap:
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=(
                f"Item price INR {item.price:,.2f} exceeds the "
                f"INR {mandate.spending_cap:,.2f} per-order spending cap."
            ),
        )

    remaining_budget = get_remaining_budget()

    if item.price > remaining_budget:
        return AgentDecision(
            item_id=item_id,
            decision="block",
            reason=(
                f"Order price INR {item.price:,.2f} would exceed the remaining "
                f"total budget of INR {remaining_budget:,.2f}."
            ),
        )

    if requires_approval(item_id):
        return AgentDecision(
            item_id=item_id,
            decision="buy",
            reason=(
                f"'{item.name}' passes category, merchant, stock, per-order cap, "
                f"and total-budget checks, but its INR {item.price:,.2f} price "
                f"requires owner approval at or above INR "
                f"{mandate.approval_threshold:,.2f}."
            ),
        )

    return AgentDecision(
        item_id=item_id,
        decision="buy",
        reason=(
            f"'{item.name}' is in an allowed category, comes from a trusted "
            f"merchant, is in stock, is within the per-order cap, and fits "
            f"within the remaining total budget of INR {remaining_budget:,.2f}."
        ),
    )


def create_order_for_item(
    item: CatalogItem,
    receipt_prefix: str,
) -> dict:
    order = create_test_order(
        amount=int(item.price * 100),
        currency=DEFAULT_CURRENCY,
        receipt_id=(
            f"{receipt_prefix}_{item.item_id}_{int(time.time())}"
        ),
    )

    _SPENT_STORE["total_spent"] = (
        _SPENT_STORE.get("total_spent", 0.0) + float(item.price)
    )

    return order


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "bounded-agent-checkout",
    }


@app.get("/catalog", response_model=list[CatalogItem])
def get_catalog():
    return CATALOG


@app.get("/mandate", response_model=Mandate)
def get_mandate():
    return CURRENT_MANDATE


@app.put("/mandate", response_model=MandateStatusResponse)
def update_mandate(request: MandateUpdateRequest):
    verify_owner(request.owner_password, "mandate_update_denied")

    if CURRENT_MANDATE.status == "revoked":
        raise HTTPException(
            status_code=409,
            detail=(
                "A permanently revoked mandate cannot be edited. "
                "Create a new mandate instead."
            ),
        )

    if request.approval_threshold > request.spending_cap:
        raise HTTPException(
            status_code=400,
            detail=(
                "Approval threshold cannot be greater than the per-order "
                "spending cap."
            ),
        )

    total_spent = float(_SPENT_STORE.get("total_spent", 0.0))

    if request.total_budget < total_spent:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Total budget cannot be lower than already spent amount "
                f"of INR {total_spent:,.2f}."
            ),
        )

    old_mandate = CURRENT_MANDATE.model_dump(mode="json")

    CURRENT_MANDATE.spending_cap = request.spending_cap
    CURRENT_MANDATE.total_budget = request.total_budget
    CURRENT_MANDATE.approval_threshold = request.approval_threshold
    CURRENT_MANDATE.allowed_categories = sorted(
        {category.strip().lower() for category in request.allowed_categories}
    )
    CURRENT_MANDATE.allowed_merchants = sorted(
        {merchant.strip() for merchant in request.allowed_merchants}
    )
    CURRENT_MANDATE.mandate_version += 1

    new_mandate = CURRENT_MANDATE.model_dump(mode="json")

    changed_fields = {
        key: {
            "previous": old_mandate.get(key),
            "new": new_mandate.get(key),
        }
        for key in [
            "spending_cap",
            "total_budget",
            "approval_threshold",
            "allowed_categories",
            "allowed_merchants",
        ]
        if old_mandate.get(key) != new_mandate.get(key)
    }

    log_audit(
        "mandate_updated",
        {
            "changed_fields": changed_fields,
            "total_spent": total_spent,
            "remaining_budget": get_remaining_budget(),
        },
    )

    return MandateStatusResponse(
        mandate=CURRENT_MANDATE,
        message="Mandate updated successfully.",
    )


@app.post("/mandate/pause", response_model=MandateStatusResponse)
def pause_mandate(request: OwnerConfirmationRequest):
    verify_owner(request.owner_password, "mandate_pause_denied")

    if CURRENT_MANDATE.status == "revoked":
        raise HTTPException(
            status_code=409,
            detail="A revoked mandate cannot be paused or resumed.",
        )

    if CURRENT_MANDATE.status == "paused":
        return MandateStatusResponse(
            mandate=CURRENT_MANDATE,
            message="Mandate is already paused.",
        )

    previous_status = CURRENT_MANDATE.status
    previous_version = CURRENT_MANDATE.mandate_version

    CURRENT_MANDATE.status = "paused"
    CURRENT_MANDATE.mandate_version += 1

    log_audit(
        "mandate_paused",
        {
            "previous_status": previous_status,
            "new_status": CURRENT_MANDATE.status,
            "previous_version": previous_version,
            "new_version": CURRENT_MANDATE.mandate_version,
        },
    )

    return MandateStatusResponse(
        mandate=CURRENT_MANDATE,
        message="Agent purchasing has been paused.",
    )


@app.post("/mandate/resume", response_model=MandateStatusResponse)
def resume_mandate(request: OwnerConfirmationRequest):
    verify_owner(request.owner_password, "mandate_resume_denied")

    if CURRENT_MANDATE.status == "revoked":
        log_audit(
            "mandate_resume_blocked",
            {
                "message": (
                    "Resume was denied because the mandate is permanently revoked."
                ),
            },
        )

        raise HTTPException(
            status_code=409,
            detail=(
                "This mandate is permanently revoked and cannot be resumed. "
                "Create a new mandate instead."
            ),
        )

    if CURRENT_MANDATE.status == "active":
        return MandateStatusResponse(
            mandate=CURRENT_MANDATE,
            message="Mandate is already active.",
        )

    previous_status = CURRENT_MANDATE.status
    previous_version = CURRENT_MANDATE.mandate_version

    CURRENT_MANDATE.status = "active"
    CURRENT_MANDATE.mandate_version += 1

    log_audit(
        "mandate_resumed",
        {
            "previous_status": previous_status,
            "new_status": CURRENT_MANDATE.status,
            "previous_version": previous_version,
            "new_version": CURRENT_MANDATE.mandate_version,
        },
    )

    return MandateStatusResponse(
        mandate=CURRENT_MANDATE,
        message="Agent purchasing has been resumed.",
    )


@app.post("/mandate/revoke", response_model=MandateStatusResponse)
def revoke_mandate(request: OwnerConfirmationRequest):
    verify_owner(request.owner_password, "mandate_revoke_denied")

    if CURRENT_MANDATE.status == "revoked":
        return MandateStatusResponse(
            mandate=CURRENT_MANDATE,
            message="Mandate is already permanently revoked.",
        )

    previous_status = CURRENT_MANDATE.status
    previous_version = CURRENT_MANDATE.mandate_version

    CURRENT_MANDATE.status = "revoked"
    CURRENT_MANDATE.mandate_version += 1

    log_audit(
        "mandate_revoked",
        {
            "previous_status": previous_status,
            "new_status": CURRENT_MANDATE.status,
            "previous_version": previous_version,
            "new_version": CURRENT_MANDATE.mandate_version,
            "message": (
                "Owner permanently revoked the mandate. "
                "Agent purchasing is disabled."
            ),
        },
    )

    return MandateStatusResponse(
        mandate=CURRENT_MANDATE,
        message=(
            "Mandate permanently revoked. Agent purchasing cannot be resumed."
        ),
    )


@app.post("/agent/decide", response_model=AgentDecision)
def agent_decide(item_id: str):
    start = time.perf_counter()
    decision = evaluate_mandate(item_id)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    log_audit(
        "agent_decision",
        {
            **decision.model_dump(mode="json"),
            "latency_ms": latency_ms,
            "requires_approval": requires_approval(item_id),
            "approval_threshold": CURRENT_MANDATE.approval_threshold,
        },
    )

    return decision


@app.post("/agent/explain", response_model=AgentExplanation)
def agent_explain(item_id: str):
    item = find_item(item_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No such item: {item_id}",
        )

    start = time.perf_counter()
    decision = evaluate_mandate(item_id)

    explanation = agent_explainer.generate_explanation(
        item_name=item.name,
        price=item.price,
        category=item.category,
        decision=decision.decision,
        reason=decision.reason,
        mandate=CURRENT_MANDATE.model_dump(mode="json"),
    )

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    result = AgentExplanation(
        item_id=item_id,
        decision=decision.decision,
        reason=decision.reason,
        explanation=explanation,
        requires_approval=requires_approval(item_id),
        approval_threshold=CURRENT_MANDATE.approval_threshold,
    )

    log_audit(
        "agent_explanation",
        {
            **result.model_dump(mode="json"),
            "latency_ms": latency_ms,
        },
    )

    return result


@app.post("/agent/plan", response_model=AgentPlanResponse)
def agent_plan(request: str):
    log_audit(
        "planner_request",
        {"user_request": request},
    )

    proposal = shopping_planner.plan_purchase(
        request,
        [item.model_dump() for item in CATALOG],
    )

    log_audit("planner_proposal", proposal)

    requested_item_id = proposal.get("requested_item_id")

    if not requested_item_id:
        return AgentPlanResponse(
            user_request=request,
            requested_item_id=None,
            intent_summary=proposal["intent_summary"],
            selection_reason=proposal["selection_reason"],
            planner_mode=proposal["planner_mode"],
            confidence=proposal["confidence"],
            approval_threshold=CURRENT_MANDATE.approval_threshold,
        )

    item = find_item(requested_item_id)

    if item is None:
        return AgentPlanResponse(
            user_request=request,
            requested_item_id=None,
            intent_summary=proposal["intent_summary"],
            selection_reason="The proposed item is not in the catalog.",
            planner_mode=proposal["planner_mode"],
            confidence=0.0,
            approval_threshold=CURRENT_MANDATE.approval_threshold,
        )

    start = time.perf_counter()
    decision = evaluate_mandate(item.item_id)

    explanation = agent_explainer.generate_explanation(
        item_name=item.name,
        price=item.price,
        category=item.category,
        decision=decision.decision,
        reason=decision.reason,
        mandate=CURRENT_MANDATE.model_dump(mode="json"),
    )

    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    result = AgentPlanResponse(
        user_request=request,
        requested_item_id=item.item_id,
        intent_summary=proposal["intent_summary"],
        selection_reason=proposal["selection_reason"],
        planner_mode=proposal["planner_mode"],
        confidence=proposal["confidence"],
        item=item,
        decision=decision.decision,
        reason=decision.reason,
        explanation=explanation,
        requires_approval=requires_approval(item.item_id),
        approval_threshold=CURRENT_MANDATE.approval_threshold,
    )

    log_audit(
        "policy_decision",
        {
            **result.model_dump(mode="json"),
            "latency_ms": latency_ms,
        },
    )

    return result


@app.post("/order/create", response_model=IdempotentOrderResponse)
def create_order(
    item_id: str,
    idempotency_key: Optional[str] = Header(
        None,
        alias="Idempotency-Key",
    ),
):
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required.",
        )

    item = find_item(item_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No such item: {item_id}",
        )

    existing = _IDEMPOTENCY_STORE.get(idempotency_key)

    if existing:
        if existing["item_id"] != item_id:
            raise HTTPException(
                status_code=409,
                detail="This idempotency key was used for another item.",
            )

        log_audit(
            "order_replay_returned",
            {
                "item_id": item_id,
                "idempotency_key": idempotency_key,
            },
        )

        return IdempotentOrderResponse(
            order=existing["order"],
            idempotent_replay=True,
        )

    decision = evaluate_mandate(item_id)

    if decision.decision == "block":
        log_audit(
            "order_blocked",
            {
                "item_id": item_id,
                "reason": decision.reason,
            },
        )

        raise HTTPException(
            status_code=403,
            detail=f"Order blocked by mandate: {decision.reason}",
        )

    if requires_approval(item_id):
        log_audit(
            "order_direct_creation_blocked",
            {
                "item_id": item_id,
                "reason": (
                    "High-value purchase requires a pending approval request "
                    "before an order can be created."
                ),
                "approval_threshold": CURRENT_MANDATE.approval_threshold,
            },
        )

        raise HTTPException(
            status_code=409,
            detail=(
                "This purchase requires owner approval. "
                "Create a pending approval request first."
            ),
        )

    order = create_order_for_item(item, "receipt")

    _IDEMPOTENCY_STORE[idempotency_key] = {
        "item_id": item_id,
        "order": order,
        "timestamp": utcnow().isoformat(),
    }

    log_audit(
        "order_created",
        {
            "item_id": item_id,
            "order": order,
            "item_price": float(item.price),
            "total_spent": _SPENT_STORE["total_spent"],
            "remaining_budget": get_remaining_budget(),
            "approved_by_owner": False,
        },
    )

    return IdempotentOrderResponse(
        order=order,
        idempotent_replay=False,
    )


@app.post("/orders/pending", response_model=PendingOrderResponse)
def create_pending_order(request: PendingOrderRequest):
    item = find_item(request.item_id)

    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No such item: {request.item_id}",
        )

    decision = evaluate_mandate(request.item_id)

    if decision.decision == "block":
        log_audit(
            "pending_order_blocked",
            {
                "item_id": request.item_id,
                "reason": decision.reason,
            },
        )

        raise HTTPException(
            status_code=403,
            detail=f"Pending order blocked by mandate: {decision.reason}",
        )

    if not requires_approval(request.item_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "This item does not require owner approval. "
                "Use the normal order creation route."
            ),
        )

    for pending_order in _PENDING_ORDERS.values():
        if (
            pending_order["item_id"] == request.item_id
            and pending_order["status"] == "pending"
        ):
            return PendingOrderResponse(
                pending_order=pending_order,
                message="An active pending approval request already exists.",
            )

    pending_id = f"pending_{uuid.uuid4().hex[:12]}"

    pending_order = {
        "pending_id": pending_id,
        "item_id": item.item_id,
        "item_name": item.name,
        "price": float(item.price),
        "category": item.category,
        "merchant_name": item.merchant_name,
        "source": request.source,
        "status": "pending",
        "created_at": utcnow().isoformat(),
        "approval_threshold": CURRENT_MANDATE.approval_threshold,
        "mandate_version": CURRENT_MANDATE.mandate_version,
    }

    _PENDING_ORDERS[pending_id] = pending_order

    log_audit(
        "approval_requested",
        {
            **pending_order,
            "message": (
                "High-value purchase is waiting for explicit owner approval."
            ),
        },
    )

    return PendingOrderResponse(
        pending_order=pending_order,
        message="Approval request created. The owner can approve or cancel it.",
    )


@app.get("/orders/pending", response_model=PendingOrderListResponse)
def list_pending_orders():
    pending_orders = sorted(
        _PENDING_ORDERS.values(),
        key=lambda pending: pending["created_at"],
        reverse=True,
    )

    return PendingOrderListResponse(pending_orders=pending_orders)


@app.post(
    "/orders/pending/{pending_id}/approve",
    response_model=IdempotentOrderResponse,
)
def approve_pending_order(
    pending_id: str,
    request: PendingOrderActionRequest,
):
    verify_owner(request.owner_password, "pending_order_approval_denied")

    pending_order = _PENDING_ORDERS.get(pending_id)

    if pending_order is None:
        raise HTTPException(
            status_code=404,
            detail="Pending approval request not found.",
        )

    if pending_order["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"This request is already {pending_order['status']} and "
                "cannot be approved again."
            ),
        )

    item = find_item(pending_order["item_id"])

    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No such item: {pending_order['item_id']}",
        )

    decision = evaluate_mandate(item.item_id)

    if decision.decision == "block":
        pending_order["status"] = "blocked"
        pending_order["resolved_at"] = utcnow().isoformat()
        pending_order["resolution_reason"] = decision.reason

        log_audit(
            "pending_order_approval_blocked",
            {
                "pending_id": pending_id,
                "item_id": item.item_id,
                "reason": decision.reason,
            },
        )

        raise HTTPException(
            status_code=403,
            detail=f"Approval blocked by current mandate: {decision.reason}",
        )

    order = create_order_for_item(item, "receipt_approved")

    pending_order["status"] = "approved"
    pending_order["resolved_at"] = utcnow().isoformat()
    pending_order["approved_by_owner"] = True
    pending_order["order"] = order

    log_audit(
        "pending_order_approved",
        {
            "pending_id": pending_id,
            "item_id": item.item_id,
            "order": order,
            "item_price": float(item.price),
            "total_spent": _SPENT_STORE["total_spent"],
            "remaining_budget": get_remaining_budget(),
            "approved_by_owner": True,
        },
    )

    return IdempotentOrderResponse(
        order=order,
        idempotent_replay=False,
    )


@app.post(
    "/orders/pending/{pending_id}/cancel",
    response_model=PendingOrderResponse,
)
def cancel_pending_order(
    pending_id: str,
    request: PendingOrderActionRequest,
):
    verify_owner(request.owner_password, "pending_order_cancel_denied")

    pending_order = _PENDING_ORDERS.get(pending_id)

    if pending_order is None:
        raise HTTPException(
            status_code=404,
            detail="Pending approval request not found.",
        )

    if pending_order["status"] != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"This request is already {pending_order['status']} and "
                "cannot be cancelled."
            ),
        )

    pending_order["status"] = "cancelled"
    pending_order["resolved_at"] = utcnow().isoformat()
    pending_order["cancelled_by_owner"] = True

    log_audit(
        "pending_order_cancelled",
        {
            "pending_id": pending_id,
            "item_id": pending_order["item_id"],
            "message": "Owner cancelled the pending approval request.",
        },
    )

    return PendingOrderResponse(
        pending_order=pending_order,
        message="Pending approval request cancelled.",
    )


@app.get("/notifications/preferences", response_model=NotificationPreferences)
def get_notification_preferences():
    return _NOTIFICATION_PREFERENCES


@app.put(
    "/notifications/preferences",
    response_model=NotificationPreferencesResponse,
)
def update_notification_preferences(
    request: NotificationPreferencesUpdateRequest,
):
    verify_owner(
        request.owner_password,
        "notification_preferences_update_denied",
    )

    _NOTIFICATION_PREFERENCES.notify_on_block = request.notify_on_block
    _NOTIFICATION_PREFERENCES.notify_on_approval_required = (
        request.notify_on_approval_required
    )
    _NOTIFICATION_PREFERENCES.notify_on_order_created = (
        request.notify_on_order_created
    )
    _NOTIFICATION_PREFERENCES.notify_on_mandate_changes = (
        request.notify_on_mandate_changes
    )

    log_audit(
        "notification_preferences_updated",
        {
            "preferences": _NOTIFICATION_PREFERENCES.model_dump(),
        },
    )

    return NotificationPreferencesResponse(
        preferences=_NOTIFICATION_PREFERENCES,
        message="Notification preferences updated.",
    )


@app.get("/notifications")
def get_notifications(limit: int = 20):
    if limit < 1:
        raise HTTPException(
            status_code=400,
            detail="limit must be a positive integer.",
        )

    relevant_events = {
        "order_blocked": _NOTIFICATION_PREFERENCES.notify_on_block,
        "pending_order_blocked": _NOTIFICATION_PREFERENCES.notify_on_block,
        "approval_requested": (
            _NOTIFICATION_PREFERENCES.notify_on_approval_required
        ),
        "order_created": _NOTIFICATION_PREFERENCES.notify_on_order_created,
        "pending_order_approved": (
            _NOTIFICATION_PREFERENCES.notify_on_order_created
        ),
        "mandate_paused": _NOTIFICATION_PREFERENCES.notify_on_mandate_changes,
        "mandate_resumed": _NOTIFICATION_PREFERENCES.notify_on_mandate_changes,
        "mandate_revoked": _NOTIFICATION_PREFERENCES.notify_on_mandate_changes,
        "mandate_updated": _NOTIFICATION_PREFERENCES.notify_on_mandate_changes,
    }

    notifications = []

    for event in reversed(audit_store.get_all_audit_entries()):
        event_type = event.get("event_type", "")

        if relevant_events.get(event_type, False):
            notifications.append(
                {
                    "timestamp": event.get("timestamp", ""),
                    "event_type": event_type,
                    "details": event.get("details", {}),
                }
            )

        if len(notifications) >= limit:
            break

    return {
        "preferences": _NOTIFICATION_PREFERENCES.model_dump(),
        "notifications": notifications,
    }


@app.get("/audit")
def get_audit():
    return audit_store.get_all_audit_entries()


@app.get("/agent/trace")
def get_agent_trace(limit: Optional[int] = None):
    events = audit_store.get_all_audit_entries()

    if limit is not None:
        if limit < 1:
            raise HTTPException(
                status_code=400,
                detail="limit must be a positive integer.",
            )

        events = events[-limit:]

    return agent_trace.build_trace(events)


@app.get("/metrics")
def get_metrics():
    return metrics.calculate_metrics(
        audit_store.get_all_audit_entries()
    )


@app.get("/metrics/policy")
def get_policy_metrics():
    return policy_simulator.validate_policy_accuracy(
        audit_store.get_all_audit_entries(),
        [item.model_dump() for item in CATALOG],
        CURRENT_MANDATE.model_dump(mode="json"),
    )


@app.get("/metrics/adversarial")
def get_adversarial_metrics():
    return adversarial_tests.get_adversarial_stats()


@app.get("/metrics/budget")
def budget_metrics():
    total = float(CURRENT_MANDATE.total_budget)
    spent = float(_SPENT_STORE.get("total_spent", 0.0))
    remaining = max(0.0, total - spent)

    return {
        "total_budget": total,
        "total_spent": spent,
        "remaining_budget": remaining,
        "per_order_cap": CURRENT_MANDATE.spending_cap,
        "approval_threshold": CURRENT_MANDATE.approval_threshold,
        "mandate_status": CURRENT_MANDATE.status,
        "mandate_version": CURRENT_MANDATE.mandate_version,
    }


@app.get("/validation/results")
def get_validation_results():
    results_path = (
        Path(__file__).resolve().parent
        / "validation_results.json"
    )

    if not results_path.exists():
        return {
            "available": False,
            "message": (
                "No validation results yet. Run "
                "`python run_validation_suite.py`."
            ),
        }

    try:
        with results_path.open("r", encoding="utf-8") as file:
            results = json.load(file)

        results["available"] = True
        return results

    except json.JSONDecodeError:
        return {
            "available": False,
            "message": "validation_results.json is invalid.",
        }


@app.get("/config/status")
def config_status():
    return {
        "razorpay_configured": RAZORPAY_CONFIGURED,
        "owner_confirmation_configured": bool(
            MANDATE_OWNER_PASSWORD
        ),
        "key_id_prefix": (
            RAZORPAY_KEY_ID[:12] + "..."
            if RAZORPAY_CONFIGURED
            else None
        ),
        "hint": (
            "Real test keys detected."
            if RAZORPAY_CONFIGURED
            else "Razorpay test keys are not configured."
        ),
    }


@app.get("/")
def root():
    return {
        "message": "Bounded Agent Checkout is running.",
        "endpoints": [
            "/health",
            "/catalog",
            "/mandate",
            "/mandate/pause",
            "/mandate/resume",
            "/mandate/revoke",
            "/agent/decide",
            "/agent/explain",
            "/agent/plan",
            "/order/create",
            "/orders/pending",
            "/orders/pending/{pending_id}/approve",
            "/orders/pending/{pending_id}/cancel",
            "/notifications",
            "/notifications/preferences",
            "/audit",
            "/agent/trace",
            "/metrics",
            "/metrics/policy",
            "/metrics/adversarial",
            "/metrics/budget",
            "/validation/results",
            "/config/status",
            "/docs",
        ],
    }