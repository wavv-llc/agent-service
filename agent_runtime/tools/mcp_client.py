"""
MCP (Model Context Protocol) client.

Connects to a separately hosted MCP server and exposes its tools to the agent.
The server URL is read from the MCP_SERVER_URL environment variable.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MCP_SERVER_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:9000')


class MCPClientError(RuntimeError):
    """Raised when the MCP server returns an error or is unreachable."""


# ---------------------------------------------------------------------------
# Low-level transport helpers
# ---------------------------------------------------------------------------


def _post(path: str, payload: dict) -> dict:
    """POST *payload* to *MCP_SERVER_URL/path* and return the JSON response."""
    url = f'{MCP_SERVER_URL}{path}'
    try:
        resp = httpx.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        msg = f'MCP request to {url!r} failed: {exc}'
        raise MCPClientError(msg) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_tools() -> list[dict]:
    """
    Fetch the list of tools the MCP server exposes.
    Returns a list of tool schema dicts (name, description, input_schema).
    """
    data = _post('/tools/list', {})
    return data.get('tools', [])


def call_tool(tool_name: str, inputs: dict[str, Any]) -> Any:
    """
    Invoke *tool_name* on the MCP server with *inputs*.
    Returns the tool's output (JSON-decoded).
    """
    data = _post('/tools/call', {'name': tool_name, 'input': inputs})
    if data.get('isError'):
        msg = f"MCP tool {tool_name!r} returned an error: {data.get('content')}"
        raise MCPClientError(msg)
    return data.get('content')


# ---------------------------------------------------------------------------
# Anthropic tool schema for the MCP proxy tool
# ---------------------------------------------------------------------------

MCP_PROXY_SCHEMA: dict = {
    'name': 'mcp_client',
    'description': (
        'Call a tool on the remote MCP server. '
        'Use list_mcp_tools first to discover available tool names.'
    ),
    'input_schema': {
        'type': 'object',
        'required': ['tool_name', 'inputs'],
        'properties': {
            'tool_name': {
                'type': 'string',
                'description': 'Name of the MCP tool to invoke.',
            },
            'inputs': {
                'type': 'object',
                'description': 'Input parameters for the MCP tool.',
            },
        },
    },
}
