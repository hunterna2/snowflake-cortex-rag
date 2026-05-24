"""
azure_ui/app.py — Compliance RAG demo UI (Azure-hosted or local).

Toggle between Live Cortex (real Snowflake) and Demo Mode (pre-loaded answers)
directly from the sidebar — no restart required.
"""

import json
import os
import time
import uuid

import streamlit as st
from guardrails import add_disclaimer, check_question

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Compliance AI Assistant",
    page_icon="🏦",
    layout="wide",
)

# ── Snowpark session (cached; only created when Live mode is actually used) ────
@st.cache_resource(show_spinner="Connecting to Snowflake…")
def get_snowflake_session():
    from snowflake.snowpark import Session
    return Session.builder.configs({
        "account":   os.environ.get("SF_ACCOUNT", ""),
        "user":      os.environ.get("SF_USER", ""),
        "password":  os.environ.get("SF_PASSWORD", ""),
        "warehouse": os.environ.get("SF_WAREHOUSE", "COMPUTE_WH"),
        "database":  "COMPLIANCE_RAG",
        "schema":    "RAG",
    }).create()


def call_live_rag(question: str, category, top_k: int, model: str, session_id: str) -> dict:
    session = get_snowflake_session()
    rows = session.sql(
        "CALL ASK_COMPLIANCE(?, ?, ?, ?, ?, ?)",
        params=[question, category, top_k, model, session_id, None],
    ).collect()
    if not rows:
        return {"answer": "No response from Snowflake.", "citations": [], "guardrail_hit": False}
    return json.loads(rows[0][0])


# ── Demo responses ─────────────────────────────────────────────────────────────
DEMO_ANSWERS = {
    "sar": {
        "answer": (
            "### SAR Filing Requirements for Wire Transfers\n\n"
            "Under **31 CFR § 1020.320**, a Suspicious Activity Report must be filed when a "
            "transaction involves **$5,000 or more** and the institution suspects it involves "
            "funds from illegal activity, is designed to evade reporting requirements, or "
            "lacks a lawful purpose.\n\n"
            "For wire transfers specifically, the **FinCEN Travel Rule (31 CFR § 1010.410(f))** "
            "requires transmitting institutions to pass originator and beneficiary information "
            "for transfers of **$3,000 or more**.\n\n"
            "**Filing deadline:** Within 30 calendar days of initial detection. "
            "Maximum delay: 60 days if no suspect identified.\n\n"
            "SARs are filed electronically via the **FinCEN BSA E-Filing System**.\n\n"
            "---\n*Disclaimer: AI-generated summary. Consult your Compliance Officer for official guidance.*"
        ),
        "citations": [
            {"source": "BSA_AML_Policy_2024.pdf", "page": 12, "category": "BSA/AML"},
            {"source": "FinCEN_SAR_Guidance_2023.pdf", "page": 3, "category": "BSA/AML"},
        ],
    },
    "kyc": {
        "answer": (
            "### KYC Requirements for New Account Opening\n\n"
            "Under the **Customer Identification Program (CIP)** per 31 CFR § 1020.220, "
            "the bank must collect:\n\n"
            "- Full legal name\n"
            "- Date of birth\n"
            "- Residential street address (P.O. Box insufficient)\n"
            "- Government-issued ID number (SSN for U.S. persons; passport/TIN for non-U.S.)\n\n"
            "For **legal entities**, beneficial ownership information is required for any "
            "individual owning **25% or more**, plus one person with significant managerial control.\n\n"
            "**Enhanced Due Diligence (EDD)** is triggered for Politically Exposed Persons (PEPs), "
            "high-risk jurisdiction customers, and private banking clients with assets over $1M.\n\n"
            "---\n*Disclaimer: AI-generated summary. Consult your Compliance Officer for official guidance.*"
        ),
        "citations": [
            {"source": "KYC_CDD_Policy_2024.pdf", "page": 5, "category": "KYC"},
            {"source": "BSA_AML_Policy_2024.pdf", "page": 22, "category": "BSA/AML"},
        ],
    },
    "ofac": {
        "answer": (
            "### OFAC Screening Process\n\n"
            "All new customers and counterparties must be screened against the **OFAC Specially "
            "Designated Nationals (SDN) List** prior to account opening or transaction processing.\n\n"
            "**Ongoing screening occurs:**\n"
            "- At each significant transaction (wires, ACH batches over $25,000)\n"
            "- Within one business day of SDN List updates\n"
            "- Annually across the existing customer base\n\n"
            "**On a potential match:** The transaction is immediately blocked and escalated to "
            "the BSA Officer. A blocking or rejection report must be filed with OFAC within "
            "**10 business days**.\n\n"
            "---\n*Disclaimer: AI-generated summary. Consult your Compliance Officer for official guidance.*"
        ),
        "citations": [
            {"source": "OFAC_Screening_Procedures.pdf", "page": 2, "category": "OFAC"},
        ],
    },
    "retention": {
        "answer": (
            "### Wire Transfer Record Retention\n\n"
            "Under BSA recordkeeping rules, wire transfer records must be retained for "
            "**5 years from the execution date**.\n\n"
            "**Full retention schedule:**\n"
            "| Record Type | Retention Period |\n"
            "|-------------|------------------|\n"
            "| SAR + supporting docs | 5 years from filing |\n"
            "| CTR filings | 5 years from filing |\n"
            "| Wire transfer records | 5 years from execution |\n"
            "| CIP/KYC documentation | 5 years after account closure |\n"
            "| OFAC blocking reports | 5 years from report date |\n\n"
            "All records must be retrievable within a reasonable time and available to FinCEN, "
            "federal banking regulators, and law enforcement upon request.\n\n"
            "---\n*Disclaimer: AI-generated summary. Consult your Compliance Officer for official guidance.*"
        ),
        "citations": [
            {"source": "BSA_AML_Policy_2024.pdf", "page": 31, "category": "BSA/AML"},
        ],
    },
    "default": {
        "answer": (
            "### Response\n\n"
            "Based on the retrieved policy documents, this topic is covered under the bank's "
            "BSA/AML compliance framework. The relevant procedures require coordination with "
            "the Chief Compliance Officer and documentation in the bank's compliance management "
            "system.\n\n"
            "For specific thresholds and filing deadlines, refer to the current policy manual "
            "or contact the BSA Officer directly.\n\n"
            "---\n*Disclaimer: AI-generated summary. Consult your Compliance Officer for official guidance.*"
        ),
        "citations": [
            {"source": "BSA_AML_Policy_2024.pdf", "page": 8, "category": "BSA/AML"},
        ],
    },
}

