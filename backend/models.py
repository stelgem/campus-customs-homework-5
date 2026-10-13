"""Structured data contracts shared by the Campus Customs agents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Ticket(BaseModel):
    id: int
    type: str
    requester: str
    subject: str
    sku: str | None = None
    size: str | None = None
    qty: int | None = None
    lease_id: int | None = None
    invoice_id: int | None = None
    status: str
    notes: str | None = None
    created_at: str


class InventoryItem(BaseModel):
    sku: str
    name: str
    size: str
    qty: int
    location: str


class Vendor(BaseModel):
    id: int
    name: str
    specialty: str
    lead_days: int


class Invoice(BaseModel):
    id: int
    vendor_id: int
    amount: float
    due_date: str
    status: str
    description: str | None = None


class Lease(BaseModel):
    id: int
    space_name: str
    landlord: str
    monthly_rent: float
    next_due: str
    notes: str | None = None


class CashAccount(BaseModel):
    name: str
    balance: float
    date: str


class Payment(BaseModel):
    id: int
    kind: str
    ref_id: int | None = None
    amount: float
    account: str
    paid_at: str
    approved_by: str


class ApprovalRequest(BaseModel):
    kind: Literal["invoice", "rent", "purchase_order", "discount", "other"]
    reference_id: int | None = None
    amount: float | None = Field(default=None, ge=0)
    vendor_id: int | None = Field(default=None, gt=0)
    rationale: str
    requires_human_approval: bool = True


class AgentReport(BaseModel):
    agent: str
    ticket_id: int | None = None
    status: Literal["complete", "needs_human_approval", "blocked", "in_progress"]
    summary: str
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    customer_message_draft: str | None = None
    delegated_agents: list[str] = Field(default_factory=list)
