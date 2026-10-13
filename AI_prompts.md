# AI Prompts

## Problem 1 — Vibe coder prompts

### Prompt typed

> So this is the scenaro:
>
> **Campus Customs Multi-Agent Operations** is the agentic team that runs the shop. Open tickets land on a board — customer orders, rent, unpaid bills, discount requests, whatever the shop has to handle. You will build three pieces that talk to each other: an **MCP server**, a **FastAPI backend** with a multi-agent team, and a **React dashboard** so a human can watch the agents at work and approve requests.
>
> Your agent team has **full connectivity** — any agent may delegate tasks to any other agent for help. In this assignment you will build these agents:
>
> - **Boss** — reads each ticket, decides who should work on it, and makes final calls
> - **Inventory** — checks stock by SKU and size, spots shortfalls, and figures out which vendor can restock
> - **Accounting** — watches cash and invoices, checks margins, and prepares payments or purchase orders for human approval
> - **Facilities** — handles the shop space side (leases, rent, etc.)
> - **Customer Service** — drafts messages for customers
>
> I’ve unzipped `data.zip`, so I have `data/campus_customs.db`. That file is the original shop database. Tables include `desk`, `tickets`, `inventory`, `pricing`, `vendors`, `leases`, `cash_accounts`, `payments`, and `invoices`.
>
> Your tools will update the database as tickets get resolved. Make a copy of the database file called `data/campus_customs_new.db` and point your MCP server and backend at that working copy. Keep `campus_customs.db` untouched so you can reset when you want to restart resolving the tickets. Here are the rules of the shop:
>
> - The field `desk.date_today` is “today” for the shop. Use this date to determine what is overdue.
> - Vendor lead times come from the `vendors` table.
> - A vendor will not ship new product while they still have an open unpaid invoice.
> - Human approval is required for any payments. Points will be deducted if this is not done. If payment is made, make sure to update the relevant table.
> - If there is not enough cash, the pay tool must refuse — no negative balances.
> - Cash only goes out in this homework — we did not model revenue, so no money comes in.
> - Before a full run to resolve the tickets, make sure to reset the database to the original values.
> - Do **not** email customers or call real vendors. Drafts stay on the board.
>
> Use your `PORTKEY_API_KEY` for AI calls. For this assignment, use **only** `gpt-6-luna` through Portkey for every agent. Multi-agent chats burn tokens fast. Points will be deducted if any other model shows up in your code or runs.
>
> Work **one problem at a time** with your vibe coder (there are 11 problems in total). Final submission will be a **public** GitHub repo (the last problem shows the file tree).

### Follow-up prompt

> Problem 1 is called 'Vibe coder prompts'. Create AI_prompts.md at the start of the assignment and keep it updated as your work. This file is the log of what I typed to you. Put one section for each problem. Each section must include: 1. The problem number and title. 2. At least one prompt I typed. 3. One follow-up prompt if I needed it (and one sentence on what was lacking after the first).

The initial assignment description set the project requirements but did not ask for the prompt log, so this follow-up supplies the Problem 1 title and logging requirements.

## Problem 2 — Study the Campus Customs database

### Prompt typed

> Problem 2: 'Study the Campus Customs database'. Open `data/campus_customs.db` and look through every table and its fields. Copy the original file to `data/campus_customs_new.db` — later problems update that working copy. Study the three open tickets so you see how they link to other tables. Start `output/harness.md`. For each table, list the fields and one short line of why that table matters for the agents. You will keep growing this harness file in later problems.

### Follow-up prompt

No follow-up was needed; the Problem 2 prompt specified the database inspection, working copy, ticket review, and harness contents.

## Problem 3 — Build the MCP server

### Prompt typed

> Problem 3: 'Build the MCP server'. Write an MCP server in `mcp_server/` using FastMCP. It will talk to `data/campus_customs_new.db`. You do not need to connect or run it in this problem. Every agent in this homework uses the tools in this MCP server. You will add more tools to it later; for now write three tools you know you will need for the tickets in the database. Keep the names clear. Never invent any data, only use information in the database. In `output/harness.md`, list each of your three MCP tools. For every tool include: which table it reads, which ticket it helps unlock (101, 102 or 103), and one sentence on why that tool is the right one for that ticket. Vague lines like 'reads inventory' score low — tie the tool to the ticket. Also add a short `mcp_server/README.md` file that explains what the MCP server is for, which database file it uses, and the three tools it has.

### Follow-up prompt

No follow-up was needed; the Problem 3 prompt specified the server location, database, three-tool scope, harness details, and README requirements.

## Problem 4 — Add the MCP server to vibe coder and test each tool

### Prompt typed

> Problem 4: 'Add the MCP server to vibe coder and test each tool' . Add your MCP server to this project so you can call the tools. Save the connection JSON text in `.mcp.json` at the project room (or homework you save MCP server lists). With you connected, test each of your three MCP tools. Save the evidence in `output/mcp_smoke.json` . For every tool include: 1. the prompt I asked you . 2. the tool name. 3. The tool output (must match values in `data/campus_customs_new.db`)

