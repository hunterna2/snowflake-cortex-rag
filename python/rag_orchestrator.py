"""
rag_orchestrator.py — Core RAG pipeline for local development and testing.

This mirrors the logic in 03_stored_procs.sql but runs outside Snowflake,
useful for rapid iteration, CI testing, and the Azure-hosted Streamlit UI.

Environment variables (or pass a connection dict):
    SF_ACCOUNT, SF_USER, SF_PASSWORD, SF_WAREHOUSE, SF_DATABASE, SF_SCHEMA
"""

import json
import os
import time
import uuid
from typing import Optional

from guardrails import GuardrailResult, add_disclaimer, check_question

DEFAULT_MODEL = "mistral-large2"
DEFAULT_TOP_K = 5

SYSTEM_PROMPT = """You are a banking compliance assistant. Answer questions about
bank policies, regulatory requirements, and compliance procedures using ONLY the
provided source excerpts. If the answer is not found in the sources, say so clearly.
Always cite the source document name and page number."""


def _get_session(conn_params: Optional[dict] = None):
    from snowflake.snowpark import Session

    params = conn_params or {
        "account":   os.environ["SF_ACCOUNT"],
        "user":      os.environ["SF_USER"],
        "password":  os.environ["SF_PASSWORD"],
        "warehouse": os.environ.get("SF_WAREHOUSE", "RAG_WH"),
        "database":  os.environ.get("SF_DATABASE", "COMPLIANCE_RAG"),
        "schema":    os.environ.get("SF_SCHEMA", "RAG"),
    }
    return Session.builder.configs(params).create()


def retrieve_chunks(session, question: str, top_k: int, category: Optional[str]) -> list[dict]:
    payload: dict = {
        "query":   question,
        "columns": ["CHUNK_TEXT", "SOURCE_FILE", "DOC_CATEGORY", "PAGE_NUM"],
        "limit":   top_k,
    }
    if category:
        payload["filter"] = {"@eq": {"DOC_CATEGORY": category}}

    rows = session.sql(
        "SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW("
        "  'COMPLIANCE_RAG.RAG.COMPLIANCE_SEARCH', ?) ::VARIANT AS R",
        params=[json.dumps(payload)],
    ).collect()

    return json.loads(rows[0]["R"]).get("results", [])


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"[Source: {c['SOURCE_FILE']}, Page {c.get('PAGE_NUM', '?')}]\n{c['CHUNK_TEXT']}"
        for c in chunks
    )
    return f"Source excerpts:\n{context}\n\nQuestion: {question}\n\nAnswer:"


def ask(
    question: str,
    category: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
    model: str = DEFAULT_MODEL,
    session_id: Optional[str] = None,
    user_email: Optional[str] = None,
    conn_params: Optional[dict] = None,
) -> dict:
    """
    Main entry point. Returns:
        {
            "answer":        str,
            "citations":     list[dict],
            "guardrail_hit": bool,
            "latency_ms":    int,
        }
    """
    import snowflake.cortex as cortex

    t0 = time.time()
    session_id = session_id or str(uuid.uuid4())

    # ── Guardrails ────────────────────────────────────────────────────────────
    guard: GuardrailResult = check_question(question)
    if guard.blocked:
        return {
            "answer":        f"I cannot help with that request. {guard.reason}",
            "citations":     [],
            "guardrail_hit": True,
            "latency_ms":    int((time.time() - t0) * 1000),
        }

    session = _get_session(conn_params)

    # ── Retrieval ─────────────────────────────────────────────────────────────
    chunks = retrieve_chunks(session, question, top_k, category)
    if not chunks:
        session.close()
        return {
            "answer":        "No relevant documents were found for your question.",
            "citations":     [],
            "guardrail_hit": False,
            "latency_ms":    int((time.time() - t0) * 1000),
        }

    # ── Generation ────────────────────────────────────────────────────────────
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": build_user_prompt(question, chunks)},
    ]
    answer_raw = cortex.Complete(model, messages, session=session)
    answer = add_disclaimer(answer_raw)
    if guard.warning:
        answer = f"⚠️ {guard.warning}\n\n{answer}"

    # ── Citations ─────────────────────────────────────────────────────────────
    seen: set = set()
    citations = []
    for c in chunks:
        key = (c["SOURCE_FILE"], c.get("PAGE_NUM"))
        if key not in seen:
            seen.add(key)
            citations.append({
                "source":   c["SOURCE_FILE"],
                "page":     c.get("PAGE_NUM"),
                "category": c.get("DOC_CATEGORY"),
            })

    # ── Audit log ─────────────────────────────────────────────────────────────
    latency_ms = int((time.time() - t0) * 1000)
    try:
        session.sql(
            """INSERT INTO QUERY_LOG
               (SESSION_ID,USER_EMAIL,QUESTION,ANSWER,CITATIONS,MODEL_USED,LATENCY_MS)
               SELECT ?,?,?,?,PARSE_JSON(?),?,?""",
            params=[session_id, user_email, question, answer,
                    json.dumps(citations), model, latency_ms],
        ).collect()
    except Exception:
        pass  # never let logging break the user experience

    session.close()
    return {
        "answer":        answer,
        "citations":     citations,
        "guardrail_hit": False,
        "latency_ms":    latency_ms,
    }


# ── CLI smoke test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    question = " ".join(sys.argv[1:]) or "What are the SAR filing thresholds?"
    result = ask(question)
    print("\nAnswer:\n", result["answer"])
    print("\nCitations:")
    for c in result["citations"]:
        print(f"  - {c['source']}  (page {c['page']}, {c['category']})")
    print(f"\nLatency: {result['latency_ms']} ms")
