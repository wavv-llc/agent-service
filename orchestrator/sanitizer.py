"""
Input sanitization — defends against prompt injection before any LLM call.

Strategy
--------
1. Strip / reject known injection patterns (e.g. "ignore previous instructions").
2. Enforce hard length limits on free-text fields.
3. Raise SanitizationError so the orchestrator can return 400 immediately.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Patterns that signal a prompt-injection attempt
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r'ignore\s+(all\s+)?previous\s+instructions?', re.I),
    re.compile(r'you\s+are\s+now\s+(a|an)\s+\w+', re.I),
    re.compile(r'disregard\s+(all\s+)?prior\s+(context|instructions?)', re.I),
    re.compile(r'<\s*system\s*>', re.I),  # XML system-tag injection
    re.compile(r'\[INST\]|\[/INST\]'),  # Llama-style control tokens
    re.compile(r'###\s*(instruction|system)', re.I),
]

MAX_CONTEXT_FIELD_LENGTH = 4_096


class SanitizationError(ValueError):
    """Raised when input fails sanitization checks."""


def sanitize_text(text: str, field_name: str = 'input') -> str:
    """
    Check *text* for injection patterns and length limits.
    Returns the (unchanged) text on success, raises SanitizationError otherwise.
    """
    if len(text) > MAX_CONTEXT_FIELD_LENGTH:
        msg = (
            f"Field '{field_name}' exceeds maximum length "
            f'({len(text)} > {MAX_CONTEXT_FIELD_LENGTH})'
        )
        raise SanitizationError(msg)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            msg = f"Field '{field_name}' contains a disallowed pattern: {pattern.pattern!r}"
            raise SanitizationError(msg)
    return text


def sanitize_context(context: dict) -> dict:
    """
    Recursively sanitize all string values in an input_context dict.
    Non-string values (numbers, booleans, nested dicts/lists) are passed through.
    """
    sanitized: dict = {}
    for key, value in context.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_text(value, field_name=key)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_context(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_text(item, field_name=f'{key}[]')
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized
