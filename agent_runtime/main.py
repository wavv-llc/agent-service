"""
Agent Runtime — container entry point.

In production this process:
  1. Connects to the task queue (env: TASK_QUEUE_URL).
  2. Blocks waiting for a single TaskRequest.
  3. Runs the full agent lifecycle.
  4. Posts the TaskResult back to the orchestrator result store.
  5. Exits (the container is ephemeral — one task per container).

For local development / testing the task can be provided via stdin JSON
or the TASK_PAYLOAD environment variable.
"""
from __future__ import annotations

import json
import logging
import os
import sys

import redis as redis_lib

from agent_runtime.lifecycle import run_task
from shared.types import TaskRequest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s — %(message)s',
)
logger = logging.getLogger(__name__)

QUEUE_KEY = 'wavv:tasks'
RESULT_KEY_PREFIX = 'wavv:result:'
RESULT_TTL = 86_400  # seconds (24 h)


# ---------------------------------------------------------------------------
# Queue consumer
# ---------------------------------------------------------------------------


def _consume_from_queue() -> TaskRequest:
    """
    Pull one task from the queue and return it as a TaskRequest.

    Priority:
      1. TASK_QUEUE_URL env var → Redis BRPOP (blocks up to 30 s)
      2. TASK_PAYLOAD env var   → JSON string (local testing)
      3. stdin                  → JSON string (pipe / redirect)
    """
    queue_url = os.getenv('TASK_QUEUE_URL')
    if queue_url:
        client = redis_lib.from_url(queue_url, decode_responses=True)
        logger.info('Waiting for task on Redis queue (key=%s)…', QUEUE_KEY)
        result = client.brpop(QUEUE_KEY, timeout=30)
        if result is None:
            logger.info('No task available after 30 s timeout. Exiting.')
            sys.exit(0)
        _, payload = result
        return TaskRequest(**json.loads(payload))

    payload_env = os.getenv('TASK_PAYLOAD')
    if payload_env:
        return TaskRequest(**json.loads(payload_env))

    logger.info('Reading task payload from stdin…')
    raw = sys.stdin.read().strip()
    if not raw:
        logger.info(
            'No task payload provided (stdin empty, TASK_PAYLOAD unset). Exiting.'
        )
        sys.exit(0)
    return TaskRequest(**json.loads(raw))


# ---------------------------------------------------------------------------
# Result writer
# ---------------------------------------------------------------------------


def _post_result(result: dict, task_id: str) -> None:
    """
    Send the TaskResult back to the result store.

    If TASK_QUEUE_URL is set, writes to Redis (key: wavv:result:<task_id>)
    so the orchestrator's GET /tasks/{id} polling endpoint can read it.
    Falls back to stdout for local development.
    """
    queue_url = os.getenv('TASK_QUEUE_URL')
    if queue_url:
        client = redis_lib.from_url(queue_url, decode_responses=True)
        key = f'{RESULT_KEY_PREFIX}{task_id}'
        client.set(key, json.dumps(result, default=str), ex=RESULT_TTL)
        logger.info('Result stored in Redis | key=%s', key)
        return

    sys.stdout.write(json.dumps(result, default=str) + '\n')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    task = _consume_from_queue()
    logger.info(
        'Agent runtime starting | task_id=%s type=%s', task.task_id, task.task_type
    )

    result = run_task(task)

    _post_result(result.model_dump(mode='json'), task.task_id)
    logger.info(
        'Agent runtime done | task_id=%s status=%s', task.task_id, result.status
    )


if __name__ == '__main__':
    main()
