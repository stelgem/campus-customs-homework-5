# Campus Customs Harness

## Database tables

| Table | Fields | Why it matters for the agents |
|---|---|---|
| `cash_accounts` | `name`, `balance`, `date` | Accounting checks available cash here and must prevent payments from making a balance negative. |
| `desk` | `date_today`, `notes` | Agents use the shop's own date to decide what is overdue. |
| `inventory` | `sku`, `name`, `size`, `qty`, `location` | Inventory checks stock by product and size and tracks where items are stored. |
| `invoices` | `id`, `vendor_id`, `amount`, `due_date`, `status`, `description` | Accounting tracks unpaid vendor bills; an open invoice can block that vendor from shipping. |
| `leases` | `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | Facilities uses lease and due-date details to handle rent tickets. |
| `payments` | `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by` | Records approved payments and the bill or lease they settle. |
| `pricing` | `sku`, `unit_cost`, `list_price` | Accounting uses costs and list prices to assess margins and discount requests. |
| `tickets` | `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at` | The board of work: Boss triages tickets and agents use their references to investigate and resolve them. |
| `vendors` | `id`, `name`, `specialty`, `lead_days` | Inventory identifies suitable suppliers and estimates restock timing from vendor lead times. |

## Open tickets and related records

The shop date in `desk.date_today` is **2026-08-31**.

| Ticket | Request | Table links and current context |
|---|---|---|
| `101` — customer order | Tauhid Zaman needs one `CC-TEE-WHITE`, size `S`. | `tickets.sku` and `tickets.size` match the inventory row with quantity `0`. `tickets.invoice_id = 501` links to an open $840 invoice in `invoices`, vendor 1 (Bulldog Print Co), for a rush reprint of this size. Vendor 1 has a 5 day lead time; the open unpaid invoice means it cannot ship new product until that invoice is paid. |
| `102` — rent notice | Elm City Properties says rent is due in two days. | `tickets.lease_id = 1` links to the Chapel Street shop lease, monthly rent $2,400, next due 2026-09-02. Relative to the shop date, the notice is not overdue. |
| `103` — price override | Yale AI Club requests 20 medium `CC-HOOD-NAVY` hoodies with a bulk discount. | SKU and size match inventory quantity `8`, a shortfall of 12. The `pricing` row gives unit cost $22 and list price $58, useful for evaluating a discount. |

Other useful database context: checking cash is $3,400 as of 2026-08-31. The vendor table lists Bulldog Print Co (apparel reprint, 5 days), Elm City Gifts (mugs and small goods, 3 days), and QuickShip CT (local courier, 1 day). No payments have been recorded yet.

## MCP tools

| Tool | Tables read | Ticket it helps unlock | Why this tool fits the ticket |
|---|---|---|---|
| `get_customer_order_context(ticket_id)` | `tickets`, `inventory`, `invoices`, `vendors` | 101 | Ticket 101 needs a small tee that is out of stock, and its linked invoice/vendor records show the reprint bill and whether the supplier is blocked from shipping. |
| `get_rent_ticket_context(ticket_id)` | `tickets`, `leases`, `desk` | 102 | Ticket 102 references lease 1, so this returns that lease's rent and due date alongside the shop's authoritative date for checking whether rent is overdue. |
| `get_bulk_discount_context(ticket_id)` | `tickets`, `inventory`, `pricing` | 103 | Ticket 103 asks for 20 medium hoodies while only 8 are in stock, and the cost/list price fields support evaluating the requested discount. |

## Additional MCP tools

| Tool | Tables read | Tickets supported | Why agents need it |
|---|---|---|---|
| `list_open_tickets()` | `tickets` | 101, 102, 103 | Boss reads the actual open board before routing work and checks a requested ticket is still open. |
| `get_accounting_context()` | `desk`, `cash_accounts`, `invoices`, `vendors`, `payments` | 101, 102, 103 | Accounting needs authoritative cash, shop date, vendor-linked payables, and recorded payments before recommending any outgoing money. |
| `get_vendor_restock_context(vendor_id)` | `vendors`, `invoices` | 101, 103 | Inventory checks the vendor's database lead time and open unpaid invoices before describing whether a restock can ship. |

## Agent team

All five agents use the only configured model, `gpt-6-luna` through Portkey. Every agent can delegate to each of the other four agents. Agent-facing shop-data tools forward to the MCP server; the backend does not open or query the shop database itself.

| Agent | MCP tools available | Main responsibility |
|---|---|---|
| Boss | `list_open_tickets`, `get_customer_order_context`, `get_rent_ticket_context`, `get_bulk_discount_context`, `get_accounting_context`, `get_vendor_restock_context` | Routes open tickets, delegates investigations, and returns the consolidated recommendation. |
| Inventory | `get_customer_order_context`, `get_bulk_discount_context`, `get_vendor_restock_context`, `get_accounting_context` | Checks stock and restock options; delegates invoice holds to Accounting. |
| Accounting | `get_accounting_context`, `get_customer_order_context`, `get_rent_ticket_context`, `get_bulk_discount_context` | Checks cash, invoices, and margins; prepares human-approval requests without issuing payment. |
| Facilities | `get_rent_ticket_context`, `get_accounting_context` | Assesses lease timing against `desk.date_today` and sends payment questions to Accounting. |
| Customer Service | `get_customer_order_context`, `get_bulk_discount_context`, `get_rent_ticket_context` | Drafts evidence-based messages that remain on the board and are never sent. |

## Safety and operating limits

- Keep customer communication as a draft until a human reviews and explicitly sends it; agents must never contact customers or vendors directly.
- Require an explicit human approval step before any payment or purchase order is executed. The agent tools are read-only and cannot record payments.
- Enforce nonnegative cash in `POST /api/approvals` using a transaction and a fresh balance check; record an approved payment and its reference atomically. Never count revenue because this homework models none.
- Keep secrets out of prompts, audit entries, and source control. Load `PORTKEY_API_KEY` from the workspace `.env`; protect logs because they may contain ticket/customer data.
- Audit agent steps, delegation, MCP tool inputs/results, and failures by appending to `output/audit_trail.json`; preserve prior entries.
- Bound model requests and output tokens per agent, cap total agent runs and delegation depth, and delegate only focused questions to control token use and prevent circular work.

## Backend routes

- `GET /api/tickets` — return all three tickets with their current status and identifying details.
- `POST /api/tickets/{ticket_id}/run` — run Boss and the delegated team for one ticket and return the structured report.
- `POST /api/tickets/{ticket_id}/resolve` — apply a human-directed `purchase_order_placed` (only with matching paid PO, paid linked invoice, stock shortfall, and vendor record) or `discount_declined` (only when evidence shows the shortfall cannot be funded); record the resolution in notes and audit without pretending goods were received or sending a message.
- `GET /api/events?limit=100` — return the most recent audit events, including each agent report, delegation, and MCP tool input/result.
- `POST /api/approvals` — after a human approves, transactionally pay an open invoice, lease rent, or database-priced purchase order; update checking cash and the relevant payment/invoice/lease tables, and reject insufficient funds or blocked vendors.
- `GET /api/cash` — return the current checking balance and its recorded date.
- `POST /api/reset` — require `{ "confirm": true }` and atomically restore only `data/campus_customs_new.db` from the untouched original.

## Dashboard

- `frontend/` is the React + Vite + TypeScript human operations desk; it calls the API at `http://localhost:8000` and is served at `http://localhost:5173`.
- The left rail lists the three tickets and live checking balance; the workbench shows ticket details, Boss recommendations, and approval cards; the agent room and activity timeline display each agent's step, delegation, and MCP tool activity.
- Payment cards require the human's name and a confirmation prompt; approved requests refresh cash, payment records, and ticket status. Customer drafts remain unsent.
- `output/design.md` documents the visual design. `output/desk_tickets.html` records Expected vs Actual and the cash ledger. `output/resolved_board.html` is a self-contained gallery of the three static React-board screenshots (`resolved_board_ticket_101.png`, `_102.png`, `_103.png`).

