"""
Executor — runs an AgentPlan step by step, dispatching tool calls to the
appropriate tool implementations.

For each step the executor:
  1. Calls the LLM with the step description + available tools.
  2. If the model requests a tool, dispatches to the tool function.
  3. Feeds the tool result back to the model.
  4. Repeats until the model emits a final text response or max iterations reached.
"""
from __future__ import annotations

import logging
from typing import Any

import anthropic

from agent_runtime.observability import AgentTracer
from agent_runtime.tools import bash, file_tools, mcp_client
from shared.constants import TaskType, ToolName
from shared.types import AgentPlan, PlanStep, SkillConfig, StepResult, TaskRequest

logger = logging.getLogger(__name__)
_client = anthropic.Anthropic()

MAX_TOOL_ROUNDS = 10  # safety limit per step


# ---------------------------------------------------------------------------
# Tool dispatch registry
# ---------------------------------------------------------------------------


def _dispatch_tool(tool_name: str, inputs: dict) -> Any:
    """Route a tool call to the correct implementation."""
    if tool_name == ToolName.BASH:
        return bash.run_command(**inputs)

    if tool_name in file_tools.TOOL_FUNCTIONS:
        return file_tools.TOOL_FUNCTIONS[tool_name](**inputs)

    if tool_name == ToolName.MCP_CLIENT:
        return mcp_client.call_tool(
            tool_name=inputs['tool_name'],
            inputs=inputs.get('inputs', {}),
        )

    msg = f'Unknown tool: {tool_name!r}'
    raise ValueError(msg)


def _build_tool_schemas(allowed_tools: list[str]) -> list[dict]:
    """Return the Anthropic tool schemas for the tools in *allowed_tools*."""
    schemas: list[dict] = []
    if ToolName.BASH in allowed_tools:
        schemas.append(bash.TOOL_SCHEMA)
    if any(t.startswith('file_') for t in allowed_tools):
        schemas.extend(file_tools.ALL_SCHEMAS)
    if ToolName.MCP_CLIENT in allowed_tools:
        schemas.append(mcp_client.MCP_PROXY_SCHEMA)
    return schemas


# ---------------------------------------------------------------------------
# Step executor
# ---------------------------------------------------------------------------


def _run_step(
    step: PlanStep,
    task: TaskRequest,
    skill: SkillConfig,
    tracer: AgentTracer,
    step_span: Any,
) -> StepResult:
    tool_schemas = _build_tool_schemas(skill.allowed_tools)
    messages: list[dict[str, Any]] = [
        {
            'role': 'user',
            'content': (
                f'Execute step {step.step_number}: {step.description}\n'
                f'Context: {task.input_context}'
            ),
        }
    ]

    final_output: Any = None
    last_bash_output: dict | None = None  # structured result for bash_automation

    for _ in range(MAX_TOOL_ROUNDS):
        response = _client.messages.create(
            model=skill.model,
            max_tokens=2048,
            tools=tool_schemas,
            messages=messages,
        )

        tracer.llm_call(
            model=skill.model,
            prompt=messages,
            response=[b.model_dump() for b in response.content],
            name=f'step-{step.step_number}',
            parent=step_span,
        )

        # Collect all tool calls in this turn
        tool_results = []
        has_tool_use = False

        for block in response.content:
            if block.type == 'tool_use':
                has_tool_use = True
                try:
                    output = _dispatch_tool(block.name, block.input)
                    if block.name == ToolName.BASH:
                        last_bash_output = output
                    tracer.tool_call(
                        tool=block.name,
                        inputs=block.input,
                        output=output,
                        parent=step_span,
                    )
                    tool_results.append(
                        {
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': str(output),
                        }
                    )
                except Exception as exc:
                    tracer.tool_call(
                        tool=block.name,
                        inputs=block.input,
                        output=None,
                        error=str(exc),
                        parent=step_span,
                    )
                    tool_results.append(
                        {
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': f'ERROR: {exc}',
                            'is_error': True,
                        }
                    )

            elif block.type == 'text':
                final_output = block.text

        if not has_tool_use:
            break

        # Feed tool results back
        messages.append({'role': 'assistant', 'content': response.content})
        messages.append({'role': 'user', 'content': tool_results})

    # For bash_automation, the schema requires {exit_code, stdout, stderr} — use
    # the structured tool output directly instead of the LLM's text summary.
    if skill.task_type == TaskType.BASH_AUTOMATION and last_bash_output is not None:
        final_output = last_bash_output

    return StepResult(
        step_number=step.step_number,
        success=True,
        output=final_output,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def execute(
    plan: AgentPlan,
    task: TaskRequest,
    skill: SkillConfig,
    tracer: AgentTracer,
) -> tuple[list[StepResult], Any]:
    """
    Execute all steps in *plan* sequentially.

    Returns (step_results, final_output) where final_output is the output
    of the last step.
    """
    results: list[StepResult] = []
    last_output: Any = None

    for step in plan.steps:
        with tracer.span(f'step-{step.step_number}') as step_span:
            result = _run_step(step, task, skill, tracer, step_span)
        results.append(result)
        if result.success:
            last_output = result.output
        else:
            logger.warning('Step %d failed: %s', step.step_number, result.error)

    return results, last_output
