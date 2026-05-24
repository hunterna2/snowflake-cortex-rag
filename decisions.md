# DECISIONS.md
**Key Architecture Decisions**  
**Reusable Snowflake Cortex RAG Accelerator**  
**Last Updated**: May 24, 2026

## 1. Choice of Snowflake as the AI/Data Platform

**Decision**: We chose Snowflake (with Cortex Search + Cortex AI Functions + Snowpark) as the backend for the Live Mode RAG functionality.

**Rationale**:
- Compute and storage can be scaled independently (pay only for the compute you use).
- Cloud-agnostic platform (can run on Azure, AWS, or GCP).
- Native support for Snowpark Python, allowing us to run complex orchestration logic securely inside Snowflake.
- Built-in Cortex AI services (Search + Complete) provide high-quality retrieval and generation without leaving the platform.

**Status**: Accepted

## 2. Hybrid Architecture (Azure UI + Snowflake Backend)

**Decision**: Built a hybrid system — Streamlit UI hosted on Azure Container Apps, with Live Mode calling Snowflake.

**Rationale**:
- Azure Container Apps provides simple deployment, easy scaling to zero (cost savings), and a familiar Python/Streamlit development experience.
- Keeps the user-facing application lightweight and responsive while leveraging Snowflake’s strengths for secure, governed AI processing.
- Allows us to showcase a realistic enterprise pattern (UI layer + governed data/AI layer).

**Status**: Accepted

## 3. Two-Stage Guardrail Design (Defense-in-Depth)

**Decision**: Implemented two guardrails:
- First guardrail in the Azure Container App (fast keyword-based check).
- Second guardrail inside the Snowflake stored procedure `ASK_COMPLIANCE()`.

**Rationale**:
- First guardrail provides fast, low-latency filtering and reduces unnecessary load on Snowflake.
- Second guardrail adds deeper protection inside the most sensitive layer (Snowflake), catching sophisticated or bypassed attempts.
- Follows security best practices for regulated environments (defense-in-depth).

**Status**: Accepted

## 4. Live Mode vs Demo Mode Toggle

**Decision**: Added a PIN-protected toggle in the Streamlit UI to switch between Demo Mode (hardcoded answers) and Live Mode (real Snowflake Cortex).

**Rationale**:
- Allows zero-cost demonstrations and development without incurring Cortex Search / LLM costs.
- Enables easy showcasing of the full production capability when needed.
- Simple and effective cost-control mechanism.

**Status**: Accepted

## 5. Decision Not to Add a Third AI-Based Guardrail (for now)

**Decision**: Did not implement a third LLM-powered guardrail between the Azure and Snowflake layers.

**Rationale**:
- Would add extra latency and cost.
- Current two-stage keyword guardrails are sufficient for the demo/proof-of-concept stage.
- Can be added later if real-world usage shows sophisticated attacks getting through.

**Status**: Accepted (with note that it may be revisited in production)

---

**Overall Status**: All major decisions documented and accepted.

**Next Review**: After first internal demo / feedback from Data Innovation team.