## Problem 9 full-run record

- Reset was performed from the untouched original before the run. Starting checking balance: **$3,400.00** (shop date 2026-08-31).
- Ticket 101: user-approved invoice 501 payment **−$840.00** (balance $2,560.00), then—after the initial three runs—the user-approved purchase order for one tee from Bulldog Print Co **−$8.00** (vendor 1; listed lead time 5 days). The PO payment is recorded. A human-directed resolution closes the order-placement task while preserving a note that delivery is pending; inventory remains 0 and no customer fulfillment was claimed.
- Ticket 102: user-approved rent payment for lease 1 **−$2,400.00**; ticket is **resolved**, and `leases.next_due` advanced to 2026-10-02. Balance after rent: $160.00.
- Ticket 103: no payment or purchase (**$0.00**); 8 hoodies are listed against 20 requested, and the $264 cost of the 12-unit shortfall exceeds the remaining $152. Per the user's latest request for full resolution, it was closed without a discount or customer message.
- Final checking balance is **$152.00**, verified against `cash_accounts`: $3,400.00 − $840.00 − $8.00 − $2,400.00 = $152.00. All three payment records identify `User-approved via chat`; invoice 501 is paid.
- Runs and tool results are appended (not reset) in `output/audit_trail.json`. The first 101 attempt failed because Portkey's chat-completions route rejected tool calls with reasoning effort enabled; the failure is retained. The successful retry uses the same sole model, `gpt-6-luna`, with `openai_reasoning_effort: none` for compatibility.
- Full per-agent contributions, actual delegation edges, and tool names are in `output/resolved_tickets.json` and the Actual panels in `output/desk_tickets.html`.

## Resolution and safety boundary

Ticket 101 is resolved as an order-placement work item, with delivery explicitly pending; it is not represented as inventory received. Ticket 103 is resolved by declining the requested discount because the 12-unit restock ($264 at listed unit cost) exceeds the $152 checking balance; the draft remains unsent. This follows the user's latest full-resolution request while preserving the underlying shop facts.

Keep vendor/customer contact disabled, leave drafts on the board, require an explicit human for every cash change or discount decision, validate payment amount/references and available cash transactionally, never model incoming revenue, and preserve the original database. Preserve audit history and keep model identity, request count, output size, delegation depth, and approval boundaries constrained. The model compatibility setting above changes no model ID: every agent run used only `gpt-6-luna` through Portkey.
