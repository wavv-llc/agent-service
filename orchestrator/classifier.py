"""
Task classifier — maps a raw task request to a TaskType using structured
tool-use (Claude function-calling), NOT free-form LLM generation.

The classifier calls the Anthropic API with a strict tool schema so the
model must return exactly one of the known task types.
"""
from __future__ import annotations

import anthropic

from shared.constants import ALL_TASK_TYPES, TaskType

_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

# ---------------------------------------------------------------------------
# Tool schema exposed to the model
# ---------------------------------------------------------------------------
_CLASSIFY_TOOL: dict = {
    'name': 'classify_task',
    'description': (
        'Classify the user task into exactly one of the supported task types. '
        'Return ONLY a task_type value from the enum.'
    ),
    'input_schema': {
        'type': 'object',
        'required': ['task_type'],
        'properties': {
            'task_type': {
                'type': 'string',
                'enum': ALL_TASK_TYPES,
                'description': 'The task type that best matches the request.',
            }
        },
    },
}

_SYSTEM_PROMPT = (
    'You are a task router. Given a description of a task, classify it into '
    'the most appropriate task_type using the classify_task tool. '
    'You MUST call the tool — do not reply with plain text.'
)


def classify_task(task_description: str) -> str:
    """
    Return a TaskType string for *task_description*.
    Falls back to TaskType.GENERIC on any error.
    """
    try:
        response = _client.messages.create(
            model='claude-haiku-4-5-20251001',  # cheap model for classification
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            tools=[_CLASSIFY_TOOL],
            tool_choice={'type': 'any'},
            messages=[{'role': 'user', 'content': task_description}],
        )
        for block in response.content:
            if block.type == 'tool_use' and block.name == 'classify_task':
                return block.input.get('task_type', TaskType.GENERIC)
    except Exception:
        pass  # log in production; fall through to default
    return TaskType.GENERIC
