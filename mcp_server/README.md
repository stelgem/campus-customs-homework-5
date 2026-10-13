# Campus Customs MCP Server

This MCP server exposes read-only database context tools for the Campus Customs PydanticAI agents. It uses the working database at `data/campus_customs_new.db`, resolved relative to the project folder, and opens it in SQLite read-only mode. Agent calls go through the MCP server; the backend does not read shop tables directly.

Tools:

- `list_open_tickets()` — reads `tickets` and returns the open board for Boss triage.
- `get_customer_order_context(ticket_id)` — reads a customer-order ticket plus matching inventory, its linked invoice, and the invoice's vendor details. Use it for ticket 101.
- `get_rent_ticket_context(ticket_id)` — reads a rent-notice ticket, its linked lease, and the shop date. Use it for ticket 102.
- `get_bulk_discount_context(ticket_id)` — reads a price-override ticket, matching inventory, and SKU pricing. Use it for ticket 103.
- `get_accounting_context()` — reads the shop date, cash accounts, invoices, and recorded payments for accounting checks and approval recommendations.
- `get_vendor_restock_context(vendor_id)` — reads a vendor's specialty and lead time plus its open invoices, so Inventory can identify shipment holds.

Requires Python 3.10 or newer. From the project folder, install dependencies into the project virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the server with:

```bash
python mcp_server/server.py
```
