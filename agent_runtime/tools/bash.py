"""
Sandboxed CLI/Bash tool.

Safety measures
---------------
- Command allow-list (only explicitly permitted executables).
- Hard timeout to prevent runaway processes.
- No network access inside the sandbox (enforced at container level; flagged here).
- Working directory constrained to a per-task temp directory.
"""
from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALLOWED_COMMANDS: set[str] = {
    'python3',
    'python',
    'pip',
    'ls',
    'cat',
    'head',
    'tail',
    'wc',
    'grep',
    'awk',
    'sed',
    'echo',
    'printf',
    'date',
    'jq',
    'curl',  # curl allowed but sandboxed network should block real calls
}

DEFAULT_TIMEOUT_SECS = 30
MAX_OUTPUT_BYTES = 1_024 * 64  # 64 KB


class BashToolError(RuntimeError):
    """Raised when a command is rejected or fails fatally."""


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


def run_command(
    command: str,
    workdir: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECS,
) -> dict:
    """
    Run *command* in a sandboxed subprocess.

    Returns
    -------
    dict with keys: exit_code, stdout, stderr
    """
    tokens = shlex.split(command)
    if not tokens:
        msg = 'Empty command'
        raise BashToolError(msg)

    executable = Path(tokens[0]).name
    if executable not in ALLOWED_COMMANDS:
        msg = (
            f'Command {executable!r} is not in the allow-list. '
            f'Allowed: {sorted(ALLOWED_COMMANDS)}'
        )
        raise BashToolError(msg)

    # Use a temp directory if no workdir specified
    if workdir is None:
        workdir = tempfile.mkdtemp(prefix='agent_task_')

    try:
        proc = subprocess.run(
            tokens,
            cwd=workdir,
            capture_output=True,
            timeout=timeout,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as err:
        msg = f'Command timed out after {timeout}s: {command!r}'
        raise BashToolError(msg) from err

    return {
        'exit_code': proc.returncode,
        'stdout': proc.stdout[:MAX_OUTPUT_BYTES],
        'stderr': proc.stderr[:MAX_OUTPUT_BYTES],
    }


# ---------------------------------------------------------------------------
# Anthropic tool schema (used when registering with the agent)
# ---------------------------------------------------------------------------

TOOL_SCHEMA: dict = {
    'name': 'bash',
    'description': (
        'Run a shell command in a sandboxed environment. '
        'Only allow-listed executables are permitted.'
    ),
    'input_schema': {
        'type': 'object',
        'required': ['command'],
        'properties': {
            'command': {
                'type': 'string',
                'description': 'The shell command to execute.',
            },
            'workdir': {
                'type': 'string',
                'description': 'Working directory for the command (optional).',
            },
        },
    },
}
