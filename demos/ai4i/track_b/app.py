"""AI4I Track B — Operational context graph Streamlit UI.

Extends Track A with:
  - Failure risk scores (derived properties, computed by PredictFailureRisk)
  - Governed maintenance action (calls FastAPI service)
  - Live audit log view

Run (with Track B API already running on :8000):
    uv run streamlit run demos/ai4i/track_b/app.py --server.port 8502
"""

import requests
import pandas as pd
import plotly.express as px
import streamlit as st

from core.ontology.graph import GraphSession
from demos.ai4i.track_b.functions import PredictFailureRisk

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="AI4I — Track B: Operational Graph",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ AI4I Predictive Maintenance — Track B")
st.caption(
    "Operational context graph: failure risk scoring + governed maintenance actions + audit trail."
)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@st.cache_resource
def get_graph() -> GraphSession:
    g = GraphSession.from_env()
    g.verify_connectivity()
    return g


try:
    graph = get_graph()
except Exception as exc:
    st.error(f"Cannot connect to Neo4j: {exc}")
    st.stop()


def api_available() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


_risk_fn = PredictFailureRisk()


# ---------------------------------------------------------------------------
# Sidebar — actor configuration (simulates real RBAC context)
# ---------------------------------------------------------------------------

st.sidebar.header("Actor context")
actor = st.sidebar.text_input("Actor (your name)", value="eng_alice")
role = st.sidebar.selectbox("Role", ["engineer", "supervisor", "operator"])
reason = st.sidebar.text_area(
    "Reason for action",
    value="High tool wear risk — preventive maintenance scheduled.",
    height=80,
)

st.sidebar.markdown("---")
api_ok = api_available()
if api_ok:
    st.sidebar.success("API service running")
else:
    st.sidebar.warning(
        "API not reachable. Start it with:\n"
        "`uvicorn demos.ai4i.track_b.api:app --port 8000`"
    )

