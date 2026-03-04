"""
Agent lifecycle — orchestrates the full receive → plan → execute → validate → return flow.

This is the main entry point called by main.py for each task.
"""
from __future__ import annotations

import logging

from agent_runtime import executor, planner, validator
from agent_runtime.observability import get_tracer
from shared.constants import TaskStatus, TaskType, ToolName
from shared.schemas import SKILL_OUTPUT_SCHEMAS
from shared.types import SkillConfig, TaskRequest, TaskResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill registry (task_type → SkillConfig)
# ---------------------------------------------------------------------------
# In production this would be loaded from a database or config file.

_SKILL_REGISTRY: dict[str, SkillConfig] = {
    TaskType.SPREADSHEET_ANALYSIS: SkillConfig(
        task_type=TaskType.SPREADSHEET_ANALYSIS,
        allowed_tools=[ToolName.FILE_EXCEL, ToolName.BASH],
        output_schema=SKILL_OUTPUT_SCHEMAS[TaskType.SPREADSHEET_ANALYSIS],
    ),
    TaskType.DOCUMENT_GENERATION: SkillConfig(
        task_type=TaskType.DOCUMENT_GENERATION,
        allowed_tools=[ToolName.FILE_WORD],
        output_schema=SKILL_OUTPUT_SCHEMAS[TaskType.DOCUMENT_GENERATION],
    ),
    TaskType.PDF_EXTRACTION: SkillConfig(
        task_type=TaskType.PDF_EXTRACTION,
        allowed_tools=[ToolName.FILE_PDF],
        output_schema=SKILL_OUTPUT_SCHEMAS[TaskType.PDF_EXTRACTION],
    ),
    TaskType.BASH_AUTOMATION: SkillConfig(
        task_type=TaskType.BASH_AUTOMATION,
        allowed_tools=[ToolName.BASH],
        output_schema=SKILL_OUTPUT_SCHEMAS[TaskType.BASH_AUTOMATION],
    ),
    TaskType.GENERIC: SkillConfig(
        task_type=TaskType.GENERIC,
        allowed_tools=[
            ToolName.BASH,
            ToolName.FILE_EXCEL,
            ToolName.FILE_WORD,
            ToolName.FILE_PDF,
            ToolName.MCP_CLIENT,
        ],
        output_schema=SKILL_OUTPUT_SCHEMAS[TaskType.GENERIC],
    ),
}


def _load_skill(task: TaskRequest) -> SkillConfig:
    """
    Load the SkillConfig for this task, then restrict its allowed_tools to
    the intersection of the skill's tools and the orchestrator's allowed_tools
    list (principle of least privilege).
    """
    skill = _SKILL_REGISTRY.get(task.task_type, _SKILL_REGISTRY[TaskType.GENERIC])

    # Respect the orchestrator's tool allowlist
    if task.allowed_tools:
        skill = skill.model_copy(
            update={
                'allowed_tools': [
                    t for t in skill.allowed_tools if t in task.allowed_tools
                ]
            }
        )
    return skill


# ---------------------------------------------------------------------------
# Main lifecycle
# ---------------------------------------------------------------------------


def run_task(task: TaskRequest) -> TaskResult:
    """
    Full agent lifecycle:
      1. Load skill config
      2. Plan (LLM → structured steps)
      3. Execute (step-by-step with tool calls)
      4. Validate output against skill schema
      5. Return TaskResult
    """
    tracer = get_tracer(
        task_id=task.task_id, org_id=task.org_id, task_type=task.task_type
    )

    try:
        # ---- 1. Load skill ------------------------------------------------
        skill = _load_skill(task)
        logger.info(
            'Task %s | type=%s | tools=%s',
            task.task_id,
            skill.task_type,
            skill.allowed_tools,
        )

        # ---- 2. Plan -------------------------------------------------------
        with tracer.span('planning') as planning_span:
            agent_plan = planner.plan(task, skill, tracer, planning_span)
        logger.info('Task %s | plan has %d steps', task.task_id, len(agent_plan.steps))

        # ---- 3. Execute ----------------------------------------------------
        with tracer.span('execution'):
            step_results, final_output = executor.execute(
                agent_plan, task, skill, tracer
            )

        # ---- 4. Validate ---------------------------------------------------
        with tracer.span('validation'):
            validator.validate_output(final_output, skill)

    except validator.OutputValidationError as exc:
        logger.exception('Task %s validation failed', task.task_id)
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.FAILED,
            error=f'Validation failed: {exc}',
        )
        tracer.finish(status=TaskStatus.FAILED)
        return result

    except Exception as exc:
        logger.exception('Task %s raised an unexpected error', task.task_id)
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.FAILED,
            error=str(exc),
        )
        tracer.finish(status=TaskStatus.FAILED)
        return result

    else:
        # ---- 5. Return success ---------------------------------------------
        result = TaskResult(
            task_id=task.task_id,
            status=TaskStatus.COMPLETED,
            output=final_output,
            plan=agent_plan,
            step_results=step_results,
        )
        tracer.finish(status=TaskStatus.COMPLETED, output=final_output)
        return result
