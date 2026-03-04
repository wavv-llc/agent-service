"""
RBAC validation — checks whether an org is allowed to run a given task type
and use the requested tools.

In production this would query a database / auth service.
Here we define a simple in-memory stub that can be swapped out.
"""
from __future__ import annotations

from shared.constants import ALL_TASK_TYPES, ToolName
from shared.types import OrgPermissions


class RBACError(PermissionError):
    """Raised when RBAC check fails."""


# ---------------------------------------------------------------------------
# Stub permission store (replace with DB / external service)
# ---------------------------------------------------------------------------
_ORG_PERMISSIONS: dict[str, OrgPermissions] = {
    'org_demo': OrgPermissions(
        org_id='org_demo',
        allowed_task_types=ALL_TASK_TYPES,
        allowed_tools=[
            ToolName.BASH,
            ToolName.FILE_EXCEL,
            ToolName.FILE_WORD,
            ToolName.FILE_PDF,
            ToolName.MCP_CLIENT,
        ],
    ),
}


def get_org_permissions(org_id: str) -> OrgPermissions:
    """Return permissions for *org_id* or raise RBACError if unknown."""
    perms = _ORG_PERMISSIONS.get(org_id)
    if perms is None:
        msg = f'Unknown org: {org_id!r}'
        raise RBACError(msg)
    return perms


def validate_task(org_id: str, task_type: str, requested_tools: list[str]) -> None:
    """
    Raise RBACError if the org is not permitted to run *task_type* or use
    any of the *requested_tools*.
    """
    perms = get_org_permissions(org_id)

    if task_type not in perms.allowed_task_types:
        msg = f'Org {org_id!r} is not permitted to run task type {task_type!r}'
        raise RBACError(msg)

    disallowed = [t for t in requested_tools if t not in perms.allowed_tools]
    if disallowed:
        msg = f'Org {org_id!r} is not permitted to use tools: {disallowed}'
        raise RBACError(msg)
