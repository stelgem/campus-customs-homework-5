"""PydanticAI Campus Customs team with MCP-only shop data access."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from openai import AsyncOpenAI
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.models import AgentReport


PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
PROMPTS_DIR = PROJECT_DIR / "backend" / "prompts"
MCP_SERVER_FILE = PROJECT_DIR / "mcp_server" / "server.py"
AUDIT_FILE = PROJECT_DIR / "output" / "audit_trail.json"
MODEL_ID = "gpt-6-luna"
MAX_AGENT_RUNS = 10
MAX_DELEGATION_DEPTH = 4

ROLE_PROMPTS = {
    "boss": "boss.md",
    "inventory": "inventory.md",
    "accounting": "accounting.md",
    "facilities": "facilities.md",
    "customer_service": "customer_service.md",
}


@dataclass
class RunBudget:
    agent_runs: int = 0
    lock: asyncio.Lock | None = None

    def __post_init__(self) -> None:
        if self.lock is None:
            self.lock = asyncio.Lock()


@dataclass
class TeamDependencies:
    mcp_session: ClientSession
    agents: dict[str, Agent[Any, AgentReport]]
    run_id: str
    budget: RunBudget
    ticket_id: int | None = None
    delegation_depth: int = 0
    current_agent: str = "system"


class AgentBudgetExceeded(RuntimeError):
    """Raised when a run reaches its agent-call budget."""


def append_audit_event(event: dict[str, Any]) -> None:
    """Append one event to a valid JSON array without replacing prior events."""
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    encoded_event = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    descriptor = os.open(AUDIT_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        size = os.fstat(descriptor).st_size
        os.lseek(descriptor, 0, os.SEEK_SET)
        existing = os.read(descriptor, size) if size else b""
        if not existing.strip():
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, b"[\n" + encoded_event + b"\n]\n")
        else:
            parsed = json.loads(existing)
            if not isinstance(parsed, list):
                raise ValueError(f"Audit file must contain a JSON array: {AUDIT_FILE}")
            closing_bracket = existing.rfind(b"]")
            if closing_bracket < 0:
                raise ValueError(f"Audit file has no closing array bracket: {AUDIT_FILE}")
            delimiter = b"\n" if not parsed else b",\n"
            suffix = delimiter + encoded_event + b"\n]\n"
            os.ftruncate(descriptor, closing_bracket)
            os.lseek(descriptor, closing_bracket, os.SEEK_SET)
            os.write(descriptor, suffix)
        os.fsync(descriptor)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


async def _audit(event_type: str, **fields: Any) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **fields,
    }
    await asyncio.to_thread(append_audit_event, event)


async def _call_mcp_tool(
    ctx: RunContext[TeamDependencies],
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    deps = ctx.deps
    args = arguments or {}
    await _audit(
        "mcp_tool_call_started",
        run_id=deps.run_id,
        agent=deps.current_agent,
        ticket_id=args.get("ticket_id", deps.ticket_id),
        tool=tool_name,
        arguments=args,
    )
    try:
        result = await deps.mcp_session.call_tool(tool_name, args)
        if result.isError:
            message = "\n".join(
                block.text for block in result.content if hasattr(block, "text")
            )
            raise RuntimeError(message or f"MCP tool {tool_name} failed")
        output = getattr(result, "structuredContent", None)
        if output is None:
            text_blocks = [block.text for block in result.content if hasattr(block, "text")]
            if text_blocks:
                try:
                    output = json.loads(text_blocks[0])
                except json.JSONDecodeError:
                    output = {"result_text": "\n".join(text_blocks)}
            else:
                output = {}
        if not isinstance(output, dict):
            output = {"result": output}
        await _audit(
            "mcp_tool_call_completed",
            run_id=deps.run_id,
            agent=deps.current_agent,
            ticket_id=args.get("ticket_id", deps.ticket_id),
            tool=tool_name,
            output=output,
        )
        return output
    except Exception as error:
        await _audit(
            "mcp_tool_call_failed",
            run_id=deps.run_id,
            agent=deps.current_agent,
            ticket_id=args.get("ticket_id", deps.ticket_id),
            tool=tool_name,
            error=f"{type(error).__name__}: {error}",
        )
        raise


async def list_open_tickets(ctx: RunContext[TeamDependencies]) -> dict[str, Any]:
    """Read the current open ticket board from MCP."""
    return await _call_mcp_tool(ctx, "list_open_tickets")


async def get_customer_order_context(
    ctx: RunContext[TeamDependencies], ticket_id: int
) -> dict[str, Any]:
    """Read ticket, stock, invoice, and supplier context for a customer order."""
    return await _call_mcp_tool(ctx, "get_customer_order_context", {"ticket_id": ticket_id})


async def get_rent_ticket_context(
    ctx: RunContext[TeamDependencies], ticket_id: int
) -> dict[str, Any]:
    """Read the rent ticket, linked lease, and authoritative shop date."""
    return await _call_mcp_tool(ctx, "get_rent_ticket_context", {"ticket_id": ticket_id})


async def get_bulk_discount_context(
    ctx: RunContext[TeamDependencies], ticket_id: int
) -> dict[str, Any]:
    """Read requested bulk quantity, matching stock, and listed SKU prices."""
    return await _call_mcp_tool(ctx, "get_bulk_discount_context", {"ticket_id": ticket_id})


async def get_accounting_context(ctx: RunContext[TeamDependencies]) -> dict[str, Any]:
    """Read the shop date, cash accounts, invoices, and payments from MCP."""
    return await _call_mcp_tool(ctx, "get_accounting_context")


async def get_vendor_restock_context(
    ctx: RunContext[TeamDependencies], vendor_id: int
) -> dict[str, Any]:
    """Read vendor specialty, lead time, and open invoices from MCP."""
    return await _call_mcp_tool(ctx, "get_vendor_restock_context", {"vendor_id": vendor_id})


MCP_TOOLS_BY_ROLE: dict[str, tuple[Any, ...]] = {
    "boss": (
        list_open_tickets,
        get_customer_order_context,
        get_rent_ticket_context,
        get_bulk_discount_context,
        get_accounting_context,
        get_vendor_restock_context,
    ),
    "inventory": (
        get_customer_order_context,
        get_bulk_discount_context,
        get_vendor_restock_context,
        get_accounting_context,
    ),
    "accounting": (
        get_accounting_context,
        get_customer_order_context,
        get_rent_ticket_context,
        get_bulk_discount_context,
    ),
    "facilities": (get_rent_ticket_context, get_accounting_context),
    "customer_service": (
        get_customer_order_context,
        get_bulk_discount_context,
        get_rent_ticket_context,
    ),
}


def _delegation_tool(target_role: str):
    async def delegate_to_teammate(
        ctx: RunContext[TeamDependencies], task: str
    ) -> AgentReport:
        """Ask the named teammate to investigate a focused part of the ticket."""
        deps = ctx.deps
        ticket_id = deps.ticket_id
        await _audit(
            "agent_delegation_started",
            run_id=deps.run_id,
            agent=deps.current_agent,
            delegate=target_role,
            ticket_id=ticket_id,
            task=task[:3000],
            depth=deps.delegation_depth + 1,
        )
        if deps.delegation_depth >= MAX_DELEGATION_DEPTH:
            response = AgentReport(
                agent=target_role,
                ticket_id=ticket_id,
                status="blocked",
                summary="Delegation depth limit reached; route the remaining question to a human.",
                findings=["The team reached its configured delegation depth limit."],
            )
        else:
            try:
                response = await _run_agent(
                    target_role,
                    task,
                    deps,
                    ticket_id=ticket_id,
                    depth=deps.delegation_depth + 1,
                )
            except AgentBudgetExceeded as error:
                response = AgentReport(
                    agent=target_role,
                    ticket_id=ticket_id,
                    status="blocked",
                    summary="Agent call budget reached; further delegation is stopped.",
                    findings=[str(error)],
                )
        await _audit(
            "agent_delegation_completed",
            run_id=deps.run_id,
            agent=deps.current_agent,
            delegate=target_role,
            ticket_id=ticket_id,
            status=response.status,
            summary=response.summary,
        )
        return response

    delegate_to_teammate.__name__ = f"delegate_to_{target_role}"
    delegate_to_teammate.__doc__ = (
        f"Delegate a focused investigation or task to the {target_role.replace('_', ' ')} agent. "
        "Pass the ticket ID and the precise question to answer."
    )
    return delegate_to_teammate


def build_agents(model: OpenAIChatModel) -> dict[str, Agent[Any, AgentReport]]:
    agents: dict[str, Agent[Any, AgentReport]] = {}
    for role, prompt_file in ROLE_PROMPTS.items():
        prompt = (PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
        agents[role] = Agent(
            model,
            deps_type=TeamDependencies,
            output_type=AgentReport,
            system_prompt=prompt,
        )

    for role, agent in agents.items():
        for mcp_tool in MCP_TOOLS_BY_ROLE[role]:
            agent.tool(mcp_tool)
        for target_role in agents:
            if target_role != role:
                agent.tool(_delegation_tool(target_role))
    return agents


async def _run_agent(
    role: str,
    task: str,
    deps: TeamDependencies,
    *,
    ticket_id: int | None,
    depth: int,
) -> AgentReport:
    assert deps.budget.lock is not None
    async with deps.budget.lock:
        if deps.budget.agent_runs >= MAX_AGENT_RUNS:
            raise AgentBudgetExceeded(
                f"The run is limited to {MAX_AGENT_RUNS} agent runs to control token use."
            )
        deps.budget.agent_runs += 1
        run_number = deps.budget.agent_runs

    agent_deps = replace(
        deps,
        ticket_id=ticket_id,
        delegation_depth=depth,
        current_agent=role,
    )
    await _audit(
        "agent_step_started",
        run_id=deps.run_id,
        agent=role,
        ticket_id=ticket_id,
        step=run_number,
        depth=depth,
        task=task[:4000],
    )
    try:
        result = await deps.agents[role].run(
            task,
            deps=agent_deps,
            usage_limits=UsageLimits(request_limit=4, output_tokens_limit=1200),
        )
        report: AgentReport = result.output
        await _audit(
            "agent_step_completed",
            run_id=deps.run_id,
            agent=role,
            ticket_id=ticket_id,
            step=run_number,
            status=report.status,
            report=report.model_dump(mode="json"),
        )
        return report
    except Exception as error:
        await _audit(
            "agent_step_failed",
            run_id=deps.run_id,
            agent=role,
            ticket_id=ticket_id,
            step=run_number,
            error=f"{type(error).__name__}: {error}",
        )
        raise


async def run_ticket_loop(ticket_id: int | None = None) -> AgentReport:
    """Run Boss and its delegated team for one ticket, or the entire open board."""
    for env_file in (PROJECT_DIR / ".env", WORKSPACE_DIR / ".env"):
        if env_file.is_file():
            load_dotenv(env_file)
            break
    api_key = os.environ["PORTKEY_API_KEY"]
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.portkey.ai/v1",
        default_headers={"x-portkey-api-key": api_key},
    )
    provider = OpenAIProvider(openai_client=openai_client)
    # Portkey's gpt-6-luna chat-completions route supports function tools only
    # when reasoning_effort is "none". Keep the required model and make that
    # compatibility explicit for PydanticAI's tool-enabled agent requests.
    model = OpenAIChatModel(
        MODEL_ID,
        provider=provider,
        settings={"openai_reasoning_effort": "none"},
    )
    agents = build_agents(model)
    run_id = str(uuid.uuid4())
    deps: TeamDependencies | None = None
    try:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(MCP_SERVER_FILE)],
            cwd=str(PROJECT_DIR),
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                deps = TeamDependencies(
                    mcp_session=session,
                    agents=agents,
                    run_id=run_id,
                    budget=RunBudget(),
                    ticket_id=ticket_id,
                )
                task = (
                    "Review the open ticket board, investigate every currently open ticket, "
                    "delegate focused work to the relevant teammates, and return a consolidated "
                    "final recommendation. Do not claim actions requiring human approval are done."
                    if ticket_id is None
                    else f"Handle open ticket {ticket_id}. Verify it is on the open ticket board, "
                    "delegate focused work to the relevant teammates, and return the final "
                    "recommendation. Do not claim actions requiring human approval are done."
                )
                await _audit(
                    "agent_loop_started",
                    run_id=run_id,
                    ticket_id=ticket_id,
                    model=MODEL_ID,
                    max_agent_runs=MAX_AGENT_RUNS,
                    max_delegation_depth=MAX_DELEGATION_DEPTH,
                )
                report = await _run_agent(
                    "boss", task, deps, ticket_id=ticket_id, depth=0
                )
                await _audit(
                    "agent_loop_completed",
                    run_id=run_id,
                    ticket_id=ticket_id,
                    status=report.status,
                    report=report.model_dump(mode="json"),
                    agent_runs=deps.budget.agent_runs,
                )
                return report
    finally:
        await openai_client.close()


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    parser.add_argument("--ticket-id", type=int, help="Handle one open ticket; omit to review the open board.")
    args = parser.parse_args()
    report = await run_ticket_loop(args.ticket_id)
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
