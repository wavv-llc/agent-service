"""
Validator — checks agent output against the skill's output schema before returning.

Uses jsonschema for validation. Raises ValidationError on failure so the
lifecycle can surface the error cleanly rather than returning invalid output.
"""
from __future__ import annotations

from typing import Any

import jsonschema

from shared.schemas import SKILL_OUTPUT_SCHEMAS
from shared.types import SkillConfig


class OutputValidationError(ValueError):
    """Raised when agent output does not satisfy the skill's output schema."""


def validate_output(output: Any, skill: SkillConfig) -> None:
    """
    Validate *output* against the JSON Schema defined in *skill.output_schema*.
    Falls back to the pre-defined schema from SKILL_OUTPUT_SCHEMAS if the
    skill carries an empty output_schema.

    Raises OutputValidationError if validation fails.
    """
    schema = skill.output_schema or SKILL_OUTPUT_SCHEMAS.get(skill.task_type, {})

    if not schema:
        return  # no schema defined — skip validation

    try:
        jsonschema.validate(instance=output, schema=schema)
    except jsonschema.ValidationError as exc:
        msg = (
            f'Output for task type {skill.task_type!r} failed schema validation: '
            f'{exc.message} (path: {list(exc.absolute_path)})'
        )
        raise OutputValidationError(msg) from exc
