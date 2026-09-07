"""
Prompt utilities and a light safety filter.
- build_prompt: composes system memory, system instructions, and user prompt into a single string.
- safety_check: blocks obviously sensitive prompts (PII / credentials) to help avoid accidental leakage to model servers.
"""

import re
from typing import Optional

# Very small set of naive detections for PII or credential patterns
_PIi_PATTERNS = [
    re.compile(r"\b(ssn|social security number)\b", re.IGNORECASE),
    re.compile(r"\b(credit card|cc number|card number)\b", re.IGNORECASE),
    re.compile(r"\b(password|pwd|passphrase)\b", re.IGNORECASE),
    re.compile(r"\b(secret|api[_-]?key|access[_-]?token)\b", re.IGNORECASE),
    # basic email/phone detection to warn if user is sending real PII
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\+?\d{7,15}"),
]


def build_prompt(
    user_prompt: str,
    memory: Optional[str] = None,
    system_instructions: Optional[str] = None,
    max_length_chars: int = 4000,
) -> str:
    """
    Compose a prompt for the model:
      - optional system_instructions (high-level assistant behavior)
      - optional memory (recent persistent memory)
      - user_prompt

    This returns a single string and will truncate memory if the prompt would exceed max_length_chars.
    """
    parts = []
    if system_instructions:
        parts.append(f"SYSTEM:\n{system_instructions.strip()}\n")
    if memory:
        parts.append(f"MEMORY:\n{memory.strip()}\n")
    parts.append(f"USER:\n{user_prompt.strip()}\nASSISTANT:")

    prompt = "\n\n".join(parts)

    if len(prompt) > max_length_chars:
        # Truncate memory first (preserve system + user)
        if memory:
            allowed_for_memory = max_length_chars - (len(prompt) - len(memory))
            if allowed_for_memory > 0:
                truncated_memory = memory.strip()[:allowed_for_memory]
                parts[1] = f"MEMORY:\n{truncated_memory}\n"
                prompt = "\n\n".join(parts)
            else:
                # remove memory entirely
                parts.pop(1)
                prompt = "\n\n".join(parts)
        # As a last resort, truncate the prompt itself
        if len(prompt) > max_length_chars:
            prompt = prompt[:max_length_chars]
    return prompt


def safety_check(prompt: str):
    """
    Naive safety filter that raises ValueError if obvious sensitive content is present.
    This is NOT a full compliance solution — it's a best-effort guardrail.
    """
    for patt in _PIi_PATTERNS:
        if patt.search(prompt):
            raise ValueError("Prompt appears to contain sensitive information (PII or credentials); remove it before sending to the model.")
    return True