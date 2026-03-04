"""
Task endpoints:
  POST /tasks          — submit a new task
  GET  /tasks/{id}     — poll task status / result
"""
from __future__ import annotations

import json
import logging
import os

import redis as redis_lib
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from orchestrator.classifier import classify_task
from orchestrator.dispatcher import RESULT_KEY_PREFIX, dispatch
from orchestrator.rbac import RBACError, validate_task
from orchestrator.sanitizer import SanitizationError, sanitize_context, sanitize_text
from shared.constants import TaskStatus
from shared.types import TaskRequest, TaskResult, TaskStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/tasks', tags=['tasks'])


# ---------------------------------------------------------------------------
# In-memory task store (replace with Redis / DB in production)
# ---------------------------------------------------------------------------
_task_store: dict[str, TaskStatusResponse] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SubmitTaskRequest(BaseModel):
    org_id: str
    auth_token: str
    task_description: str
    requested_tools: list[str] = []
    document_ids: list[str] = []
    input_context: dict = {}


class SubmitTaskResponse(BaseModel):
    task_id: str
    status: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    '', response_model=SubmitTaskResponse, status_code=status.HTTP_202_ACCEPTED
)
async def submit_task(body: SubmitTaskRequest) -> SubmitTaskResponse:
    """
    1. Sanitize inputs
    2. Classify task type (structured tool-use)
    3. RBAC validation
    4. Dispatch to agent-runtime queue
    """
    # 1. Sanitize
    try:
        sanitize_text(body.task_description, field_name='task_description')
        sanitize_context(body.input_context)
    except SanitizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 2. Classify
    task_type = classify_task(body.task_description)

    # 3. RBAC
    try:
        validate_task(body.org_id, task_type, body.requested_tools)
    except RBACError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 4. Build + dispatch task
    task = TaskRequest(
        task_type=task_type,
        org_id=body.org_id,
        auth_token=body.auth_token,
        allowed_tools=body.requested_tools,
        document_ids=body.document_ids,
        input_context={**body.input_context, 'task_description': body.task_description},
    )

    task_id = dispatch(task)

    # Track initial status
    _task_store[task_id] = TaskStatusResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        created_at=task.created_at,
    )

    return SubmitTaskResponse(task_id=task_id, status=TaskStatus.PENDING)


def _check_redis_result(task_id: str) -> TaskStatusResponse | None:
    """Check Redis for a completed result written by the agent-runtime."""
    url = os.getenv('TASK_QUEUE_URL')
    if not url:
        return None
    try:
        client = redis_lib.from_url(url, decode_responses=True)
        raw = client.get(f'{RESULT_KEY_PREFIX}{task_id}')
        if raw is None:
            return None
        data = json.loads(raw)
        result = TaskResult(**data)
        existing = _task_store.get(task_id)
        return TaskStatusResponse(
            task_id=result.task_id,
            status=result.status,
            result=result,
            created_at=existing.created_at if existing else None,
        )
    except Exception:
        logger.exception('Error reading result from Redis for task %s', task_id)
        return None


@router.get('/{task_id}', response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Poll for task status and result."""
    record = _task_store.get(task_id)

    # If already terminal in memory, return immediately
    if record is not None and record.status in (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
    ):
        return record

    # Check Redis for a result written by agent-runtime
    redis_record = _check_redis_result(task_id)
    if redis_record is not None:
        _task_store[task_id] = redis_record  # cache locally
        return redis_record

    if record is None:
        raise HTTPException(status_code=404, detail=f'Task {task_id!r} not found')
    return record


# ---------------------------------------------------------------------------
# Internal helper: called by agent-runtime (or a worker) to write back result
# ---------------------------------------------------------------------------


def record_task_result(result: TaskResult) -> None:
    """Store a completed TaskResult so the polling endpoint can return it."""
    existing = _task_store.get(result.task_id)
    _task_store[result.task_id] = TaskStatusResponse(
        task_id=result.task_id,
        status=result.status,
        result=result,
        created_at=existing.created_at if existing else None,
    )
