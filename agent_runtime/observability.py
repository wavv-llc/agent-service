"""
Observability — traces all LLM calls and tool invocations to Langfuse v2.

Usage
-----
    from agent_runtime.observability import get_tracer

    tracer = get_tracer(task_id="abc-123", org_id="org_demo")
    with tracer.span("planning") as span:
        tracer.llm_call(model="claude-sonnet-4-6", prompt=..., response=..., parent=span)
    tracer.tool_call(tool="bash", inputs={...}, output={...})
    tracer.finish(status="completed")

Environment variables
---------------------
    LANGFUSE_PUBLIC_KEY  — Langfuse public key
    LANGFUSE_SECRET_KEY  — Langfuse secret key
    LANGFUSE_HOST        — Langfuse host (default: https://us.cloud.langfuse.com)
"""
from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from typing import Any

logger = logging.getLogger(__name__)

_LANGFUSE_AVAILABLE = False
try:
    from langfuse import Langfuse  # type: ignore

    _LANGFUSE_AVAILABLE = True
except ImportError:
    pass  # Langfuse not installed — tracing is a no-op


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------


class AgentTracer:
    """
    Thin wrapper around a Langfuse Trace that exposes helper methods for
    the common agent lifecycle events.
    """

    def __init__(self, task_id: str, org_id: str, task_type: str) -> None:
        self.task_id = task_id
        self.org_id = org_id
        self.task_type = task_type
        self._trace = None
        self._client = None

        if _LANGFUSE_AVAILABLE:
            try:
                self._client = Langfuse(
                    public_key=os.environ['LANGFUSE_PUBLIC_KEY'],
                    secret_key=os.environ['LANGFUSE_SECRET_KEY'],
                    host=os.getenv('LANGFUSE_HOST', 'https://us.cloud.langfuse.com'),
                )
                self._trace = self._client.trace(
                    id=task_id,
                    name=f'agent-task:{task_type}',
                    metadata={'org_id': org_id},
                )
                logger.info(
                    'Langfuse tracing enabled | task_id=%s host=%s',
                    task_id,
                    os.getenv('LANGFUSE_HOST', 'https://us.cloud.langfuse.com'),
                )
            except Exception as exc:
                logger.warning('Langfuse init failed (tracing disabled): %s', exc)

    # ------------------------------------------------------------------

    def llm_call(
        self,
        model: str,
        prompt: Any,
        response: Any,
        name: str = 'llm-call',
        metadata: dict | None = None,
        parent: Any | None = None,
    ) -> None:
        """Record an LLM call as a Generation span.

        Pass *parent* (a span returned by the ``span()`` context manager) to
        nest the generation inside that span rather than at the trace level.
        """
        if self._trace is None:
            return
        try:
            node = parent if parent is not None else self._trace
            node.generation(
                name=name,
                model=model,
                input=prompt,
                output=response,
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.debug('Langfuse llm_call error: %s', exc)

    def tool_call(
        self,
        tool: str,
        inputs: dict,
        output: Any,
        error: str | None = None,
        parent: Any | None = None,
    ) -> None:
        """Record a tool invocation as a Span.

        Pass *parent* (a span returned by the ``span()`` context manager) to
        nest the span inside that span rather than at the trace level.
        """
        if self._trace is None:
            return
        try:
            node = parent if parent is not None else self._trace
            child = node.span(
                name=f'tool:{tool}',
                input=inputs,
                metadata={'error': error} if error else {},
                level='ERROR' if error else 'DEFAULT',
            )
            child.end(output=output)
        except Exception as exc:
            logger.debug('Langfuse tool_call error: %s', exc)

    @contextmanager
    def span(
        self, name: str, metadata: dict | None = None
    ) -> Generator[Any, None, None]:
        """Context manager that wraps a block in a named Langfuse span.

        Yields the underlying span object so callers can pass it as *parent*
        to ``llm_call()`` / ``tool_call()`` for proper nesting.
        Yields ``None`` when tracing is disabled.
        """
        if self._trace is None:
            yield None
            return
        span = None
        try:
            span = self._trace.span(name=name, metadata=metadata or {})
            yield span
        finally:
            if span:
                with suppress(Exception):
                    span.end()

    def finish(self, status: str = 'completed', output: Any = None) -> None:
        """Finalise the trace and flush to Langfuse."""
        if self._trace is None:
            return
        try:
            self._trace.update(output=output, metadata={'final_status': status})
        except Exception as exc:
            logger.warning('Langfuse trace.update error: %s', exc)
        finally:
            if self._client:
                try:
                    self._client.shutdown()  # blocks until queue is drained, safe on process exit
                except Exception as exc:
                    logger.warning('Langfuse shutdown error: %s', exc)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_tracer(task_id: str, org_id: str, task_type: str) -> AgentTracer:
    return AgentTracer(task_id=task_id, org_id=org_id, task_type=task_type)
