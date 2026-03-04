"""
Task dispatcher — enqueues a TaskRequest onto the task queue so an
agent-runtime container can pick it up.

Queue backend is abstracted behind a simple interface so it can be swapped
(Redis, SQS, Celery, etc.) without touching orchestrator logic.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod

import redis as redis_lib

from shared.types import TaskRequest

logger = logging.getLogger(__name__)

QUEUE_KEY = 'wavv:tasks'
RESULT_KEY_PREFIX = 'wavv:result:'


# ---------------------------------------------------------------------------
# Abstract queue interface
# ---------------------------------------------------------------------------


class TaskQueue(ABC):
    @abstractmethod
    def enqueue(self, task: TaskRequest) -> None:
        """Put *task* on the queue."""

    @abstractmethod
    def ack(self, task_id: str) -> None:
        """Acknowledge that a task has been consumed (for at-least-once queues)."""


# ---------------------------------------------------------------------------
# In-memory stub (local dev / unit tests only)
# ---------------------------------------------------------------------------


class InMemoryTaskQueue(TaskQueue):
    """Synchronous in-memory queue backed by a plain list."""

    def __init__(self) -> None:
        self._queue: list[dict] = []

    def enqueue(self, task: TaskRequest) -> None:
        payload = task.model_dump(mode='json')
        self._queue.append(payload)
        logger.info('Enqueued task %s (type=%s)', task.task_id, task.task_type)

    def ack(self, task_id: str) -> None:
        self._queue = [t for t in self._queue if t['task_id'] != task_id]


# ---------------------------------------------------------------------------
# Redis queue (used when TASK_QUEUE_URL is set)
# ---------------------------------------------------------------------------


class RedisTaskQueue(TaskQueue):
    """
    Redis-backed queue using a list (LPUSH / BRPOP).
    The agent-runtime does a blocking BRPOP to consume tasks.
    """

    def __init__(self, url: str) -> None:
        self._client = redis_lib.from_url(url, decode_responses=True)

    def enqueue(self, task: TaskRequest) -> None:
        payload = json.dumps(task.model_dump(mode='json'), default=str)
        self._client.lpush(QUEUE_KEY, payload)
        logger.info('Enqueued task %s (type=%s)', task.task_id, task.task_type)

    def ack(self, task_id: str) -> None:
        pass  # BRPOP is destructive; nothing to ack


# ---------------------------------------------------------------------------
# Module-level singleton — picks backend from TASK_QUEUE_URL
# ---------------------------------------------------------------------------

_queue_url = os.getenv('TASK_QUEUE_URL')
_queue: TaskQueue = RedisTaskQueue(_queue_url) if _queue_url else InMemoryTaskQueue()


def get_queue() -> TaskQueue:
    return _queue


def dispatch(task: TaskRequest) -> str:
    """Enqueue *task* and return its task_id so the caller can poll for results."""
    _queue.enqueue(task)
    return task.task_id
