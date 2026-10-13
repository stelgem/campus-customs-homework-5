"""FastAPI routes for the Campus Customs dashboard."""

from __future__ import annotations

import asyncio
import calendar
import math
import os
import sqlite3
import sys
import threading
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from backend.team import append_audit_event, run_ticket_loop  # noqa: E402


ORIGINAL_DB = PROJECT_DIR / "data" / "campus_customs.db"
WORKING_DB = PROJECT_DIR / "data" / "campus_customs_new.db"
AUDIT_FILE = PROJECT_DIR / "output" / "audit_trail.json"
DB_LOCK = threading.RLock()
RUN_OR_RESET_LOCK = asyncio.Lock()

app = FastAPI(title="Campus Customs Operations API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApprovalRequest(BaseModel):
    kind: Literal["invoice", "rent", "purchase_order"]
    ref_id: int = Field(gt=0, description="Invoice ID, lease ID, or ticket ID, according to kind")
    approved_by: str = Field(min_length=1, max_length=120)
    vendor_id: int | None = Field(default=None, gt=0, description="Required for purchase_order")
    amount: float | None = Field(default=None, gt=0, description="Optional confirmation; server derives the payable amount")


class ResetRequest(BaseModel):
    confirm: bool


class TicketResolutionRequest(BaseModel):
    decision: Literal["purchase_order_placed", "discount_declined"]
    approved_by: str = Field(min_length=1, max_length=120)


def _connect() -> sqlite3.Connection:
    if not WORKING_DB.is_file():
        raise HTTPException(status_code=500, detail="Working database is missing")
    connection = sqlite3.connect(WORKING_DB, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _dict_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _advance_one_month(iso_date: str) -> str:
    due = date.fromisoformat(iso_date)
    year = due.year + (1 if due.month == 12 else 0)
    month = 1 if due.month == 12 else due.month + 1
    day = min(due.day, calendar.monthrange(year, month)[1])
    return date(year, month, day).isoformat()


@app.get("/api/tickets")
def get_tickets() -> dict[str, Any]:
    """Return every ticket and its current open/resolved status."""
    with DB_LOCK, closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT id, type, requester, subject, sku, size, qty, lease_id,
                   invoice_id, status, notes, created_at
            FROM tickets
            ORDER BY id
            """
        ).fetchall()
    return {"tickets": _dict_rows(rows)}


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int) -> dict[str, Any]:
    """Run Boss and its delegated agent team for one ticket."""
    async with RUN_OR_RESET_LOCK:
        with DB_LOCK, closing(_connect()) as connection:
            ticket = connection.execute(
                "SELECT id, status FROM tickets WHERE id = ?", (ticket_id,)
            ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if ticket["status"] != "open":
            raise HTTPException(status_code=409, detail="Only open tickets can be run")
        try:
            report = await run_ticket_loop(ticket_id)
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"Agent run failed: {error}") from error
    return {"ticket_id": ticket_id, "report": report.model_dump(mode="json")}


@app.post("/api/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, request: TicketResolutionRequest) -> dict[str, Any]:
    """Record a human-directed, evidence-backed non-payment ticket decision."""
    approver = request.approved_by.strip()
    if not approver:
        raise HTTPException(status_code=422, detail="approved_by must identify the human decision-maker")

    decision_note: str
    with DB_LOCK:
        connection = _connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            ticket = connection.execute(
                "SELECT id, type, status, sku, size, qty, invoice_id, notes FROM tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()
            if ticket is None:
                raise HTTPException(status_code=404, detail="Ticket not found")
            if ticket["status"] != "open":
                raise HTTPException(status_code=409, detail="Only open tickets can be resolved")

            if request.decision == "purchase_order_placed":
                if ticket["type"] != "customer_order":
                    raise HTTPException(status_code=409, detail="This decision only applies to customer-order tickets")
                paid_order = connection.execute(
                    "SELECT id, amount FROM payments WHERE kind = 'purchase_order' AND ref_id = ? ORDER BY id DESC LIMIT 1",
                    (ticket_id,),
                ).fetchone()
                inventory = connection.execute(
                    "SELECT qty FROM inventory WHERE sku = ? AND size = ?",
                    (ticket["sku"], ticket["size"]),
                ).fetchone()
                pricing = connection.execute(
                    "SELECT unit_cost FROM pricing WHERE sku = ?",
                    (ticket["sku"],),
                ).fetchone()
                invoice = connection.execute(
                    "SELECT vendor_id, status FROM invoices WHERE id = ?",
                    (ticket["invoice_id"],),
                ).fetchone()
                vendor = connection.execute(
                    "SELECT lead_days FROM vendors WHERE id = ?",
                    (invoice["vendor_id"],) if invoice else (-1,),
                ).fetchone()
                if not all((paid_order, inventory, pricing, invoice, vendor)) or invoice["status"] != "paid":
                    raise HTTPException(status_code=409, detail="A paid, eligible purchase order and linked vendor are required")
                shortfall = max(0, int(ticket["qty"] or 0) - int(inventory["qty"]))
                expected_cost = round(shortfall * float(pricing["unit_cost"]), 2)
                if shortfall <= 0 or not math.isclose(float(paid_order["amount"]), expected_cost, abs_tol=0.005):
                    raise HTTPException(status_code=409, detail="The recorded purchase order does not match the current stock shortfall")
                decision_note = (
                    f"Purchase order placed and paid (${expected_cost:.2f}) with the linked vendor; "
                    f"listed lead time is {vendor['lead_days']} days. Delivery is pending; no customer/vendor was contacted."
                )

            else:
                if ticket["type"] != "price_override":
                    raise HTTPException(status_code=409, detail="This decision only applies to price-override tickets")
                inventory = connection.execute(
                    "SELECT qty FROM inventory WHERE sku = ? AND size = ?",
                    (ticket["sku"], ticket["size"]),
                ).fetchone()
                pricing = connection.execute(
                    "SELECT unit_cost FROM pricing WHERE sku = ?",
                    (ticket["sku"],),
                ).fetchone()
                cash = connection.execute(
                    "SELECT balance FROM cash_accounts WHERE name = 'checking'",
                ).fetchone()
                if not all((inventory, pricing, cash)):
                    raise HTTPException(status_code=409, detail="Stock, pricing, or checking data is missing")
                shortfall = max(0, int(ticket["qty"] or 0) - int(inventory["qty"]))
                restock_cost = round(shortfall * float(pricing["unit_cost"]), 2)
                if shortfall == 0 or float(cash["balance"]) >= restock_cost:
                    raise HTTPException(status_code=409, detail="Insufficient-cash basis for declining this restock is not met")
                decision_note = (
                    f"Closed without a discount or purchase: {shortfall} units are needed and the listed "
                    f"restock cost is ${restock_cost:.2f}, above the ${float(cash['balance']):.2f} checking balance. "
                    "No customer message was sent."
                )

            combined_notes = f"{ticket['notes'] or ''}\nResolution ({approver}): {decision_note}".strip()
            connection.execute(
                "UPDATE tickets SET status = 'resolved', notes = ? WHERE id = ?",
                (combined_notes, ticket_id),
            )
            connection.commit()
        except HTTPException:
            connection.rollback()
            raise
        except Exception as error:
            connection.rollback()
            raise HTTPException(status_code=500, detail="Ticket resolution could not be recorded") from error
        finally:
            connection.close()

    result = {"ticket_id": ticket_id, "status": "resolved", "decision": request.decision, "approved_by": approver, "note": decision_note}
    try:
        append_audit_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "ticket_human_resolution",
                **result,
            }
        )
    except (OSError, ValueError):
        result["audit_warning"] = "Ticket was resolved, but its audit event could not be appended."
    return result


@app.get("/api/events")
def get_events(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    """Return recent agent-step, delegation, and MCP tool events in run order."""
    if not AUDIT_FILE.exists():
        return {"events": []}
    try:
        import json

        with AUDIT_FILE.open("r", encoding="utf-8") as audit_file:
            events = json.load(audit_file)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail="Audit trail is unreadable") from error
    if not isinstance(events, list):
        raise HTTPException(status_code=500, detail="Audit trail must be a JSON array")
    return {"events": events[-limit:]}


@app.post("/api/approvals")
def approve_payment_or_purchase(request: ApprovalRequest) -> dict[str, Any]:
    """Record a human-approved invoice, rent, or purchase-order payment."""
    approver = request.approved_by.strip()
    if not approver:
        raise HTTPException(status_code=422, detail="approved_by must identify the human approver")

    with DB_LOCK:
        connection = _connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            desk = connection.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
            cash = connection.execute(
                "SELECT name, balance FROM cash_accounts WHERE name = 'checking'"
            ).fetchone()
            if desk is None or cash is None:
                raise HTTPException(status_code=409, detail="Shop date or checking account is missing")
            paid_at = desk["date_today"]
            amount: float
            account = cash["name"]
            payment_kind = request.kind
            reference_id = request.ref_id
            approved_vendor_id: int | None = None
            purchased_quantity: int | None = None

            if request.kind == "invoice":
                invoice = connection.execute(
                    "SELECT id, amount, status FROM invoices WHERE id = ?",
                    (request.ref_id,),
                ).fetchone()
                if invoice is None:
                    raise HTTPException(status_code=404, detail="Invoice not found")
                if invoice["status"] != "open":
                    raise HTTPException(status_code=409, detail="Invoice is not open")
                amount = float(invoice["amount"])
                if request.amount is not None and not math.isclose(request.amount, amount, abs_tol=0.005):
                    raise HTTPException(status_code=409, detail="Approved amount does not match the invoice")

            elif request.kind == "rent":
                lease = connection.execute(
                    "SELECT id, monthly_rent, next_due FROM leases WHERE id = ?",
                    (request.ref_id,),
                ).fetchone()
                if lease is None:
                    raise HTTPException(status_code=404, detail="Lease not found")
                rent_ticket = connection.execute(
                    """
                    SELECT id FROM tickets
                    WHERE type = 'rent_notice' AND lease_id = ? AND status = 'open'
                    LIMIT 1
                    """,
                    (request.ref_id,),
                ).fetchone()
                if rent_ticket is None:
                    raise HTTPException(status_code=409, detail="There is no open rent ticket for this lease")
                amount = float(lease["monthly_rent"])
                if request.amount is not None and not math.isclose(request.amount, amount, abs_tol=0.005):
                    raise HTTPException(status_code=409, detail="Approved amount does not match the lease rent")
                already_paid_today = connection.execute(
                    "SELECT id FROM payments WHERE kind = 'rent' AND ref_id = ? AND paid_at = ? LIMIT 1",
                    (request.ref_id, paid_at),
                ).fetchone()
                if already_paid_today:
                    raise HTTPException(status_code=409, detail="Rent for this lease was already paid today")
                connection.execute(
                    "UPDATE leases SET next_due = ? WHERE id = ?",
                    (_advance_one_month(lease["next_due"]), request.ref_id),
                )

            else:
                if request.vendor_id is None:
                    raise HTTPException(status_code=422, detail="vendor_id is required for a purchase order")
                ticket = connection.execute(
                    """
                    SELECT id, type, sku, size, qty, status
                    FROM tickets WHERE id = ?
                    """,
                    (request.ref_id,),
                ).fetchone()
                if ticket is None:
                    raise HTTPException(status_code=404, detail="Purchase ticket not found")
                if ticket["status"] != "open" or ticket["qty"] is None or not ticket["sku"] or not ticket["size"]:
                    raise HTTPException(status_code=409, detail="Ticket is not an open inventory purchase request")
                inventory = connection.execute(
                    "SELECT qty FROM inventory WHERE sku = ? AND size = ?",
                    (ticket["sku"], ticket["size"]),
                ).fetchone()
                pricing = connection.execute(
                    "SELECT unit_cost FROM pricing WHERE sku = ?",
                    (ticket["sku"],),
                ).fetchone()
                vendor = connection.execute(
                    "SELECT id, name, specialty FROM vendors WHERE id = ?",
                    (request.vendor_id,),
                ).fetchone()
                if inventory is None or pricing is None or vendor is None:
                    raise HTTPException(status_code=409, detail="Inventory, pricing, or vendor data is missing")
                specialty = vendor["specialty"].casefold()
                sku = ticket["sku"].upper()
                if (
                    sku.startswith(("CC-HOOD", "CC-TEE", "CC-HAT"))
                    and "apparel" not in specialty
                ) or (
                    sku.startswith("CC-MUG")
                    and not ("mug" in specialty or "gift" in specialty)
                ) or "courier" in specialty:
                    raise HTTPException(status_code=409, detail="Vendor specialty does not match this product")
                open_invoice = connection.execute(
                    "SELECT id FROM invoices WHERE vendor_id = ? AND status = 'open' LIMIT 1",
                    (request.vendor_id,),
                ).fetchone()
                if open_invoice:
                    raise HTTPException(status_code=409, detail="Vendor has an open unpaid invoice and cannot ship")
                duplicate = connection.execute(
                    "SELECT id FROM payments WHERE kind = 'purchase_order' AND ref_id = ? LIMIT 1",
                    (request.ref_id,),
                ).fetchone()
                if duplicate:
                    raise HTTPException(status_code=409, detail="A purchase order was already paid for this ticket")
                shortfall = max(0, int(ticket["qty"]) - int(inventory["qty"]))
                if shortfall == 0:
                    raise HTTPException(status_code=409, detail="Current stock already covers the ticket quantity")
                amount = round(shortfall * float(pricing["unit_cost"]), 2)
                approved_vendor_id = request.vendor_id
                purchased_quantity = shortfall
                if request.amount is not None and not math.isclose(request.amount, amount, abs_tol=0.005):
                    raise HTTPException(status_code=409, detail="Approved amount does not match the database-derived order cost")
                payment_kind = "purchase_order"

            current_balance = float(cash["balance"])
            if amount <= 0:
                raise HTTPException(status_code=409, detail="Payment amount must be positive")
            if current_balance < 0:
                raise HTTPException(status_code=409, detail="Checking balance is already negative")
            if amount > current_balance:
                raise HTTPException(status_code=409, detail="Insufficient checking cash; payment refused")

            connection.execute(
                "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
                (round(current_balance - amount, 2), paid_at, account),
            )
            if request.kind == "invoice":
                connection.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (reference_id,))
            elif request.kind == "rent":
                connection.execute(
                    "UPDATE tickets SET status = 'resolved' WHERE id = ?",
                    (rent_ticket["id"],),
                )
            cursor = connection.execute(
                """
                INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payment_kind, reference_id, amount, account, paid_at, approver),
            )
            payment_id = cursor.lastrowid
            new_balance = round(current_balance - amount, 2)
            connection.commit()
        except HTTPException:
            connection.rollback()
            raise
        except Exception as error:
            connection.rollback()
            raise HTTPException(status_code=500, detail="Payment could not be recorded") from error
        finally:
            connection.close()

    audit_warning = None
    try:
        append_audit_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "human_approval_recorded",
                "approval_kind": request.kind,
                "reference_id": reference_id,
                "amount": amount,
                "account": account,
                "approved_by": approver,
                "payment_id": payment_id,
                "remaining_balance": new_balance,
                "vendor_id": approved_vendor_id,
                "quantity": purchased_quantity,
            }
        )
    except (OSError, ValueError):
        audit_warning = "Payment was committed, but the audit event could not be appended. Do not retry this approval."
    response = {
        "status": "paid",
        "kind": payment_kind,
        "ref_id": reference_id,
        "payment_id": payment_id,
        "amount": amount,
        "account": account,
        "paid_at": paid_at,
        "approved_by": approver,
        "remaining_balance": new_balance,
        "vendor_id": approved_vendor_id,
        "quantity": purchased_quantity,
    }
    if audit_warning:
        response["audit_warning"] = audit_warning
    return response