def get_demo_response(question: str) -> dict:
    q = question.lower()
    if any(w in q for w in ["sar", "suspicious", "wire", "filing"]):
        data = DEMO_ANSWERS["sar"]
    elif any(w in q for w in ["kyc", "know your customer", "account opening", "identity", "cip"]):
        data = DEMO_ANSWERS["kyc"]
    elif any(w in q for w in ["ofac", "sanction", "sdn", "blocked"]):
        data = DEMO_ANSWERS["ofac"]
    elif any(w in q for w in ["retain", "retention", "record", "how long"]):
        data = DEMO_ANSWERS["retention"]
    else:
        data = DEMO_ANSWERS["default"]
    time.sleep(0.9)  # simulate realistic latency
    return {**data, "guardrail_hit": False}


# ── Session state ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏦 Compliance AI")

    # ── MODE TOGGLE (PIN-protected) ────────────────────────────────────────────
    st.markdown("### ⚡ Mode")

    ADMIN_PIN = os.environ.get("ADMIN_PIN", "")

    if "pin_unlocked" not in st.session_state:
        st.session_state.pin_unlocked = False

    if not st.session_state.pin_unlocked:
        pin_input = st.text_input("Admin PIN to enable Live mode", type="password",
                                  placeholder="Enter PIN…")
        if pin_input:
            if ADMIN_PIN and pin_input == ADMIN_PIN:
                st.session_state.pin_unlocked = True
                st.rerun()
            else:
                st.error("Incorrect PIN")

    if st.session_state.pin_unlocked:
        st.success("🔓 Admin unlocked")
        live_mode = st.toggle(
            "Live Cortex (Snowflake)",
            value=False,
            help="ON = calls real Snowflake Cortex Search + AI. OFF = pre-loaded demo answers.",
        )
        if st.button("🔒 Lock", use_container_width=True):
            st.session_state.pin_unlocked = False
            st.rerun()
    else:
        live_mode = False
        st.info("🟡 Demo Mode — pre-loaded answers")

    if live_mode:
        sf_ok = bool(os.environ.get("SF_ACCOUNT"))
        if sf_ok:
            st.success("🟢 Live — Snowflake Cortex")
        else:
            st.error("SF_ACCOUNT not set in environment.")
            live_mode = False

    st.divider()

    # ── Model / retrieval settings (shown in both modes) ──────────────────────
    st.markdown("### ⚙️ Settings")
    model = st.selectbox(
        "Model",
        ["mistral-large2", "llama3.1-70b", "snowflake-arctic"],
        disabled=not live_mode,
        help="Only applies in Live mode",
    )
    top_k = st.slider("Retrieved chunks (Top-K)", 3, 10, 5, disabled=not live_mode)

    category = None
    if live_mode:
        try:
            session = get_snowflake_session()
            cats = ["All"] + [
                r["DOC_CATEGORY"]
                for r in session.sql(
                    "SELECT DISTINCT DOC_CATEGORY FROM DOC_CHUNKS ORDER BY 1"
                ).collect()
                if r["DOC_CATEGORY"]
            ]
            sel = st.selectbox("Filter by category", cats)
            category = None if sel == "All" else sel
        except Exception:
            st.warning("Could not load categories.")

    st.divider()

    # ── Sample questions ───────────────────────────────────────────────────────
    st.markdown("### 💬 Sample questions")
    samples = [
        "What are the SAR filing thresholds?",
        "Describe KYC requirements for new account opening.",
        "What is our OFAC screening process?",
        "How long must we retain wire transfer records?",
    ]
    for q in samples:
        if st.button(q, use_container_width=True):
            st.session_state.prefill = q

    st.divider()
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

