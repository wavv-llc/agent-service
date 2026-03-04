"""
Orchestrator — FastAPI entry point.

Responsibilities (does NOT run agent logic):
  - Input sanitization
  - Task classification (structured tool-use)
  - RBAC validation
  - Dispatch to agent-runtime via task queue
  - Task status polling endpoint
"""
from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orchestrator.routes.tasks import router as tasks_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title='Wavv Orchestrator',
    description='Lightweight orchestrator — classifies, validates, and dispatches tasks to agent-runtime.',
    version='0.1.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # tighten in production
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(tasks_router)


@app.get('/health')
async def health() -> dict:
    return {'status': 'ok'}


if __name__ == '__main__':
    port = int(os.getenv('ORCHESTRATOR_PORT', '8000'))
    uvicorn.run('orchestrator.main:app', host='0.0.0.0', port=port)
