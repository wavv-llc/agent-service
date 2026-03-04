"""
Shared Pydantic models used by both orchestrator and agent-runtime.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.constants import TaskStatus

# ---------------------------------------------------------------------------
# Core task envelope (orchestrator → agent-runtime)
# ---------------------------------------------------------------------------


class TaskRequest(BaseModel):
    """Payload the orchestrator enqueues for the agent-runtime."""

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = Field(..., description='One of TaskType.*')
    org_id: str = Field(..., description='Originating organisation')
    auth_token: str = Field(..., description='Scoped auth token for this task')
    allowed_tools: list[str] = Field(
        default_factory=list,
        description='Subset of ToolName.* the agent is allowed to use',
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description='IDs of documents / blobs attached to this task',
    )
    input_context: dict[str, Any] = Field(
        default_factory=dict,
        description='Arbitrary structured context forwarded to the agent',
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Skill configuration (loaded by agent-runtime)
# ---------------------------------------------------------------------------


class SkillConfig(BaseModel):
    """Defines what an agent can do for a given task_type."""

    task_type: str
    allowed_tools: list[str]
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description='JSON Schema that the agent output must satisfy',
    )
    max_steps: int = 10
    model: str = 'claude-sonnet-4-6'


# ---------------------------------------------------------------------------
# Plan produced by the planning step
# ---------------------------------------------------------------------------


class PlanStep(BaseModel):
    step_number: int
    description: str
    tool: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    task_id: str
    steps: list[PlanStep]


# ---------------------------------------------------------------------------
# Step execution result
# ---------------------------------------------------------------------------


class StepResult(BaseModel):
    step_number: int
    success: bool
    output: Any = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Final task result (agent-runtime → orchestrator)
# ---------------------------------------------------------------------------


class TaskResult(BaseModel):
    task_id: str
    status: str = TaskStatus.COMPLETED
    output: Any = None
    error: str | None = None
    plan: AgentPlan | None = None
    step_results: list[StepResult] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Task status response (for polling endpoint)
# ---------------------------------------------------------------------------


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: TaskResult | None = None
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# RBAC primitives
# ---------------------------------------------------------------------------


class OrgPermissions(BaseModel):
    org_id: str
    allowed_task_types: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
