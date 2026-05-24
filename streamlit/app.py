"""
app.py — Streamlit-in-Snowflake chat UI for the Compliance RAG assistant.

Deploy via: Snowsight → Projects → Streamlit → + Streamlit App
Paste this file content into the editor and point it at COMPLIANCE_RAG.RAG.
"""

import json
import uuid

import streamlit as st
from snowflake.snowpark.context import get_active_session
import snowflake.cortex as cortex

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Compliance Policy Assistant",
    page_icon="🏦",
    layout="wide",
)

# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

session = get_active_session()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")
    model = st.selectbox(
        "Model",
        ["mistral-large2", "llama3.1-70b", "snowflake-arctic"],
        index=0,
    )
    top_k = st.slider("Retrieved chunks (Top-K)", 3, 10, 5)

    categories = ["All"] + [
        r["DOC_CATEGORY"]
        for r in session.sql(
            "SELECT DISTINCT DOC_CATEGORY FROM COMPLIANCE_RAG.RAG.DOC_CHUNKS ORDER BY 1"
        ).collect()
        if r["DOC_CATEGORY"]
    ]
    category = st.selectbox("Filter by category", categories)
    category = None if category == "All" else category

    st.divider()
    if st.button("Clear conversation"):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

    st.divider()
    st.caption("📊 Usage today")
    usage = session.sql("""
        SELECT COUNT(*) AS QUERIES, AVG(LATENCY_MS) AS AVG_MS
        FROM COMPLIANCE_RAG.RAG.QUERY_LOG
        WHERE CREATED_AT >= CURRENT_DATE
    """).collect()
    if usage:
        st.metric("Queries", usage[0]["QUERIES"])
        if usage[0]["AVG_MS"]:
            st.metric("Avg latency", f"{usage[0]['AVG_MS']:.0f} ms")

# ── Main UI ────────────────────────────────────────────────────────────────────
st.title("🏦 Banking Compliance Policy Assistant")
st.caption("Ask questions about bank policies, BSA/AML rules, KYC requirements, and regulatory filings.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander("📄 Sources"):
                for c in msg["citations"]:
                    st.markdown(f"- **{c['source']}** — page {c.get('page', '?')} ({c.get('category', '')})")

# ── Chat input ─────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask a compliance question…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching policy documents…"):
            result = session.sql(
                "CALL COMPLIANCE_RAG.RAG.ASK_COMPLIANCE(?, ?, ?, ?, ?, ?)",
                params=[prompt, category, top_k, model,
                        st.session_state.session_id, None],
            ).collect()
            data = json.loads(result[0][0]) if result else {}

        answer    = data.get("answer", "No answer returned.")
        citations = data.get("citations", [])
        blocked   = data.get("guardrail_hit", False)

        if blocked:
            st.warning(answer)
        else:
            st.markdown(answer)
            if citations:
                with st.expander("📄 Sources"):
                    for c in citations:
                        st.markdown(
                            f"- **{c['source']}** — page {c.get('page','?')} ({c.get('category','')})"
                        )

    st.session_state.messages.append({
        "role":      "assistant",
        "content":   answer,
        "citations": citations,
    })
