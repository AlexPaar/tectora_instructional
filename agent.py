#!/usr/bin/env python3
"""Tectora 🏛️ Deep Agent."""

import asyncio
import os
import sys
from typing import Any

import typer
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from prompt_toolkit import PromptSession
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel

from tools.dhsn import search_contact
from tools.load_thesis_artifacts import load_thesis_artifacts
from tools.retrieve_academics import retrieve_academic_by_name, retrieve_academics_from_ids
from tools.retrieve_theses import retrieve_theses
from tools.weather import get_current_weather
from utils.keycloak_auth import get_access_token

load_dotenv()

app = typer.Typer(help="Deep Agent Institute Assistant.")

console = Console()

console.print("[dim]Initializing Tectora 🏛️ deep agent...[/dim]")

PYTHON_ENV = os.getenv("PYTHON_ENV", "production").lower()

MODEL_ENV = os.getenv("MODEL_ENV", "litellm").lower()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

WORKSPACE_DIR = os.path.join(SCRIPT_DIR, "workspace")

MODEL_CHAT = os.getenv("MODEL_CHAT", "openai:gpt-4o-mini")

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://localhost:4000/v1")

litellm_virtual_key = (
    os.getenv("SK_DEVELOPMENT", "sk-development-pb") if PYTHON_ENV == "development" else os.getenv("SK_LITELLM")
)

GITHUB_MCP_PAT = os.getenv("GITHUB_MCP_PAT")

backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/workspace/": FilesystemBackend(
            root_dir=WORKSPACE_DIR,
            virtual_mode=True,
        ),
        "/skills/": FilesystemBackend(
            root_dir=os.path.join(SCRIPT_DIR, "skills"),
            virtual_mode=True,
        ),
    },
)

_mcp_client: Any | None = None

MCP_SERVER_REGISTRY: dict[str, dict[str, Any]] = {
    "pizza_ops_server": {
        "path": os.path.join("mcp", "pizza-ops", "pizza_ops_server.py"),
        "transport": "stdio",
        "command": sys.executable,
        "args": [],
    },
    "github": {
        "transport": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": ({"Authorization": f"Bearer {GITHUB_MCP_PAT}"} if GITHUB_MCP_PAT else {}),
    },
}


async def _load_mcp_tools() -> list[Any]:
    """Load MCP tools from configured MCP servers (local and remote)."""
    global _mcp_client

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient  # pyright: ignore[reportMissingImports]
    except ImportError:
        console.print(
            "[yellow]Optional dependency missing:[/yellow] langchain-mcp-adapters. Install it to enable MCP tools."
        )
        return []

    server_configs: dict[str, dict[str, Any]] = {}

    for server_name, server_spec in MCP_SERVER_REGISTRY.items():
        transport = str(server_spec.get("transport", "stdio")).lower()

        if transport == "stdio":
            server_path_value = server_spec.get("path")

            if not isinstance(server_path_value, str) or not server_path_value:
                console.print(f"[yellow]Invalid MCP server path for:[/yellow] {server_name}")
                continue

            server_path = os.path.join(SCRIPT_DIR, server_path_value)

            if not os.path.exists(server_path):
                console.print(f"[yellow]MCP server not found:[/yellow] {server_path}")
                continue

            command = server_spec.get("command")

            args = server_spec.get("args", [])

            if not isinstance(command, str) or not command:
                console.print(f"[yellow]Invalid MCP server command for:[/yellow] {server_name}")
                continue

            if not isinstance(args, list):
                console.print(f"[yellow]Invalid MCP server args for:[/yellow] {server_name}")
                continue

            server_configs[server_name] = {
                "transport": transport,
                "command": command,
                "args": [server_path, *args],
            }
            continue

        if transport in {"http", "sse"}:
            url = server_spec.get("url")

            if not isinstance(url, str) or not url:
                console.print(f"[yellow]Invalid MCP server URL for:[/yellow] {server_name}")
                continue

            remote_config: dict[str, Any] = {"transport": transport, "url": url}

            headers = server_spec.get("headers")

            if isinstance(headers, dict):
                safe_headers = {k: v for k, v in headers.items() if isinstance(k, str) and isinstance(v, str) and v}
                if safe_headers:
                    remote_config["headers"] = safe_headers

            server_configs[server_name] = remote_config
            continue

        console.print(f"[yellow]Unsupported MCP transport for {server_name}:[/yellow] {transport}")

    if not server_configs:
        return []

    _mcp_client = MultiServerMCPClient(server_configs)

    return await _mcp_client.get_tools()


