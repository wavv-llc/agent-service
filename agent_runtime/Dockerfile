FROM python:3.12.0-slim

WORKDIR /app

COPY shared/ shared/
COPY agent_runtime/ agent_runtime/

RUN pip install --no-cache-dir \
    -r shared/requirements.txt \
    -r agent_runtime/requirements.txt

ENV PYTHONPATH=/app

# Default: wait for a task payload on stdin (override via TASK_PAYLOAD env var)
CMD ["python", "-m", "agent_runtime.main"]