@app.get("/api/cash")
def get_checking_balance() -> dict[str, Any]:
    """Return the current checking balance and database date."""
    with DB_LOCK, closing(_connect()) as connection:
        row = connection.execute(
            "SELECT name, balance, date FROM cash_accounts WHERE name = 'checking'"
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Checking account not found")
    return {"account": row["name"], "balance": row["balance"], "date": row["date"]}


@app.post("/api/reset")
async def reset_working_database(request: ResetRequest) -> dict[str, str]:
    """Replace the working database with a verified copy of the original database."""
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to reset the working database")
    if not ORIGINAL_DB.is_file():
        raise HTTPException(status_code=500, detail="Original database is missing")

    async with RUN_OR_RESET_LOCK:
        temporary_db = WORKING_DB.with_name(f"{WORKING_DB.name}.{uuid.uuid4().hex}.tmp")
        with DB_LOCK:
            try:
                source = sqlite3.connect(f"file:{ORIGINAL_DB}?mode=ro", uri=True)
                destination = sqlite3.connect(temporary_db)
                try:
                    source.backup(destination)
                    check = destination.execute("PRAGMA integrity_check").fetchone()
                    if check is None or check[0] != "ok":
                        raise RuntimeError("Reset copy failed SQLite integrity check")
                finally:
                    destination.close()
                    source.close()
                os.replace(temporary_db, WORKING_DB)
            except Exception as error:
                temporary_db.unlink(missing_ok=True)
                raise HTTPException(status_code=500, detail="Working database reset failed") from error

    response = {"status": "reset", "database": "data/campus_customs_new.db"}
    try:
        append_audit_event(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "working_database_reset",
                "source": "data/campus_customs.db",
                "target": "data/campus_customs_new.db",
            }
        )
    except (OSError, ValueError):
        response["audit_warning"] = "Database reset succeeded, but the audit event could not be appended."
    return response
