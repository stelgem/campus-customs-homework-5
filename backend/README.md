# Campus Customs agent team

The backend uses five PydanticAI agents with full peer delegation. All five use `gpt-6-luna` through Portkey, reading `PORTKEY_API_KEY` from the workspace root `.env` with `python-dotenv`.

Shop facts are obtained only through the MCP server in `mcp_server/server.py`, which reads `data/campus_customs_new.db`. PydanticAI tools forward calls over MCP and append tool inputs/results, delegation, and agent-step reports to `output/audit_trail.json`. The audit file is a JSON array and new events are appended while preserving prior records.

Run one ticket or the open board from the Homework 5 folder after installing `requirements.txt` into a Python 3.10+ virtual environment:

```bash
python -m backend.team --ticket-id 101
python -m backend.team
```

The team limits a run to 10 agent runs, four delegation levels, four model requests per agent run, and 1,200 generated tokens per agent run. Accounting produces approval requests only; no agent can execute or record payments. Customer Service drafts stay on the board.

From the repository root, activate the project environment, then start the dashboard API:

```bash
source ../.venv/bin/activate
uvicorn main:app --reload --port 8000
```

The API exposes `GET /api/tickets`, `POST /api/tickets/{ticket_id}/run`, `POST /api/tickets/{ticket_id}/resolve`, `GET /api/events`, `POST /api/approvals`, `GET /api/cash`, and `POST /api/reset`. Payment and purchase amounts are derived from the working database in a transaction; approvals require an `approved_by` name. The human-directed resolution route accepts `purchase_order_placed` only when the matching purchase order and linked invoice are paid and evidence still shows a shortfall; it records the task as resolved while noting delivery is pending. It accepts `discount_declined` only when the listed restock cost exceeds checking cash. It does not create inventory or send customer messages. Example approval bodies are `{"kind":"invoice","ref_id":501,"approved_by":"Human Name"}` and `{"kind":"purchase_order","ref_id":101,"vendor_id":1,"approved_by":"Human Name"}`. Reset requires `{ "confirm": true }` and replaces only `data/campus_customs_new.db` from the original.
