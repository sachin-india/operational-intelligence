"""SECOM Track B — Operational context graph Streamlit UI.

Yield risk scoring + governed lot-hold action + SPC alarm drill-down + audit.

Run (with Track B API on :8001):
    uv run streamlit run demos/secom/track_b/app.py --server.port 8504
"""

import requests
import pandas as pd
import plotly.express as px
import streamlit as st

from core.ontology.graph import GraphSession
from demos.secom.track_b.functions import PredictYieldRisk

API_BASE = "http://localhost:8001"

st.set_page_config(
    page_title="SECOM — Track B: Operational Graph",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ SECOM Semiconductor Yield — Track B")
st.caption(
    "Operational context graph: yield risk scoring + governed lot-hold action + audit trail."
)


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
        return requests.get(f"{API_BASE}/health", timeout=2).status_code == 200
    except Exception:
        return False


_risk_fn = PredictYieldRisk()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.header("Actor context")
actor = st.sidebar.text_input("Actor", value="eng_bob")
role = st.sidebar.selectbox("Role", ["engineer", "supervisor", "operator"])
reason = st.sidebar.text_area(
    "Reason for hold",
    value="Elevated SPC alarm count — yield risk review required.",
    height=80,
)

st.sidebar.markdown("---")
api_ok = api_available()
if api_ok:
    st.sidebar.success("API running on :8001")
else:
    st.sidebar.warning(
        "API not reachable.\n"
        "`uvicorn demos.secom.track_b.api:app --port 8001`"
    )

page = st.sidebar.radio(
    "Navigate",
    ["Risk Dashboard", "Score All Lots", "SPC Alarm Deep Dive", "Audit Log"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def fetch_lots_with_risk(outcome_filter: str, limit: int) -> pd.DataFrame:
    where = f"WHERE out.outcome_id = '{outcome_filter}'" if outcome_filter != "All" else ""
    rows = graph.run(
        f"""
        MATCH (lot:Lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
        {where}
        OPTIONAL MATCH (lot)-[r:TRIGGERED_ALARM]->(:SPCAlarm)
        WITH lot, out, max(abs(r.sigma_deviation)) AS max_sigma
        RETURN lot.lot_id         AS lot_id,
               lot.event_time     AS event_time,
               out.outcome_id     AS outcome,
               lot.n_spc_alarms   AS n_spc_alarms,
               lot.sensor_na_rate AS sensor_na_rate,
               coalesce(max_sigma, 0.0) AS max_sigma_dev,
               lot.risk_score     AS risk_score,
               lot.risk_level     AS risk_level,
               lot.lot_on_hold    AS lot_on_hold
        ORDER BY lot.n_spc_alarms DESC
        LIMIT {limit}
        """
    )
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def score_inline(row: dict) -> dict:
    return _risk_fn.compute({
        "n_spc_alarms": row.get("n_spc_alarms") or 0,
        "sensor_na_rate": row.get("sensor_na_rate") or 0.0,
        "max_sigma_dev": row.get("max_sigma_dev") or 0.0,
    })


color_map = {"high": "#d62728", "medium": "#ff7f0e", "low": "#2ca02c"}


# ---------------------------------------------------------------------------
# PAGE: Risk Dashboard
# ---------------------------------------------------------------------------

if page == "Risk Dashboard":
    st.header("Yield Risk Dashboard")

    col1, col2 = st.columns([2, 1])
    with col1:
        outcome_filter = st.selectbox("Outcome filter", ["All", "PASS", "FAIL"])
    with col2:
        display_limit = st.slider("Rows", 50, 500, 100, step=50)

    df = fetch_lots_with_risk(outcome_filter, display_limit)
    if df.empty:
        st.warning("No lots found.")
        st.stop()

    # Compute inline for lots without stored scores.
    if "risk_score" not in df.columns or df["risk_score"].isna().all():
        scores = df.apply(lambda r: score_inline(r.to_dict()), axis=1)
        df["risk_score"] = [s["risk_score"] for s in scores]
        df["risk_level"] = [s["risk_level"] for s in scores]

    df["risk_score"] = pd.to_numeric(df["risk_score"], errors="coerce").fillna(0.0)
    df["risk_level"] = df["risk_level"].fillna("low")
    df["lot_on_hold"] = df.get("lot_on_hold", False).fillna(False)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lots shown", len(df))
    c2.metric("High risk", int((df["risk_level"] == "high").sum()))
    c3.metric("Medium risk", int((df["risk_level"] == "medium").sum()))
    c4.metric("On hold", int(df["lot_on_hold"].sum()))

    col_a, col_b = st.columns(2)
    with col_a:
        level_counts = df["risk_level"].value_counts().reset_index()
        level_counts.columns = ["risk_level", "count"]
        fig = px.bar(level_counts, x="risk_level", y="count", color="risk_level",
                     color_discrete_map=color_map, title="Risk level distribution")
        st.plotly_chart(fig, use_container_width=True)
    with col_b:
        fig = px.scatter(df, x="n_spc_alarms", y="risk_score",
                         color="risk_level",
                         color_discrete_map=color_map,
                         hover_data=["lot_id", "outcome"],
                         title="SPC alarms vs risk score")
        st.plotly_chart(fig, use_container_width=True)

    # High-risk table with hold button
    st.subheader("High-risk lots")
    high_df = df[df["risk_level"] == "high"].copy()
    if high_df.empty:
        st.info("No high-risk lots in current view.")
    else:
        display_cols = ["lot_id", "outcome", "risk_score", "n_spc_alarms",
                        "max_sigma_dev", "sensor_na_rate", "event_time", "lot_on_hold"]
        st.dataframe(high_df[[c for c in display_cols if c in high_df.columns]].reset_index(drop=True),
                     use_container_width=True, hide_index=True)

        selected = st.selectbox("Select lot for hold action", high_df["lot_id"].tolist())
        already = bool(high_df[high_df["lot_id"] == selected]["lot_on_hold"].values[0])

        if already:
            st.info(f"{selected} is already on hold.")
        elif not api_ok:
            st.warning("Start the API to enable this action.")
        else:
            if st.button("Hold Lot", type="primary"):
                resp = requests.post(
                    f"{API_BASE}/actions/hold-lot",
                    json={"lot_id": selected, "actor": actor, "role": role, "reason": reason},
                )
                if resp.status_code == 200:
                    st.success(f"Lot {selected} placed on hold.")
                    st.json(resp.json())
                    fetch_lots_with_risk.clear()
                    st.rerun()
                else:
                    st.error(f"Action failed ({resp.status_code}): {resp.json().get('detail')}")


# ---------------------------------------------------------------------------
# PAGE: Score All Lots
# ---------------------------------------------------------------------------

elif page == "Score All Lots":
    st.header("Score All Lots")
    st.markdown(
        "Compute `predict_yield_risk` for every Lot and store "
        "`risk_score` + `risk_level` back as derived properties."
    )

    if st.button("Run scoring (all 1,567 lots)", type="primary"):
        bar = st.progress(0, text="Fetching lots…")
        rows = graph.run(
            """
            MATCH (lot:Lot)
            OPTIONAL MATCH (lot)-[r:TRIGGERED_ALARM]->(:SPCAlarm)
            WITH lot, max(abs(r.sigma_deviation)) AS max_sigma
            RETURN lot.lot_id         AS lot_id,
                   lot.n_spc_alarms   AS n_spc_alarms,
                   lot.sensor_na_rate AS sensor_na_rate,
                   coalesce(max_sigma, 0.0) AS max_sigma_dev
            ORDER BY lot.lot_id
            """
        )
        total = len(rows)
        bar.progress(10, text=f"Scoring {total:,} lots…")

        batch: list[dict] = []
        for i, row in enumerate(rows):
            score = _risk_fn.compute(row)
            batch.append({
                "lot_id": row["lot_id"],
                "risk_score": score["risk_score"],
                "risk_level": score["risk_level"],
            })

            if len(batch) == 200 or i == total - 1:
                graph.run(
                    """
                    UNWIND $batch AS b
                    MATCH (lot:Lot {lot_id: b.lot_id})
                    SET lot.risk_score = b.risk_score,
                        lot.risk_level = b.risk_level
                    """,
                    batch=batch,
                )
                batch = []
                bar.progress(10 + int(85 * (i + 1) / total), text=f"Stored {i+1:,}/{total:,}…")

        bar.progress(100, text="Done.")
        st.success(f"Scored and stored {total:,} Lot nodes.")
        fetch_lots_with_risk.clear()

        summary = graph.run(
            """
            MATCH (lot:Lot) WHERE lot.risk_level IS NOT NULL
            RETURN lot.risk_level AS risk_level, count(*) AS count ORDER BY risk_level
            """
        )
        st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# PAGE: SPC Alarm Deep Dive
# ---------------------------------------------------------------------------

elif page == "SPC Alarm Deep Dive":
    st.header("SPC Alarm Analysis")
    st.caption("Explore which alarms correlate with failing lots.")

    df = pd.DataFrame(graph.run(
        """
        MATCH (lot:Lot)-[r:TRIGGERED_ALARM]->(alm:SPCAlarm)
        MATCH (lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
        RETURN alm.alarm_id AS alarm_id,
               out.outcome_id AS outcome,
               r.sigma_deviation AS sigma_dev,
               lot.lot_id AS lot_id
        """
    ))

    if df.empty:
        st.warning("No alarm data found.")
    else:
        fail_alarm_rates = (
            df.groupby("alarm_id")
            .apply(lambda x: (x["outcome"] == "FAIL").mean(), include_groups=False)
            .rename("fail_rate")
            .reset_index()
            .sort_values("fail_rate", ascending=False)
            .head(20)
        )

        fig = px.bar(fail_alarm_rates, x="alarm_id", y="fail_rate",
                     title="Top 20 alarms by failure rate (fraction of triggering lots that failed)",
                     labels={"fail_rate": "Fraction of lots that failed"})
        fig.update_layout(xaxis_tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

        alarm_choice = st.selectbox("Inspect alarm", fail_alarm_rates["alarm_id"].tolist())
        alarm_df = df[df["alarm_id"] == alarm_choice]
        fig2 = px.histogram(alarm_df, x="sigma_dev", color="outcome",
                            color_discrete_map={"PASS": "#2ca02c", "FAIL": "#d62728"},
                            nbins=30,
                            title=f"Sigma deviation distribution for {alarm_choice}")
        st.plotly_chart(fig2, use_container_width=True)


# ---------------------------------------------------------------------------
# PAGE: Audit Log
# ---------------------------------------------------------------------------

elif page == "Audit Log":
    st.header("Audit Log")
    limit = st.slider("Entries", 10, 100, 20)

    if not api_ok:
        from sqlalchemy import text
        from core.governance.db import SessionLocal
        with SessionLocal() as db:
            rows = db.execute(
                text("SELECT id, action_name, actor, reason, outcome, error, created_at "
                     "FROM audit_log ORDER BY id DESC LIMIT :lim"),
                {"lim": limit},
            ).fetchall()
        audit_df = pd.DataFrame([dict(r._mapping) for r in rows])
    else:
        resp = requests.get(f"{API_BASE}/audit?limit={limit}")
        audit_df = pd.DataFrame(resp.json()) if resp.status_code == 200 else pd.DataFrame()

    if audit_df.empty:
        st.info("No audit entries yet.")
    else:
        st.dataframe(audit_df, use_container_width=True, hide_index=True)