### Follow-up prompt

No follow-up was needed; the Problem 4 prompt specified the MCP configuration, tool calls, and evidence format.

## Problem 5 — Build the agent team and grow the MCP tools

### Prompt typed

> Problem 5: 'Build the agent team and grow the MCP tools'. Build the agentic team for Campus Customs using **PydanticAI**: **Boss**, **Inventory**, **Accounting**, **Facilities**, and **Customer Service**. Include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Put the agent prompts in `backend/prompts/` — **one file per agent**. Put data types in `backend/models.py`, and the agent files under `backend/` (your layout can vary as long as the five roles are clear). Use your `PORTKEY_API_KEY` and **only** `gpt-6-luna` for every agent.
>
> **What a strong agent prompt usually covers:**
>
> 1. **Role and scope.** Who the agent is and what it owns, plus what it should **not** do (e.g., Customer Service drafts messages but never approves discounts or payments).
> 2. **Tools it can use.** Which MCP tools it calls and when (e.g., Inventory checks stock by SKU and size).
> 3. **Shop rules that apply to it.** Pull from the rules page and assign each one to the agents that need it.
> 4. **Delegation.** Which teammates it should ask for help and in what situations, since your team has full connectivity.
> 5. **Output format.** What it returns (a structured result matching your `models.py` types, a draft, a recommendation).
> 6. **Edge cases.** What to do when data is missing, stock is short, or cash is too low.
>
> **Which rules matter most for each agent:**
>
> - **Boss:** routes every ticket, makes final calls, and knows that payments always need human approval.
> - **Inventory:** uses vendor lead times from the `vendors` table, and knows a vendor won’t ship while it has an open unpaid invoice (so it may need to delegate to Accounting).
> - **Accounting:** never pays without human approval, refuses payments that would go negative, updates the relevant table after payment, and knows no revenue comes in.
> - **Facilities:** handles leases and rent, uses `desk.date_today` to judge what’s overdue, and hands off any payment to Accounting.
> - **Customer Service:** only drafts messages that stay on the board and never emails real customers.
>
> Add any tools the agents need to your MCP server so they can work on the open tickets. Shop facts come from the MCP server over `data/campus_customs_new.db` — do not invent a second shop-tools layer that bypasses MCP. Wire the agents so they append to `output/audit_trail.json` as they run: for each agent-loop step, record enough to audit later. Append to this file — do not wipe it each run.
>
> In `output/harness.md`, list each agent and each MCP tool (including ones you add in this problem) along with which table the tool uses. Also add a short safety section: the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check.
>
> Update `mcp_server/README.md` so the tool list matches what you have now.

### Follow-up prompt

No follow-up was needed; the Problem 5 prompt specified the five roles, MCP-only data access, auditing, documentation, and safety requirements.

## Problem 6 — Plan the three tickets

### Prompt typed

> Problem 6: 'Plan the three tickets'. Before you wire the backend, write down what you **expect** the team to do on each open ticket. Build `output/desk_tickets.html` — a page you can double-click with **one tab per ticket** (101, 102, and 103). Also add empty **Cash** and **Reflection** tabs for later problems (leave them blank or with a short “coming later” note for now).
>
> On each ticket tab, fill an **Expected** section only (leave room for an **Actual** section you will fill after you run the agents). For each ticket’s Expected section, write in your own words:
>
> - Who the **Boss** should call **first**, and why
> - **All** the agent delegations you expect — not “Boss calls everyone”
> - Which **MCP tools** you expect that run to use
>
> Plans that send every specialist on every ticket score low. You will compare this plan to what actually happens when your agents resolve the three tickets.

### Follow-up prompt

No follow-up was needed; the Problem 6 prompt specified the five tabs and the expected delegation and tool details for each ticket.

## Problem 7 — Backend routes

### Prompt typed

> Problem 7: 'Backend routes' . Your React frontend dashboard (the next problem) needs a backend it can call. In `backend/main.py`, use **FastAPI** and add **routes** that do the following:
>
> - Return the three tickets and whether each is open or resolved.
> - Take a ticket id and run your agent team on that ticket.
> - Return recent agent events — what each agent said and which tools they used — so the board can refresh.
> - Approve a payment or purchase after a human clicks approve (agents only prepare the pay; this route is what actually changes cash).
> - Return the current checking balance from `cash_accounts`.
> - Reset the database to the original values when you want to try a fresh run.
>
> From the backend/ folder, start the server with: uvicorn main:app --reload --port 8000 . This turns on your backend at http://localhost:8000 so the frontend dashboard can call those rotes. In output/harness.md , list each route in one line (what URL / what it does)

### Follow-up prompt

No follow-up was needed; the Problem 7 prompt specified the six backend operations and the required route documentation.

## Problem 8 — Agent dashboard

### Prompt typed