async def _close_mcp_client() -> None:
    """Close the configured MCP client when the host application shuts down."""
    global _mcp_client

    if _mcp_client is None:
        return

    close = getattr(_mcp_client, "aclose", None) or getattr(_mcp_client, "close", None)
    if close is not None:
        result = close()
        if hasattr(result, "__await__"):
            await result

    _mcp_client = None


_mcp_tools: list[Any] = asyncio.run(_load_mcp_tools())

if _mcp_tools:
    console.print(f"[dim]Loaded {len(_mcp_tools)} MCP {escape('tool')}{'s' if len(_mcp_tools) > 1 else ''}.[/dim]")


def _build_agent(
    checkpointer=None,
    mcp_tools: list[Any] | None = None,
    agent_backend: FilesystemBackend | None = None,
):
    """Create the deep agent, optionally with a caller-provided checkpointer."""
    base_tools = [
        get_current_weather,
        search_contact,
        load_thesis_artifacts,
        retrieve_theses,
        retrieve_academic_by_name,
        retrieve_academics_from_ids,
    ]

    tools = [*base_tools, *(mcp_tools or [])]

    subagents = []

    if MODEL_ENV == "direct":
        llm = MODEL_CHAT
    else:
        llm = ChatOpenAI(
            model=MODEL_CHAT.rsplit(":", 1)[-1],  # Must match a model allowed by your LiteLLM team
            base_url=LITELLM_BASE_URL,
            api_key=litellm_virtual_key,
        )

    return create_deep_agent(
        model=llm,
        backend=agent_backend if agent_backend is not None else backend,
        tools=tools,
        subagents=subagents,
        skills=["/skills/agent/"],
        system_prompt=get_system_prompt(),
        checkpointer=checkpointer,
        debug=False,
    )


def _extract_text_from_content(content: Any) -> str:
    """Extract readable text from common message content shapes."""
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)

    return ""


def _extract_text_from_message(message: Any) -> str:
    """Extract readable text from message objects or dicts."""
    if isinstance(message, dict):
        return _extract_text_from_content(message.get("content", ""))

    text_attr = getattr(message, "text", None)
    if isinstance(text_attr, str) and text_attr:
        return text_attr

    content = getattr(message, "content", "")
    return _extract_text_from_content(content)


def _find_latest_message_text(payload: Any) -> str:
    """Recursively find the latest message text in nested stream payloads."""
    if payload is None:
        return ""

    # Direct message-like object/dict.
    direct_text = _extract_text_from_message(payload)
    if direct_text:
        return direct_text

    # LangGraph may stream tuples like (message_chunk, metadata).
    if isinstance(payload, tuple):
        for item in payload:
            text = _find_latest_message_text(item)
            if text:
                return text
        return ""

    # Handle lists of messages/events.
    if isinstance(payload, list):
        for item in reversed(payload):
            text = _find_latest_message_text(item)
            if text:
                return text
        return ""

    # Handle nested dict updates such as {"agent": {"messages": [...]}}.
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            text = _find_latest_message_text(messages[-1])
            if text:
                return text

        for value in payload.values():
            text = _find_latest_message_text(value)
            if text:
                return text

    return ""


def _parse_stream_event(event: Any) -> tuple[str, str]:
    """Normalize stream events to (event_type, text)."""
    # Object-like events (older/newer wrappers that expose attributes).
    if hasattr(event, "type"):
        event_type = str(event.type)
        content = getattr(event, "content", "")
        text = _extract_text_from_content(content)
        return event_type, text

    # Dict-like events (LangGraph/deepagents state updates).
    if isinstance(event, dict):
        if "type" in event:
            event_type = str(event.get("type"))
            text = _extract_text_from_content(event.get("content", ""))
            return event_type, text

        text = _find_latest_message_text(event)
        if text:
            return "message", text

    # Tuple/list events can appear in some stream modes.
    if isinstance(event, tuple | list):
        text = _find_latest_message_text(event)
        if text:
            return "message", text

    return "", ""


