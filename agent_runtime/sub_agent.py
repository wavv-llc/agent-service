"""
Sub-agent spawning — runs a child agent in-process, inheriting the parent's
tool constraints (allowed_tools) but scoped to a sub-task.

Sub-agents do NOT spin up a new container; they reuse the same lifecycle
logic with a narrowed context. This makes them cheap to spawn and keeps
them within the parent's security boundary.
"""
from __future__ import annotations

import logging

from shared.types import TaskRequest, TaskResult

logger = logging.getLogger(__name__)


def spawn_sub_agent(
    parent_task: TaskRequest,
    sub_task_description: str,
    sub_task_type: str | None = None,
    additional_context: dict | None = None,
) -> TaskResult:
    """
    Spawn a sub-agent to handle *sub_task_description*.

    The sub-agent:
    - Inherits parent's allowed_tools, org_id, and auth_token.
    - Runs the full plan → execute → validate lifecycle.
    - Returns a TaskResult that the parent can inspect.

    Parameters
    ----------
    parent_task:
        The originating TaskRequest (provides auth + tool constraints).
    sub_task_description:
        What the sub-agent should do.
    sub_task_type:
        Optional override for task_type; defaults to parent's task_type.
    additional_context:
        Extra context merged into the sub-task's input_context.
    """
    # Avoid circular import — lifecycle imports sub_agent, sub_agent needs lifecycle
    from agent_runtime.lifecycle import run_task

    sub_task = TaskRequest(
        task_type=sub_task_type or parent_task.task_type,
        org_id=parent_task.org_id,
        auth_token=parent_task.auth_token,
        allowed_tools=parent_task.allowed_tools,  # inherit constraints
        document_ids=parent_task.document_ids,
        input_context={
            **parent_task.input_context,
            **(additional_context or {}),
            'task_description': sub_task_description,
            'is_sub_agent': True,
            'parent_task_id': parent_task.task_id,
        },
    )

    logger.info(
        'Spawning sub-agent for parent=%s type=%s',
        parent_task.task_id,
        sub_task.task_type,
    )

    return run_task(sub_task)
