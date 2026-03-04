"""
Planning step — breaks a task into discrete steps before execution begins.

Uses structured tool-use so the model returns a typed plan, not free text.
"""
from __future__ import annotations

from typing import Any

import anthropic

from agent_runtime.observability import AgentTracer
from shared.types import AgentPlan, PlanStep, SkillConfig, TaskRequest

_client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------

_PLAN_TOOL: dict = {
    'name': 'create_plan',
    'description': (
        'Create a step-by-step execution plan for the task. '
        'Each step should reference the tool it will use (if any).'
    ),
    'input_schema': {
        'type': 'object',
        'required': ['steps'],
        'properties': {
            'steps': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'required': ['step_number', 'description'],
                    'properties': {
                        'step_number': {'type': 'integer'},
                        'description': {'type': 'string'},
                        'tool': {'type': 'string'},
                        'inputs': {'type': 'object'},
                    },
                },
            }
        },
    },
}


def plan(
    task: TaskRequest, skill: SkillConfig, tracer: AgentTracer, parent_span: Any = None
) -> AgentPlan:
    """
    Call the LLM to produce a structured plan for *task* given *skill* config.
    Returns an AgentPlan with ordered PlanStep objects.
    """
    system = (
        f'You are a planning agent. Task type: {task.task_type}. '
        f'Allowed tools: {skill.allowed_tools}. '
        f'Max steps: {skill.max_steps}. '
        'Break the task into concrete, ordered steps using the create_plan tool.'
    )
    user_content = (
        f"Task description: {task.input_context.get('task_description', '')}\n"
        f"Input context: {task.input_context}\n"
        f"Documents: {task.document_ids}"
    )
    messages = [{'role': 'user', 'content': user_content}]

    response = _client.messages.create(
        model=skill.model,
        max_tokens=1024,
        system=system,
        tools=[_PLAN_TOOL],
        tool_choice={'type': 'any'},
        messages=messages,
    )

    tracer.llm_call(
        model=skill.model,
        prompt=messages,
        response=[b.model_dump() for b in response.content],
        name='planning-llm',
        parent=parent_span,
    )

    steps: list[PlanStep] = []
    for block in response.content:
        if block.type == 'tool_use' and block.name == 'create_plan':
            for s in block.input.get('steps', []):
                steps.append(PlanStep(**s))
            break

    return AgentPlan(task_id=task.task_id, steps=steps)
