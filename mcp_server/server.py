"""Read-only MCP tools for investigating Campus Customs tickets."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_DIR / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")


def _fetch_one(query: str, parameters: tuple[Any, ...]) -> dict[str, Any] | None:
    """Run a read-only query against the assignment's working database."""
    connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(query, parameters).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _fetch_all(query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Run a read-only query and return every matching database row."""
    connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(query, parameters).fetchall()]
    finally:
        connection.close()


@mcp.tool()
def list_open_tickets() -> dict[str, Any]:
    """List open work items from the ticket board for the Boss agent."""
    rows = _fetch_all(
        """
        SELECT id, type, requester, subject, sku, size, qty, lease_id,
               invoice_id, status, notes, created_at
        FROM tickets
        WHERE status = 'open'
        ORDER BY id
        """
    )
    return {"tickets": rows}


@mcp.tool()
def get_accounting_context() -> dict[str, Any]:
    """Read shop date, cash balances, invoices, and recorded payments for Accounting."""
    desk = _fetch_one("SELECT date_today, notes FROM desk LIMIT 1", ())
    cash_accounts = _fetch_all("SELECT name, balance, date FROM cash_accounts ORDER BY name")
    invoices = _fetch_all(
        """
        SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date,
               i.status, i.description
        FROM invoices AS i
        LEFT JOIN vendors AS v ON v.id = i.vendor_id
        ORDER BY i.id
        """
    )
    payments = _fetch_all(
        "SELECT id, kind, ref_id, amount, account, paid_at, approved_by FROM payments ORDER BY id"
    )
    return {
        "desk": desk,
        "cash_accounts": cash_accounts,
        "invoices": invoices,
        "payments": payments,
    }


@mcp.tool()
def get_vendor_restock_context(vendor_id: int) -> dict[str, Any]:
    """Read a vendor's specialty, lead time, and open invoices that may block shipment."""
    vendor = _fetch_one(
        "SELECT id, name, specialty, lead_days FROM vendors WHERE id = ?",
        (vendor_id,),
    )
    if vendor is None:
        return {"error": "No vendor with that ID was found."}
    open_invoices = _fetch_all(
        """
        SELECT id, amount, due_date, status, description
        FROM invoices
        WHERE vendor_id = ? AND status = 'open'
        ORDER BY id
        """,
        (vendor_id,),
    )
    return {"vendor": vendor, "open_invoices": open_invoices}


@mcp.tool()
def get_customer_order_context(ticket_id: int) -> dict[str, Any]:
    """Read order, matching stock, invoice, and vendor details for a customer-order ticket."""
    row = _fetch_one(
        """
        SELECT t.id AS ticket_id, t.type, t.status, t.requester, t.subject,
               t.sku, t.size, t.qty AS requested_qty, t.notes AS ticket_notes,
               i.qty AS stock_qty, i.location AS stock_location,
               inv.id AS invoice_id, inv.amount AS invoice_amount,
               inv.due_date AS invoice_due_date, inv.status AS invoice_status,
               inv.description AS invoice_description,
               v.id AS vendor_id, v.name AS vendor_name,
               v.specialty AS vendor_specialty, v.lead_days
        FROM tickets AS t
        LEFT JOIN inventory AS i ON i.sku = t.sku AND i.size = t.size
        LEFT JOIN invoices AS inv ON inv.id = t.invoice_id
        LEFT JOIN vendors AS v ON v.id = inv.vendor_id
        WHERE t.id = ? AND t.type = 'customer_order'
        """,
        (ticket_id,),
    )
    return row or {"error": "No matching customer-order ticket was found."}


@mcp.tool()
def get_rent_ticket_context(ticket_id: int) -> dict[str, Any]:
    """Read the linked lease and shop date for a rent-notice ticket."""
    row = _fetch_one(
        """
        SELECT t.id AS ticket_id, t.type, t.status, t.requester, t.subject,
               t.lease_id, t.notes AS ticket_notes,
               l.space_name, l.landlord, l.monthly_rent, l.next_due,
               l.notes AS lease_notes, d.date_today
        FROM tickets AS t
        LEFT JOIN leases AS l ON l.id = t.lease_id
        CROSS JOIN desk AS d
        WHERE t.id = ? AND t.type = 'rent_notice'
        """,
        (ticket_id,),
    )
    return row or {"error": "No matching rent-notice ticket was found."}


@mcp.tool()
def get_bulk_discount_context(ticket_id: int) -> dict[str, Any]:
    """Read requested quantity, matching hoodie stock, and listed cost/pricing for a price-override ticket."""
    row = _fetch_one(
        """
        SELECT t.id AS ticket_id, t.type, t.status, t.requester, t.subject,
               t.sku, t.size, t.qty AS requested_qty, t.notes AS ticket_notes,
               i.qty AS stock_qty, i.location AS stock_location,
               p.unit_cost, p.list_price
        FROM tickets AS t
        LEFT JOIN inventory AS i ON i.sku = t.sku AND i.size = t.size
        LEFT JOIN pricing AS p ON p.sku = t.sku
        WHERE t.id = ? AND t.type = 'price_override'
        """,
        (ticket_id,),
    )
    return row or {"error": "No matching price-override ticket was found."}


if __name__ == "__main__":
    mcp.run()
