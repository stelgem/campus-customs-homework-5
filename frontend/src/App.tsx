import { useEffect, useMemo, useState } from 'react'

const API = 'http://localhost:8000'

type Ticket = {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
}

type AgentReport = {
  agent: string
  ticket_id: number | null
  status: string
  summary: string
  findings: string[]
  recommendations: string[]
  approval_requests: ApprovalRequest[]
  customer_message_draft?: string | null
  delegated_agents: string[]
}

type ApprovalRequest = {
  kind: 'invoice' | 'rent' | 'purchase_order' | 'discount' | 'other'
  reference_id: number | null
  amount: number | null
  vendor_id?: number | null
  rationale: string
  requires_human_approval: boolean
}

type AgentEvent = {
  timestamp: string
  event: string
  run_id?: string
  ticket_id?: number | null
  agent?: string
  step?: number
  task?: string
  delegate?: string
  tool?: string
  arguments?: Record<string, unknown>
  output?: Record<string, unknown>
  approval_kind?: ApprovalRequest['kind']
  reference_id?: number | null
  amount?: number
  approved_by?: string
  status?: string
  summary?: string
  report?: AgentReport
  error?: string
}

type Cash = { account: string; balance: number; date: string }
type RunState = { startedAt: string; complete: boolean; report?: AgentReport }

const AGENTS = [
  { id: 'boss', name: 'Boss', initials: 'B', color: 'boss', role: 'Routing & final call' },
  { id: 'inventory', name: 'Inventory', initials: 'IN', color: 'inventory', role: 'Stock & vendors' },
  { id: 'accounting', name: 'Accounting', initials: '$', color: 'accounting', role: 'Cash & margins' },
  { id: 'facilities', name: 'Facilities', initials: 'F', color: 'facilities', role: 'Space & rent' },
  { id: 'customer_service', name: 'Customer Service', initials: 'CS', color: 'customer', role: 'Drafts only' },
]