page = st.sidebar.radio(
    "Navigate",
    ["Risk Dashboard", "Score All Runs", "Audit Log"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def fetch_runs_with_risk(machine_filter: str, limit: int) -> pd.DataFrame:
    where = f"WHERE r.machine_id = '{machine_filter}'" if machine_filter != "All" else ""
    rows = graph.run(
        f"""
        MATCH (r:ToolRun)
        {where}
        RETURN r.run_id AS run_id,
               r.machine_id AS machine_id,
               r.air_temp_k AS air_temp_k,
               r.process_temp_k AS process_temp_k,
               r.rotational_speed_rpm AS rotational_speed_rpm,
               r.torque_nm AS torque_nm,
               r.tool_wear_min AS tool_wear_min,
               r.machine_failure AS machine_failure,
               r.event_time AS event_time,
               r.risk_score AS risk_score,
               r.risk_level AS risk_level,
               r.maintenance_scheduled AS maintenance_scheduled
        ORDER BY r.tool_wear_min DESC
        LIMIT {limit}
        """
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def score_run_inline(row: dict) -> dict:
    return _risk_fn.compute({
        "air_temp_k": row["air_temp_k"],
        "process_temp_k": row["process_temp_k"],
        "rotational_speed_rpm": row["rotational_speed_rpm"],
        "torque_nm": row["torque_nm"],
        "tool_wear_min": row["tool_wear_min"],
        "machine_id": row["machine_id"],
    })


# ---------------------------------------------------------------------------
# PAGE: Risk Dashboard
# ---------------------------------------------------------------------------

if page == "Risk Dashboard":
    st.header("Failure Risk Dashboard")

    col1, col2 = st.columns([2, 1])
    with col1:
        machine_filter = st.selectbox("Machine", ["All", "MACHINE_L", "MACHINE_M", "MACHINE_H"])
    with col2:
        display_limit = st.slider("Rows to display", 50, 500, 100, step=50)

    df = fetch_runs_with_risk(machine_filter, display_limit)

    if df.empty:
        st.warning("No runs found.")
        st.stop()

    # Compute risk inline for rows that don't have stored scores yet.
    if "risk_score" not in df.columns or df["risk_score"].isna().all():
        scores = df.apply(lambda r: score_run_inline(r.to_dict()), axis=1)
        df["risk_score"] = [s["risk_score"] for s in scores]
        df["risk_level"] = [s["risk_level"] for s in scores]

    df["risk_score"] = pd.to_numeric(df["risk_score"], errors="coerce").fillna(0.0)
    df["risk_level"] = df["risk_level"].fillna("low")
    df["maintenance_scheduled"] = df.get("maintenance_scheduled", False).fillna(False)

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total runs shown", len(df))
    high = (df["risk_level"] == "high").sum()
    medium = (df["risk_level"] == "medium").sum()
    scheduled = df["maintenance_scheduled"].sum()
    c2.metric("High risk", int(high))
    c3.metric("Medium risk", int(medium))
    c4.metric("Maintenance scheduled", int(scheduled))

    # Risk distribution chart
    col_a, col_b = st.columns(2)
    with col_a:
        level_counts = df["risk_level"].value_counts().reset_index()
        level_counts.columns = ["risk_level", "count"]
        level_order = ["high", "medium", "low"]
        level_counts["risk_level"] = pd.Categorical(level_counts["risk_level"], categories=level_order, ordered=True)
        level_counts = level_counts.sort_values("risk_level")
        color_map = {"high": "#d62728", "medium": "#ff7f0e", "low": "#2ca02c"}
        fig = px.bar(
            level_counts, x="risk_level", y="count", color="risk_level",
            color_discrete_map=color_map,
            title="Risk level distribution",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        fig = px.scatter(
            df, x="tool_wear_min", y="risk_score",
            color="risk_level",
            color_discrete_map=color_map,
            hover_data=["run_id", "machine_id"],
            title="Tool wear vs risk score",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Run table with action button
    st.subheader("Runs — click to trigger maintenance")

    high_df = df[df["risk_level"] == "high"].copy()
    if high_df.empty:
        st.info("No high-risk runs in current view.")
    else:
        display_cols = ["run_id", "machine_id", "risk_score", "risk_level",
                        "tool_wear_min", "torque_nm", "event_time", "maintenance_scheduled"]
        st.dataframe(high_df[display_cols].reset_index(drop=True),
                     use_container_width=True, hide_index=True)

        selected_run = st.selectbox(
            "Select run for maintenance action",
            high_df["run_id"].tolist(),
        )
        already = bool(
            high_df[high_df["run_id"] == selected_run]["maintenance_scheduled"].values[0]
        )

        if already:
            st.info(f"{selected_run} already has maintenance scheduled.")
        else:
            if not api_ok:
                st.warning("Start the API service to enable this action.")
            else:
                if st.button("Trigger Maintenance", type="primary"):
                    resp = requests.post(
                        f"{API_BASE}/actions/trigger-maintenance",
                        json={
                            "run_id": selected_run,
                            "actor": actor,
                            "role": role,
                            "reason": reason,
                        },
                    )
                    if resp.status_code == 200:
                        st.success(f"Maintenance scheduled for {selected_run}.")
                        st.json(resp.json())
                        fetch_runs_with_risk.clear()
                        st.rerun()
                    else:
                        st.error(f"Action failed ({resp.status_code}): {resp.json().get('detail')}")


# ---------------------------------------------------------------------------
# PAGE: Score All Runs
# ---------------------------------------------------------------------------

elif page == "Score All Runs":
    st.header("Score All Runs")
    st.markdown(
        "Compute `predict_failure_risk` for every ToolRun and store the result "
        "back to each node as `risk_score` and `risk_level` derived properties."
    )

    if st.button("Run scoring (all 10,000 nodes)", type="primary"):
        bar = st.progress(0, text="Fetching runs…")
        rows = graph.run(
            """
            MATCH (r:ToolRun)
            RETURN r.run_id AS run_id,
                   r.air_temp_k AS air_temp_k,
                   r.process_temp_k AS process_temp_k,
                   r.rotational_speed_rpm AS rotational_speed_rpm,
                   r.torque_nm AS torque_nm,
                   r.tool_wear_min AS tool_wear_min,
                   r.machine_id AS machine_id
            ORDER BY r.run_id
            """
        )
        total = len(rows)
        bar.progress(10, text=f"Scoring {total:,} runs…")

        batch: list[dict] = []
        for i, row in enumerate(rows):
            score = _risk_fn.compute(row)
            batch.append({
                "run_id": row["run_id"],
                "risk_score": score["risk_score"],
                "risk_level": score["risk_level"],
            })

            if len(batch) == 500 or i == total - 1:
                graph.run(
                    """
                    UNWIND $batch AS b
                    MATCH (r:ToolRun {run_id: b.run_id})
                    SET r.risk_score = b.risk_score,
                        r.risk_level  = b.risk_level
                    """,
                    batch=batch,
                )
                batch = []
                bar.progress(10 + int(85 * (i + 1) / total), text=f"Stored {i + 1:,}/{total:,}…")

        bar.progress(100, text="Done.")
        st.success(f"Scored and stored {total:,} ToolRun nodes.")
        fetch_runs_with_risk.clear()

        # Summary of results.
        summary = graph.run(
            """
            MATCH (r:ToolRun)
            WHERE r.risk_level IS NOT NULL
            RETURN r.risk_level AS risk_level, count(*) AS count
            ORDER BY risk_level
            """
        )
        st.subheader("Risk distribution after scoring")
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# PAGE: Audit Log
# ---------------------------------------------------------------------------

elif page == "Audit Log":
    st.header("Audit Log")
    st.caption("Every governed action is recorded here — who, what, when, outcome.")

    limit = st.slider("Entries to show", 10, 100, 20)

    if not api_ok:
        st.warning("API not reachable — fetching audit log directly from Postgres.")
        from sqlalchemy import text
        from core.governance.db import SessionLocal
        with SessionLocal() as db:
            rows = db.execute(
                text(
                    "SELECT id, action_name, actor, reason, outcome, error, created_at "
                    "FROM audit_log ORDER BY id DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).fetchall()
        audit_df = pd.DataFrame([dict(r._mapping) for r in rows])
    else:
        resp = requests.get(f"{API_BASE}/audit?limit={limit}")
        audit_df = pd.DataFrame(resp.json()) if resp.status_code == 200 else pd.DataFrame()

    if audit_df.empty:
        st.info("No audit entries yet. Trigger a maintenance action first.")
    else:
        st.dataframe(audit_df, use_container_width=True, hide_index=True)

        if "outcome" in audit_df.columns:
            outcome_counts = audit_df["outcome"].value_counts().reset_index()
            outcome_counts.columns = ["outcome", "count"]
            fig = px.bar(outcome_counts, x="outcome", y="count",
                         color="outcome",
                         color_discrete_map={
                             "success": "#2ca02c", "aborted": "#ff7f0e", "failed": "#d62728"
                         },
                         title="Action outcomes")
            st.plotly_chart(fig, use_container_width=True)
