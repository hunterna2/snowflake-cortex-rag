"""
guardrails.py — Responsible AI guardrails for the compliance RAG assistant.

Intentional copy of python/guardrails.py for the self-contained Azure container
deployment — app.py imports from the same directory at runtime inside the container.
All checks are fast (no LLM calls) so they add negligible latency.
"""

from dataclasses import dataclass

BLOCKED_PHRASES = [
    "how to launder",
    "avoid detection",
    "evade reporting",
    "hide transaction",
    "structuring cash",
    "bypass kyc",
    "circumvent aml",
    "off the books",
]

OFF_TOPIC_SIGNALS = [
    "write me a poem",
    "tell me a joke",
    "who won the game",
    "stock price",
    "recipe for",
    "political opinion",
]

MAX_QUESTION_LENGTH = 2000


@dataclass
class GuardrailResult:
    blocked: bool
    reason: str = ""
    warning: str = ""   # non-blocking advisory shown to user


def check_question(question: str) -> GuardrailResult:
    q = question.strip().lower()

    if len(question) > MAX_QUESTION_LENGTH:
        return GuardrailResult(blocked=True, reason="Question exceeds maximum allowed length.")

    for phrase in BLOCKED_PHRASES:
        if phrase in q:
            return GuardrailResult(
                blocked=True,
                reason=f"This question cannot be answered as it may relate to prohibited activities.",
            )

    for signal in OFF_TOPIC_SIGNALS:
        if signal in q:
            return GuardrailResult(
                blocked=False,
                warning="This question appears off-topic for a compliance assistant. "
                        "Answers may not be relevant.",
            )

    return GuardrailResult(blocked=False)


DISCLAIMER = (
    "\n\n---\n**Disclaimer:** This is an AI-generated informational summary based on policy "
    "documents. It does not constitute legal or regulatory advice. Always consult your "
    "Compliance Officer or Legal team for official guidance."
)


def add_disclaimer(answer: str) -> str:
    return answer + DISCLAIMER