const TYPE_LABELS: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`)
  }
  return body as T
}

function formatMoney(amount: number | null | undefined) {
  if (amount == null) return 'Amount from database'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(amount)
}

function formatTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })
}

function agentLabel(id?: string) {
  return AGENTS.find((agent) => agent.id === id)?.name ?? id?.replaceAll('_', ' ') ?? 'System'
}

function eventDescription(event: AgentEvent) {
  if (event.event === 'agent_step_started') return event.task ?? 'Started work on the ticket.'
  if (event.event === 'agent_step_completed') return event.report?.summary ?? event.summary ?? 'Finished this step.'
  if (event.event === 'agent_delegation_started') return `Asked ${agentLabel(event.delegate)} to help: ${event.task ?? 'focused review'}`
  if (event.event === 'agent_delegation_completed') return `Received ${agentLabel(event.delegate)}’s findings.`
  if (event.event === 'mcp_tool_call_started') return `Checking ${event.tool ?? 'shop records'}…`
  if (event.event === 'mcp_tool_call_completed') return `Read ${event.tool ?? 'shop records'} from the MCP server.`
  if (event.event === 'mcp_tool_call_failed') return `Tool error: ${event.error ?? 'could not read shop records'}`
  if (event.event === 'agent_step_failed') return `Step stopped: ${event.error ?? 'agent error'}`
  if (event.event === 'human_approval_recorded') return `Human-approved ${event.approval_kind?.replaceAll('_', ' ') ?? 'payment'} for ${formatMoney(event.amount)} (${event.approved_by ?? 'approver recorded'}).`
  return event.summary ?? event.event.replaceAll('_', ' ')
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    const requestedTicket = Number(new URLSearchParams(window.location.search).get('ticket'))
    return [101, 102, 103].includes(requestedTicket) ? requestedTicket : null
  })
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [connection, setConnection] = useState<'checking' | 'online' | 'offline'>('checking')
  const [error, setError] = useState('')
  const [runningTicketId, setRunningTicketId] = useState<number | null>(null)
  const [runByTicket, setRunByTicket] = useState<Record<number, RunState>>({})
  const [approver, setApprover] = useState('')
  const [approvedRequests, setApprovedRequests] = useState<Set<string>>(new Set())
  const [notice, setNotice] = useState('')

  const selectedTicket = tickets.find((ticket) => ticket.id === selectedId) ?? null
  const runState = selectedId == null ? undefined : runByTicket[selectedId]

  async function loadTickets() {
    const result = await api<{ tickets: Ticket[] }>('/api/tickets')
    setTickets(result.tickets)
    setSelectedId((current) => current ?? result.tickets[0]?.id ?? null)
  }

  async function loadEvents() {
    const result = await api<{ events: AgentEvent[] }>('/api/events?limit=500')
    setEvents(result.events)
  }

  async function loadCash() {
    setCash(await api<Cash>('/api/cash'))
  }

  async function refreshBoard() {
    try {
      await Promise.all([loadTickets(), loadEvents(), loadCash()])
      setConnection('online')
      setError('')
    } catch (cause) {
      setConnection('offline')
      setError(cause instanceof Error ? cause.message : 'Could not reach the operations API.')
    }
  }

  useEffect(() => {
    void refreshBoard()
    const timer = window.setInterval(() => {
      void Promise.all([loadEvents(), loadCash()]).catch(() => setConnection('offline'))
    }, 1600)
    return () => window.clearInterval(timer)
  }, [])

  const selectedEvents = useMemo(() => {
    if (!selectedId) return []
    const startedAt = runState?.startedAt
    return events.filter((event) => {
      const selectedTicket = tickets.find((ticket) => ticket.id === selectedId)
      const belongsToSelected = event.ticket_id === selectedId || (
        event.event === 'human_approval_recorded' && selectedTicket != null && (
          (event.approval_kind === 'invoice' && selectedTicket.invoice_id === event.reference_id) ||
          (event.approval_kind === 'rent' && selectedTicket.lease_id === event.reference_id) ||
          (event.approval_kind === 'purchase_order' && selectedTicket.id === event.reference_id)
        )
      )
      if (!belongsToSelected) return false
      if (!startedAt) return true
      return new Date(event.timestamp).getTime() >= new Date(startedAt).getTime()
    })
  }, [events, runState?.startedAt, selectedId, tickets])

  const agentSummaries = useMemo(() => {
    return AGENTS.map((agent) => {
      const ownEvents = selectedEvents.filter((event) => event.agent === agent.id)
      const lastEvent = ownEvents[ownEvents.length - 1]
      const finished = [...ownEvents].reverse().find((event) => event.event === 'agent_step_completed')
      const latestTool = [...ownEvents].reverse().find((event) => event.event === 'mcp_tool_call_started')
      const latestStarted = [...ownEvents].reverse().find((event) => event.event === 'agent_step_started')
      const latestCompleted = [...ownEvents].reverse().find((event) => event.event === 'agent_step_completed')
      const isActive = runningTicketId === selectedId && Boolean(latestStarted) && (!latestCompleted || (latestStarted?.step ?? 0) > (latestCompleted.step ?? 0))
      const tools = Array.from(new Set(ownEvents.filter((event) => event.event === 'mcp_tool_call_started').map((event) => event.tool).filter(Boolean)))
      return {
        ...agent,
        lastEvent,
        finished,
        latestTool,
        tools,
        isActive,
        state: isActive ? 'Working' : finished ? 'Step complete' : ownEvents.length ? 'On the board' : 'Standing by',
      }
    })
  }, [selectedEvents, runningTicketId, selectedId])

  const approvals = useMemo(() => {
    const found: { key: string; agent: string; request: ApprovalRequest; paymentRecorded: boolean }[] = []
    for (const event of selectedEvents) {
      const report = event.report
      if (!report) continue
      for (const request of report.approval_requests ?? []) {
        if (!request.requires_human_approval || !['invoice', 'rent', 'purchase_order'].includes(request.kind)) continue
        const key = `${event.run_id ?? ''}:${report.agent}:${request.kind}:${request.reference_id ?? selectedId}`
        const paymentRecorded = selectedEvents.some((candidate) => (
          candidate.event === 'human_approval_recorded' &&
          candidate.approval_kind === request.kind &&
          candidate.reference_id === request.reference_id
        ))
        if (!found.some((entry) => entry.key === key)) found.push({ key, agent: report.agent, request, paymentRecorded })
      }
    }
    return found
  }, [selectedEvents, selectedId])

  const timeline = [...selectedEvents].reverse().slice(0, 14)

  async function startRun() {
    if (!selectedId || runningTicketId != null) return
    const ticketId = selectedId
    const startedAt = new Date(Date.now() - 800).toISOString()
    setRunningTicketId(ticketId)
    setRunByTicket((current) => ({ ...current, [ticketId]: { startedAt, complete: false } }))
    setNotice('')
    setError('')
    try {
      const response = await api<{ ticket_id: number; report: AgentReport }>(`/api/tickets/${ticketId}/run`, { method: 'POST' })
      setRunByTicket((current) => ({ ...current, [ticketId]: { startedAt, complete: true, report: response.report } }))
      setNotice(`Ticket ${ticketId} run finished. Review the agent notes and any approval requests.`)
      await refreshBoard()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The team run failed.')
      setRunByTicket((current) => ({ ...current, [ticketId]: { startedAt, complete: false } }))
    } finally {
      setRunningTicketId(null)
      void loadEvents()
    }
  }

  async function approve(request: ApprovalRequest, key: string) {
    if (!selectedId) return
    const human = approver.trim()
    if (!human) {
      setError('Enter your name before approving a payment or purchase.')
      return
    }
    if (request.reference_id == null) {
      setError('This approval is missing its database reference.')
      return
    }
    if (request.kind === 'purchase_order' && !request.vendor_id) {
      setError('This purchase approval is missing a vendor ID.')
      return
    }
    const confirmed = window.confirm(`Approve ${request.kind.replaceAll('_', ' ')} for ${formatMoney(request.amount)}? The backend will recheck the database and cash balance.`)
    if (!confirmed) return
    try {
      setError('')
      const response = await api<{ remaining_balance: number; status: string }>('/api/approvals', {
        method: 'POST',
        body: JSON.stringify({
          kind: request.kind,
          ref_id: request.reference_id,
          approved_by: human,
          amount: request.amount ?? undefined,
          vendor_id: request.vendor_id ?? undefined,
        }),
      })
      setApprovedRequests((current) => new Set(current).add(key))
      setNotice(`Approved. Checking balance is now ${formatMoney(response.remaining_balance)}.`)
      await Promise.all([loadCash(), loadTickets(), loadEvents()])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Approval was not recorded.')
    }
  }

  function ticketStatus(ticket: Ticket) {
    if (ticket.status === 'resolved') return 'Resolved'
    if (runningTicketId === ticket.id) return 'In progress'
    return ticket.status === 'open' ? 'Open' : ticket.status
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Campus Customs desk home">
          <span className="brand-mark">CC</span>
          <span className="brand-copy"><strong>Campus Customs</strong><small>multi-agent operations desk</small></span>
        </a>
        <div className="topbar-right">
          <div className={`connection ${connection}`}><span className="connection-dot" />{connection === 'online' ? 'Backend connected' : connection === 'offline' ? 'Backend offline' : 'Connecting'}</div>
          <div className="date-stamp"><span className="date-icon">✳</span> OPERATIONS / NEW HAVEN</div>
        </div>
      </header>

      <main id="top" className="desk-layout">
        <aside className="left-rail">
          <div className="section-kicker"><span>01</span> OPEN BOARD <span className="kicker-line" /></div>
          <div className="queue-heading"><h1>Today’s desk</h1><span className="count-pill">{tickets.length.toString().padStart(2, '0')}</span></div>
          <p className="rail-caption">Three threads to untangle. Choose a ticket to bring it to the center desk.</p>

          <nav className="ticket-list" aria-label="Campus Customs tickets">
            {tickets.map((ticket, index) => (
              <button key={ticket.id} className={`ticket-row ${selectedId === ticket.id ? 'selected' : ''}`} onClick={() => { setSelectedId(ticket.id); setNotice('') }}>
                <span className={`ticket-index index-${index + 1}`}>{String(ticket.id).slice(-2)}</span>
                <span className="ticket-row-copy">
                  <span className="ticket-type">{TYPE_LABELS[ticket.type] ?? ticket.type}</span>
                  <strong>{ticket.subject}</strong>
                  <small>{ticket.requester}</small>
                </span>
                <span className={`status-dot status-${ticketStatus(ticket).toLowerCase().replaceAll(' ', '-')}`} title={ticketStatus(ticket)} />
              </button>
            ))}
            {tickets.length === 0 && <div className="empty-queue">Waiting for the ticket board…</div>}
          </nav>

          <section className="cash-card" aria-label="Checking balance">
            <div className="cash-card-top"><span className="cash-icon">↘</span><span>CHECKING / CASH OUT ONLY</span></div>
            <p className="cash-label">Available balance</p>
            <strong className="cash-amount">{cash ? formatMoney(cash.balance) : '—'}</strong>
            <div className="cash-foot"><span>{cash ? `Ledger date ${cash.date}` : 'Syncing ledger'}</span><span className="cash-live"><i /> LIVE</span></div>
          </section>

          <div className="rail-note"><span className="note-star">✳</span><p>Nothing leaves the desk without a human’s say-so.</p></div>
        </aside>

        <section className="workbench">
          <div className="workbench-head">
            <div>
              <div className="section-kicker"><span>02</span> WORKBENCH <span className="kicker-line" /></div>
              <div className="ticket-title-line">
                <h2>{selectedTicket ? selectedTicket.subject : 'Select a ticket'}</h2>
                {selectedTicket && <span className={`large-status ${ticketStatus(selectedTicket).toLowerCase().replaceAll(' ', '-')}`}>{ticketStatus(selectedTicket)}</span>}
              </div>
              {selectedTicket && <p className="workbench-subtitle">Ticket {selectedTicket.id} <span>·</span> {TYPE_LABELS[selectedTicket.type] ?? selectedTicket.type} <span>·</span> Opened {formatTime(selectedTicket.created_at)}</p>}
            </div>
            <button className="run-button" onClick={startRun} disabled={!selectedTicket || runningTicketId != null || ticketStatus(selectedTicket) === 'Resolved'}>
              {runningTicketId === selectedId ? <><span className="button-spinner" /> Team at work</> : <><span>▶</span> Run this ticket</>}
            </button>
          </div>

          {selectedTicket ? (
            <>
              <div className="ticket-brief">
                <div className="brief-stamp">TICKET NOTE <span>#{selectedTicket.id}</span></div>
                <p>{selectedTicket.notes || 'No note attached to this ticket.'}</p>
                <div className="brief-facts">
                  {selectedTicket.sku && <span><small>SKU</small><strong>{selectedTicket.sku}</strong></span>}
                  {selectedTicket.size && <span><small>SIZE</small><strong>{selectedTicket.size}</strong></span>}
                  {selectedTicket.qty != null && <span><small>QTY</small><strong>{selectedTicket.qty}</strong></span>}
                  {selectedTicket.invoice_id != null && <span><small>INVOICE</small><strong>#{selectedTicket.invoice_id}</strong></span>}
                  {selectedTicket.lease_id != null && <span><small>LEASE</small><strong>#{selectedTicket.lease_id}</strong></span>}
                </div>
              </div>

              {runState?.complete && runState.report && (
                <section className="final-summary">
                  <div className="summary-icon">✓</div>
                  <div><div className="summary-kicker">BOSS · FINAL READ</div><p>{runState.report.summary}</p></div>
                </section>
              )}

              {approvals.length > 0 && (
                <section className="approval-section">
                  <div className="section-heading"><div><div className="section-kicker"><span>03</span> HUMAN REVIEW <span className="kicker-line" /></div><h3>Nothing moves without you.</h3></div><span className="approval-count">{approvals.filter((item) => !approvedRequests.has(item.key) && !item.paymentRecorded).length} pending</span></div>
                  <label className="approver-field">Approving as<input value={approver} onChange={(event) => setApprover(event.target.value)} placeholder="Your name" autoComplete="name" /></label>
                  <div className="approval-list">
                    {approvals.map(({ key, agent, request, paymentRecorded }) => {
                      const approved = approvedRequests.has(key) || paymentRecorded
                      return (
                        <article className={`approval-card ${approved ? 'approved' : ''}`} key={key}>
                          <div className="approval-symbol">{approved ? '✓' : '!'}</div>
                          <div className="approval-copy"><div className="approval-title">{request.kind.replaceAll('_', ' ')} <span>· {agentLabel(agent)}</span></div><p>{request.rationale}</p><strong>{formatMoney(request.amount)}</strong></div>
                          <button className="approve-button" disabled={approved || runningTicketId != null} onClick={() => void approve(request, key)}>{approved ? 'Approved' : 'Review & approve'}</button>
                        </article>
                      )
                    })}
                  </div>
                </section>
              )}

              {runState?.complete && runState.report && (
                <section className="recommendations">
                  <div className="section-kicker"><span>04</span> NEXT MOVES <span className="kicker-line" /></div>
                  <ul>{runState.report.recommendations?.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
                  {runState.report.customer_message_draft && <blockquote><span>DRAFT · NOT SENT</span>{runState.report.customer_message_draft}</blockquote>}
                </section>
              )}
            </>
          ) : <div className="empty-workbench">The desk is waiting for a ticket.</div>}

          {notice && <div className="notice" role="status"><span>✓</span>{notice}</div>}
          {error && <div className="error-banner" role="alert"><span>!</span>{error}<button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
        </section>

        <aside className="right-rail">
          <div className="section-kicker"><span>03</span> THE CREW <span className="kicker-line" /></div>
          <div className="crew-heading"><h2>Agent room</h2><span className={`crew-pulse ${runningTicketId != null ? 'active' : ''}`} />{runningTicketId != null && <small>LIVE</small>}</div>
          <p className="rail-caption">Their notes arrive as the team works.</p>

          <div className="agent-stack">
            {agentSummaries.map((agent) => (
              <article className={`agent-card ${agent.color} ${agent.isActive ? 'agent-active' : ''}`} key={agent.id}>
                <div className="agent-card-head"><span className="agent-avatar">{agent.initials}</span><div className="agent-name-wrap"><strong>{agent.name}</strong><small>{agent.role}</small></div><span className={`agent-state ${agent.isActive ? 'working' : ''}`}><i />{agent.state}</span></div>
                <p className="agent-says">{agent.finished?.report?.summary ?? (agent.isActive ? eventDescription(agent.lastEvent ?? { timestamp: '', event: 'agent_step_started' }) : agent.lastEvent ? eventDescription(agent.lastEvent) : 'No assignment on this ticket yet.')}</p>
                {agent.tools.length > 0 && <div className="tool-chips">{agent.tools.slice(-3).map((tool) => <span key={tool}>{tool}</span>)}</div>}
                {agent.isActive && agent.latestTool && <div className="current-tool"><span className="mini-spin" /> Calling {agent.latestTool.tool}</div>}
              </article>
            ))}
          </div>

          <section className="activity-card">
            <div className="activity-head"><div><div className="section-kicker"><span>04</span> LIVE NOTES <span className="kicker-line" /></div><h3>Run activity</h3></div><span className="activity-count">{timeline.length.toString().padStart(2, '0')}</span></div>
            <div className="activity-list">
              {timeline.length === 0 ? <p className="activity-empty">When a run starts, tool calls and agent notes will appear here.</p> : timeline.map((event, index) => (
                <div className="activity-item" key={`${event.timestamp}-${event.event}-${index}`}>
                  <span className={`activity-marker marker-${event.agent ?? 'system'}`} />
                  <div><div className="activity-meta"><strong>{agentLabel(event.agent)}</strong><time>{formatTime(event.timestamp)}</time></div><p>{eventDescription(event)}</p>{event.event === 'mcp_tool_call_completed' && event.tool && <span className="activity-tool">MCP · {event.tool}</span>}</div>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </main>
      <footer className="footer"><span>CC / CAMPUS CUSTOMS</span><span>LOCAL DESK · HUMAN IN THE LOOP</span><span>DATA VIA MCP</span></footer>
    </div>
  )
}