> Problem 8: 'Agent dashboard' Build the frontend dashboard in `frontend/` with **React + Vite + TypeScript**. The page should call the routes you built in Problem 7. At minimum the board should:
>
> - List all **three** tickets.
> - Let you **pick one ticket** and start the agent team on it.
> - Show each agent and what they are saying / doing while the ticket runs.
> - Mark a ticket **resolved** when the run finishes.
> - Show a short **summary of what each agent did** on that ticket.
> - Let a human **approve** a pay or purchase when asked.
> - Show the checking balance (it should drop after an approved pay).
>
> Make the dashboard look good. Be creative with the layout and feel — this is a real desk people would want to sit at, so put thought into how it looks.
>
> Tell the front end to talk to your backend at `http://localhost:8000`. On the backend, allow the Vite page origin (usually `http://localhost:5173`) so the browser is allowed to call those routes. Start the board with: `npm run dev`. This opens the React desk in your browser so you can pick tickets and watch agents.
>
> Write `output/design.md` with what you chose for the dashboard look (layout, how agents read differently, how resolved tickets and cash show up) and why — including the creative choices that make it feel special and something humans would actually enjoy using.

### Follow-up prompt

No follow-up was needed; the Problem 8 prompt specified the framework, dashboard actions, backend URL, development server, and design document.

## Problem 9 — Resolve the tickets

### Prompt typed

> Problem 9: 'Resolve the tickets'. Before testing the agents on a full run over the three tickets, **reset** the working database `data/campus_customs_new.db` again so you start clean. Note the starting checking balance. Then run **all three tickets** on the board (101, 102, 103) until each is resolved. Open `output/desk_tickets.html` from Problem 6. On each ticket tab, fill the **Actual** section from this run: which agents worked, what they delegated, and which tools they used. Keep your Expected section so you can compare the two. On the Cash tab of the same `output/desk_tickets.html`, itemize the money:
>
> - Starting checking balance (after the reset)
> - For **each** ticket: how cash changed when that ticket resolved, and why (which pay / purchase, dollar amount)
> - Ending checking balance — it must match `cash_accounts` in the working database
>
> Wrong cash math loses points even if the board shows every ticket resolved. Also save:
>
> - `output/resolved_tickets.json` — for each ticket: id, final status, short outcome, what each agent contributed, and any human approvals
> - `output/resolved_board.html` — a page you can double-click with a screenshot of your React board for **each** resolved ticket (101, 102, and 103)
>
> Append real runs to `output/audit_trail.json`. Finish `output/harness.md` so it covers tables, MCP tools, the five agents, API routes, the dashboard, and safety rules.

### Follow-up prompt

> Approve 1 tee for $8. Keep ticket 103 open; no affordable restock.

The original prompt asked for the tickets to be resolved but did not specify approval for the separate $8 purchase order or what to do with ticket 103 once its $264 restock shortfall exceeded available cash; this follow-up authorized the tee order and explicitly kept ticket 103 open.

### Additional follow-up prompt

> I want it to be a full three-ticket resolution and a complete match to the screenshot requirement.

This superseded the prior direction to leave ticket 103 open and clarified that all ticket work items should be closed and static screenshots still needed; it did not authorize inventing a product delivery, so ticket 101 is recorded as an order-placement resolution with delivery pending.

### Completion follow-up

> can you complete it

This reaffirmed that the remaining resolution workflow and static screenshot artifact should be completed rather than left as blockers.

## Problem 10 — Reflection

### Prompt typed

> Problem 10: 'Reflection'. Open `output/desk_tickets.html` and fill the **Reflection** tab. Answer in your own vibe, and be detailed and thorough:
>
> - How would you evaluate the performance of the agents on each ticket and why?
> - For each ticket, how did Actual compare to the Expected plan you wrote earlier?
> - What would have been simpler as one agent with tools — and **why**?
> - Describe three **new** problems Campus Customs might face that this agent team could solve with the tools you built.
> - Describe three **new** problems Campus Customs might face that this agent team could **not** solve with the tools you built, and explain the tools and agents you would need to solve them.
>
> Tie every answer to *this* app and the three tickets you ran — use the ticket tabs and Cash tab on the same page as your evidence. Generic essays without Campus Customs details will score low.

### Follow-up prompt

No follow-up was needed; the prompt specified the Reflection tab's questions and required ticket-specific evidence from the existing tabs.

## Problem 11 — Public GitHub submission

### Prompt typed

> Push your code to a **public** GitHub repository so graders can clone it. Submit the repo URL to Canvas, and also put it in `output/github_url.txt`. Do **not** push your real `.env` to the GitHub repo. **Do** include both database files under `data/` (the original and your working copy) so graders can run your app easily. Expected file layout (in the screenshots). README should explain: copy original DB to the working copy when you need a clean run, start MCP server, start FastAPI backend, start the React board, reset the DB before a full three-ticket run.

### Follow-up prompt

No follow-up was needed; the prompt states the publication visibility, required files, secret exclusion, Canvas destination, and README instructions.