async def _interactive_agent_loop(thread_id: str = "cli-session"):
    """The actual asynchronous chat loop for your agent."""
    cli_agent = _build_agent(checkpointer=InMemorySaver(), mcp_tools=_mcp_tools)

    session = PromptSession()

    console.print(f"[bold green]Tectora 🏛️ Deep Agent initialized with {MODEL_CHAT}[/bold green]\n")

    while True:
        try:
            user_input = await session.prompt_async("You ❯ ")

            if user_input.strip().lower() in ("exit", "quit"):
                break

            # Your deep agent streaming logic goes here...
            console.print(f"[dim]Processing via {MODEL_CHAT}...[/dim]")

            last_text = ""
            with Live("", console=console, refresh_per_second=12) as live:
                payload = {"messages": [{"role": "user", "content": user_input}]}
                async for event in cli_agent.astream(
                    payload,
                    config={"configurable": {"thread_id": thread_id, "litellm_virtual_key": litellm_virtual_key}},
                ):
                    event_type, event_text = _parse_stream_event(event)

                    if event_type == "message" and event_text:
                        last_text = event_text
                        live.update(Panel(Markdown(event_text), title="Agent Response"))
                    elif event_type == "error":
                        live.update(Panel(f"[bold red]Error:[/bold red] {event_text or event}", title="Agent Error"))
                    elif event_type == "done":
                        break

            if not last_text:
                console.print(Panel("The agent completed without a text response.", title="Agent Response"))

        except (KeyboardInterrupt, EOFError):
            break


def _invoke_thread(message: str, thread_id: str):
    """Invoke the agent within a specific LangGraph thread."""
    cli_agent = _build_agent(checkpointer=InMemorySaver(), mcp_tools=_mcp_tools)

    payload = {"messages": [{"role": "user", "content": message}]}
    return cli_agent.invoke(
        payload, config={"configurable": {"thread_id": thread_id, "litellm_virtual_key": litellm_virtual_key}}
    )


def get_system_prompt() -> str:
    """Return the system prompt for the deep agent."""
    return """
    You are a research data management assistant. Your job is research data ingestion and research.

    IMPORTANT: Before answering, ALWAYS check the Available Skills list. If any skill's description matches the user's request, you MUST first read its SKILL.md with `read_file` and follow its instructions yourself before responding.

    Skills are not subagents. A skill's `name` frontmatter is only an identifier for a markdown file, never a valid
    subagent type. Never call the subagent-dispatch tool with a skill's name. Only dispatch to a subagent using one
    of the exact `name` values listed under "Available Subagents" (if any are listed) - "general-purpose" is always valid.
    """


agent = _build_agent(mcp_tools=_mcp_tools)


@app.command()
def main(
    query: str | None = typer.Argument(None, help="The query for the institute assistant."),
    thread_id: str = typer.Option("cli-session", help="Thread identifier used to preserve agent state."),
):
    """Deep Agent Institute Assistant."""
    global litellm_virtual_key

    if PYTHON_ENV == "development":
        console.print("[dim]Authenticated as developer! 🔐[/dim]")
    else:
        try:
            console.print("[dim]Authenticating... 🔒[/dim]")

            access_token = get_access_token()

            litellm_virtual_key = access_token["litellm_sk"]
            groups = access_token["groups"]

            console.print(f"[dim]Authenticated as member of {', '.join(groups)}! 🔓[/dim]")
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]Authentication failed:[/yellow] {e}")
            sys.exit(1)

    try:
        if query:
            result = _invoke_thread(query, thread_id)

            last_message = result["messages"][-1]
            md = Markdown(_extract_text_from_message(last_message))
            console.print("\n")
            console.print(md)
        else:
            asyncio.run(_interactive_agent_loop(thread_id))
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.run(_close_mcp_client())
        if not query:
            console.print("\n[bold blue]Goodbye![/bold blue]")


if __name__ == "__main__":
    app()