# ── Main header ────────────────────────────────────────────────────────────────
st.title("🏦 Banking Compliance Policy Assistant")

mode_badge = "🟢 **Live Cortex**" if live_mode else "🟡 **Demo Mode**"
st.caption(
    f"{mode_badge} · Retrieval-Augmented Generation over policy documents · "
    "Powered by Snowflake Cortex Search + AI"
)

# ── Architecture expander ──────────────────────────────────────────────────────
with st.expander("🏗️ Architecture", expanded=False):
    st.markdown("""
```
User Question
      │
      ▼
┌─────────────────────────────────────────────┐
│         Guardrail Layer  (Python)            │
│  Blocked-phrase check · length validation    │
└──────────────────┬──────────────────────────┘
                   │ safe questions only
                   ▼
┌─────────────────────────────────────────────┐
│    Cortex Search  (Snowflake)               │
│  Hybrid semantic + keyword retrieval         │
│  Top-K policy doc chunks + metadata filter  │
└──────────────────┬──────────────────────────┘
                   │ grounding context
                   ▼
┌─────────────────────────────────────────────┐
│  Cortex AI Complete  (mistral-large2)       │
│  Citation-enforced · no hallucination       │
└──────────────────┬──────────────────────────┘
                   ▼
        Answer + Source citations
                   │
                   ▼
        QUERY_LOG  (audit table)
```
**Ingestion:** PDF/DOCX/TXT → 1,000-char chunks (150 overlap) → `DOC_CHUNKS` → Cortex Search index
""")

# ── Chat history ───────────────────────────────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("citations"):
            with st.expander("📄 Sources"):
                for c in msg["citations"]:
                    st.markdown(
                        f"- **{c['source']}** — page {c.get('page','?')}  ·  *{c.get('category','')}*"
                    )

# ── Input ──────────────────────────────────────────────────────────────────────
prefill = st.session_state.pop("prefill", None)
prompt  = st.chat_input("Ask a compliance question…") or prefill

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        guard = check_question(prompt)
        if guard.blocked:
            answer    = f"⛔ {guard.reason}"
            citations = []
            blocked   = True
        else:
            if live_mode:
                with st.spinner("Querying Snowflake Cortex…"):
                    data = call_live_rag(
                        prompt, category, top_k, model, st.session_state.session_id
                    )
            else:
                with st.spinner("Searching policy documents…"):
                    data = get_demo_response(prompt)

            answer    = data.get("answer", "No answer returned.")
            citations = data.get("citations", [])
            blocked   = False
            if guard.warning:
                answer = f"⚠️ {guard.warning}\n\n{answer}"

        if blocked:
            st.warning(answer)
        else:
            st.markdown(answer)
            if citations:
                with st.expander("📄 Sources"):
                    for c in citations:
                        st.markdown(
                            f"- **{c['source']}** — page {c.get('page','?')}  ·  *{c.get('category','')}*"
                        )

    st.session_state.messages.append({
        "role": "assistant", "content": answer, "citations": citations,
    })
