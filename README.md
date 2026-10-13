# Campus Customs Multi-Agent Operations Desk

A small local operations desk for three Campus Customs tickets. It combines a FastMCP server over SQLite, a FastAPI backend with five PydanticAI agents, and a React + Vite + TypeScript dashboard.

## Project layout

```text
AI_prompts.md
.env.example
.mcp.json
README.md
requirements.txt
data/
  campus_customs.db
  campus_customs_new.db
mcp_server/
backend/
  main.py
  models.py
  prompts/
frontend/
output/
```

The original `data/campus_customs.db` is the reset source. All app tools use the separate working copy, `data/campus_customs_new.db`. Both files are included for the assignment. Do not replace or edit the original when testing.

## Setup

Requirements: Python 3.10+, Node.js/npm, and a Portkey API key for agent runs.

1. From this repository folder, create and activate a virtual environment and install backend dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

2. Install the dashboard dependencies:

   ```bash
   cd frontend
   npm install
   cd ..
   ```

3. Copy `.env.example` to `.env` in this repository and put your own `PORTKEY_API_KEY` in `.env`. Never commit `.env`; `.gitignore` excludes it. The agents use only `gpt-6-luna` through Portkey.

## Start the services

Start the MCP server from the repository folder (it speaks MCP over standard input/output):

```bash
source .venv/bin/activate
python mcp_server/server.py
```

The FastAPI agent backend starts its own MCP server process for each agent run. In another terminal, start the backend:

```bash
source .venv/bin/activate
cd backend
uvicorn main:app --reload --port 8000
```

In another terminal, start the React desk:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The board calls the backend at <http://localhost:8000>.

## Start a clean run

Before a full three-ticket run, restore only the working copy from the original. This discards previous test payments and ticket updates in the working copy while preserving the original:

```bash
curl -X POST http://localhost:8000/api/reset \
  -H 'Content-Type: application/json' \
  -d '{"confirm":true}'
```

Alternatively, with the backend stopped, copy the original over the working copy:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

Confirm the starting board and cash balance in the dashboard, then run tickets 101, 102, and 103 individually. Review each proposed payment and approve it as a human; agents do not pay on their own. The backend rejects payments that exceed checking cash. Customer-service text stays a draft, and the homework does not contact real customers or vendors. Agent runs append events to `output/audit_trail.json`; reset the working database before a new full run, but do not clear the audit history.

## Assignment evidence

- `output/desk_tickets.html` — Expected/Actual ticket plans, cash ledger, and reflection; open it directly in a browser.
- `output/resolved_tickets.json` — outcomes, agent contributions, approvals, and cash math.
- `output/resolved_board.html` — static screenshot gallery for tickets 101–103 (PNG files live beside it).
- `output/audit_trail.json` — append-only run, tool, delegation, approval, and resolution evidence.
- `output/harness.md` — database tables, MCP tools, agents, routes, dashboard, and safety notes.

The original shop date is stored in `desk.date_today`; use it, not the computer's clock, for overdue calculations. Vendor lead times and unpaid-invoice shipping holds come from the database. No revenue is modeled.
