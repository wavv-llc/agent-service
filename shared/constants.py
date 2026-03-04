"""
Shared constants used by both orchestrator and agent-runtime.
"""


# ---------------------------------------------------------------------------
# Task types (used for classification + skill routing)
# ---------------------------------------------------------------------------
class TaskType:
    SPREADSHEET_ANALYSIS = 'spreadsheet_analysis'
    DOCUMENT_GENERATION = 'document_generation'
    PDF_EXTRACTION = 'pdf_extraction'
    BASH_AUTOMATION = 'bash_automation'
    GENERIC = 'generic'


ALL_TASK_TYPES = [
    TaskType.SPREADSHEET_ANALYSIS,
    TaskType.DOCUMENT_GENERATION,
    TaskType.PDF_EXTRACTION,
    TaskType.BASH_AUTOMATION,
    TaskType.GENERIC,
]


# ---------------------------------------------------------------------------
# Tool names (used in allowed_tools lists)
# ---------------------------------------------------------------------------
class ToolName:
    BASH = 'bash'
    FILE_EXCEL = 'file_excel'
    FILE_WORD = 'file_word'
    FILE_PDF = 'file_pdf'
    MCP_CLIENT = 'mcp_client'


# ---------------------------------------------------------------------------
# Task queue settings
# ---------------------------------------------------------------------------
TASK_QUEUE_NAME = 'agent_tasks'
TASK_RESULT_TTL_SECS = 3600  # how long to keep results in store


# ---------------------------------------------------------------------------
# Task status values
# ---------------------------------------------------------------------------
class TaskStatus:
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'
