"""
Pre-defined output JSON Schemas per task type.
The validator in agent-runtime uses these to check agent output before returning.
"""
from shared.constants import TaskType

# Each value is a JSON Schema dict that TaskResult.output must satisfy.
SKILL_OUTPUT_SCHEMAS: dict[str, dict] = {
    TaskType.SPREADSHEET_ANALYSIS: {
        'type': 'object',
        'required': ['summary', 'rows_processed'],
        'properties': {
            'summary': {'type': 'string'},
            'rows_processed': {'type': 'integer'},
            'insights': {'type': 'array', 'items': {'type': 'string'}},
        },
        'additionalProperties': True,
    },
    TaskType.DOCUMENT_GENERATION: {
        'type': 'object',
        'required': ['document_path'],
        'properties': {
            'document_path': {'type': 'string'},
            'page_count': {'type': 'integer'},
        },
        'additionalProperties': True,
    },
    TaskType.PDF_EXTRACTION: {
        'type': 'object',
        'required': ['text'],
        'properties': {
            'text': {'type': 'string'},
            'metadata': {'type': 'object'},
        },
        'additionalProperties': True,
    },
    TaskType.BASH_AUTOMATION: {
        'type': 'object',
        'required': ['exit_code', 'stdout'],
        'properties': {
            'exit_code': {'type': 'integer'},
            'stdout': {'type': 'string'},
            'stderr': {'type': 'string'},
        },
        'additionalProperties': True,
    },
    TaskType.GENERIC: {
        'type': 'object',
        'additionalProperties': True,
    },
}
