FROM python:3.12.0-slim

WORKDIR /app

COPY shared/ shared/
COPY orchestrator/ orchestrator/

RUN pip install --no-cache-dir \
    -r shared/requirements.txt \
    -r orchestrator/requirements.txt

ENV PYTHONPATH=/app
ENV ORCHESTRATOR_PORT=8000

CMD uvicorn orchestrator.main:app --host 0.0.0.0 --port ${ORCHESTRATOR_PORT}
