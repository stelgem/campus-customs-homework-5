# Agent Dashboard Design

## Look and layout

The dashboard is an editorial-style campus operations desk: warm paper tones, a dark ink masthead, deep Yale-adjacent blue for the cash ledger, and coral accents for the action that starts a run. The ticket note is presented like a pinned dispatch slip, with compact database facts stamped beneath it. This gives the interface a human, tactile desk feeling without making the work area busy.

The desktop view uses three columns: a left ticket queue and checking card, a wide central ticket workbench, and a right agent room with the live activity timeline. On smaller screens the queue and workbench stack, while the agent room moves below them. Vite serves the page locally; the frontend calls the backend at `http://localhost:8000`.

## Agent activity and summaries

Each role has a consistent color, initials badge, and short remit. The activity panel distinguishes agent starts, completed reports, delegation, and MCP reads; the agent cards show the latest summary and tool names. While a ticket runs, the page polls the backend audit route so progress appears before the full run response arrives. When the run returns successfully, the selected ticket gets a resolved badge and the final Boss summary and next moves appear in the workbench.

## Resolved tickets and cash

Open tickets have a warm amber dot; resolved tickets use green. A successful run marks the ticket resolved in the live dashboard view. Human approval requests appear as separate review cards with the agent's rationale and amount. The approver enters their name and confirms the action; the backend rechecks the database and available cash before it records the payment. The checking card polls for updates and shows the ledger date so an approved payment visibly changes the balance.

## Human-centered details

The layout makes the ticket, current owner, and next decision easy to scan. The warm dispatch slip and restrained role colors make the desk feel more like a campus shop than a generic admin template. Live status dots, short activity sentences, tool chips, keyboard-accessible ticket buttons, focus rings, and responsive columns help people follow the work without reading raw logs. Drafts are labeled as unsent and approval remains a deliberate human action.
