"""SECOM Track A — Streamlit graph explorer.

Passive knowledge graph: browse the SECOM semiconductor manufacturing graph.
Lot → YieldOutcome, Lot → SPCAlarm relationships, read-only exploration.

Run:
    uv run streamlit run demos/secom/track_a/app.py --server.port 8503
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from core.ontology.graph import GraphSession

st.set_page_config(
    page_title="SECOM — Track A: Knowledge Graph",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 SECOM Semiconductor Yield — Track A")
st.caption(
    "Passive knowledge graph: browse Lot → YieldOutcome → SPCAlarm relationships. "
    "No actions, no governance — read-only exploration."
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
    st.info("Start Neo4j with: `docker compose -f infra/docker-compose.yml up -d`")
    st.stop()


page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Lots", "SPC Alarms", "Yield Analysis", "Cypher Explorer"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Graph schema**")
st.sidebar.markdown(
    """
    ```
    (Lot)
      -[:HAS_OUTCOME]->
    (YieldOutcome)

    (Lot)
      -[:TRIGGERED_ALARM]->
    (SPCAlarm)
    ```
    """
)


@st.cache_data(ttl=60)
def query(_key: str, cypher: str, **params) -> pd.DataFrame:
    rows = graph.run(cypher, **params)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def q(cypher: str, **params) -> pd.DataFrame:
    return query(id(graph), cypher, **params)


# ---------------------------------------------------------------------------
# PAGE: Overview
# ---------------------------------------------------------------------------

if page == "Overview":
    st.header("Graph Overview")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Lot nodes", q("MATCH (n:Lot) RETURN count(n) AS c")["c"].iloc[0])
    c2.metric("YieldOutcome nodes", q("MATCH (n:YieldOutcome) RETURN count(n) AS c")["c"].iloc[0])
    c3.metric("SPCAlarm nodes", q("MATCH (n:SPCAlarm) RETURN count(n) AS c")["c"].iloc[0])
    c4.metric("HAS_OUTCOME rels", q("MATCH ()-[r:HAS_OUTCOME]->() RETURN count(r) AS c")["c"].iloc[0])
    c5.metric("TRIGGERED_ALARM rels", q("MATCH ()-[r:TRIGGERED_ALARM]->() RETURN count(r) AS c")["c"].iloc[0])

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Pass / Fail split")
        df = q(
            """
            MATCH (lot:Lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
            RETURN out.outcome_id AS outcome, count(lot) AS count
            """
        )
        if not df.empty:
            fig = px.pie(df, names="outcome", values="count",
                         color="outcome",
                         color_discrete_map={"PASS": "#2ca02c", "FAIL": "#d62728"},
                         title="Yield outcome distribution")
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("SPC alarms per lot distribution")
        df = q("MATCH (lot:Lot) RETURN lot.n_spc_alarms AS n_alarms")
        if not df.empty:
            fig = px.histogram(df, x="n_alarms", nbins=30,
                               title="How many 3σ alarms does a typical lot trigger?",
                               labels={"n_alarms": "Number of SPC alarms"})
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 10 most frequently alarming sensors")
    df = q(
        """
        MATCH (lot:Lot)-[:TRIGGERED_ALARM]->(alm:SPCAlarm)
        RETURN alm.alarm_id AS alarm_id, alm.feature_name AS feature,
               count(lot) AS triggered_by_n_lots
        ORDER BY triggered_by_n_lots DESC
        LIMIT 10
        """
    )
    if not df.empty:
        fig = px.bar(df, x="alarm_id", y="triggered_by_n_lots",
                     title="Which sensors alarm most often?",
                     labels={"alarm_id": "Sensor", "triggered_by_n_lots": "Lots triggered"})
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# PAGE: Lots
# ---------------------------------------------------------------------------

elif page == "Lots":
    st.header("Lots")

    col1, col2 = st.columns(2)
    with col1:
        outcome_filter = st.selectbox("Yield outcome", ["All", "PASS", "FAIL"])
    with col2:
        min_alarms = st.slider("Min SPC alarms", 0, 20, 0)

    where_parts = []
    if outcome_filter != "All":
        where_parts.append(f"out.outcome_id = '{outcome_filter}'")
    if min_alarms > 0:
        where_parts.append(f"lot.n_spc_alarms >= {min_alarms}")
    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    df = q(
        f"""
        MATCH (lot:Lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
        {where}
        RETURN lot.lot_id AS lot_id, lot.event_time AS event_time,
               out.outcome_id AS outcome, lot.sensor_na_rate AS sensor_na_rate,
               lot.n_spc_alarms AS n_spc_alarms
        ORDER BY lot.n_spc_alarms DESC
        LIMIT 200
        """
    )

    st.caption("Showing up to 200 rows ordered by alarm count.")
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        selected_lot = st.selectbox("Drill into lot", df["lot_id"].tolist())
        alarms = q(
            """
            MATCH (lot:Lot {lot_id: $lid})-[r:TRIGGERED_ALARM]->(alm:SPCAlarm)
            RETURN alm.alarm_id AS alarm_id, alm.feature_name AS feature,
                   r.sensor_value AS value, r.sigma_deviation AS sigma_dev,
                   alm.upper_control_limit AS ucl, alm.lower_control_limit AS lcl
            ORDER BY abs(r.sigma_deviation) DESC
            """,
            lid=selected_lot,
        )
        if alarms.empty:
            st.info(f"{selected_lot} triggered no SPC alarms.")
        else:
            st.subheader(f"SPC alarms for {selected_lot} ({len(alarms)} sensors)")
            st.dataframe(alarms, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# PAGE: SPC Alarms
# ---------------------------------------------------------------------------

elif page == "SPC Alarms":
    st.header("SPC Alarm Features")
    st.caption(
        "Each node represents a sensor feature whose 3σ control limits were crossed "
        "at least once across 1,567 lots."
    )

    df = q(
        """
        MATCH (alm:SPCAlarm)
        RETURN alm.alarm_id AS alarm_id, alm.feature_name AS feature,
               alm.population_mean AS mean, alm.population_std AS std,
               alm.upper_control_limit AS ucl, alm.lower_control_limit AS lcl,
               alm.total_alarm_count AS total_alarms
        ORDER BY total_alarms DESC
        """
    )

    col1, col2 = st.columns([3, 1])
    with col2:
        top_n = st.slider("Show top N", 10, len(df), 50)
    with col1:
        st.write(f"{len(df)} SPC alarm features total. Sorted by alarm frequency.")

    st.dataframe(df.head(top_n), use_container_width=True, hide_index=True)

    st.subheader("Alarm count distribution across features")
    fig = px.histogram(df, x="total_alarms", nbins=40,
                       title="How many lots does each alarming sensor affect?",
                       labels={"total_alarms": "Number of lots triggering this alarm"})
    st.plotly_chart(fig, use_container_width=True)

    selected_alarm = st.selectbox("Drill into sensor", df["alarm_id"].tolist())
    s = df[df["alarm_id"] == selected_alarm].iloc[0]
    st.markdown(
        f"**{s['alarm_id']}** — mean={s['mean']:.4f}, std={s['std']:.4f}, "
        f"UCL={s['ucl']:.4f}, LCL={s['lcl']:.4f}, alarms={int(s['total_alarms'])}"
    )

    lots_with_alarm = q(
        """
        MATCH (lot:Lot)-[r:TRIGGERED_ALARM]->(alm:SPCAlarm {alarm_id: $aid})
        MATCH (lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
        RETURN lot.lot_id AS lot_id, out.outcome_id AS outcome,
               r.sensor_value AS value, r.sigma_deviation AS sigma_dev
        ORDER BY abs(r.sigma_deviation) DESC
        LIMIT 50
        """,
        aid=selected_alarm,
    )
    if not lots_with_alarm.empty:
        fig = px.scatter(
            lots_with_alarm, x="sigma_dev", y="value",
            color="outcome",
            color_discrete_map={"PASS": "#2ca02c", "FAIL": "#d62728"},
            hover_data=["lot_id"],
            title=f"Alarm readings for {selected_alarm} — pass vs fail",
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# PAGE: Yield Analysis
# ---------------------------------------------------------------------------

elif page == "Yield Analysis":
    st.header("Yield Analysis")

    st.subheader("Do more SPC alarms predict failure?")
    df = q(
        """
        MATCH (lot:Lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
        RETURN lot.n_spc_alarms AS n_alarms, out.outcome_id AS outcome,
               lot.sensor_na_rate AS na_rate
        """
    )
    if not df.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.box(df, x="outcome", y="n_alarms",
                         color="outcome",
                         color_discrete_map={"PASS": "#2ca02c", "FAIL": "#d62728"},
                         title="SPC alarms: PASS vs FAIL lots")
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            fig = px.box(df, x="outcome", y="na_rate",
                         color="outcome",
                         color_discrete_map={"PASS": "#2ca02c", "FAIL": "#d62728"},
                         title="Sensor missing rate: PASS vs FAIL lots")
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Which alarms are more common in failing lots?")
    df = q(
        """
        MATCH (lot:Lot)-[:TRIGGERED_ALARM]->(alm:SPCAlarm)
        MATCH (lot)-[:HAS_OUTCOME]->(out:YieldOutcome)
        WHERE out.outcome_id = 'FAIL'
        RETURN alm.alarm_id AS alarm_id, count(lot) AS fail_count
        ORDER BY fail_count DESC
        LIMIT 15
        """
    )
    if not df.empty:
        fig = px.bar(df, x="alarm_id", y="fail_count",
                     title="Top 15 alarms in FAIL lots",
                     labels={"fail_count": "# failing lots with this alarm"})
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# PAGE: Cypher Explorer
# ---------------------------------------------------------------------------

elif page == "Cypher Explorer":
    st.header("Cypher Explorer")

    examples = {
        "Lot with most SPC alarms": "MATCH (lot:Lot) RETURN lot.lot_id, lot.n_spc_alarms ORDER BY lot.n_spc_alarms DESC LIMIT 10",
        "FAIL lots and their alarm count": "MATCH (lot:Lot)-[:HAS_OUTCOME]->(out:YieldOutcome {outcome_id:'FAIL'}) RETURN lot.lot_id, lot.n_spc_alarms, lot.sensor_na_rate ORDER BY lot.n_spc_alarms DESC LIMIT 20",
        "Top alarming sensors in FAIL lots": "MATCH (lot:Lot)-[:TRIGGERED_ALARM]->(alm:SPCAlarm) MATCH (lot)-[:HAS_OUTCOME]->(:YieldOutcome {outcome_id:'FAIL'}) RETURN alm.alarm_id, count(*) AS n ORDER BY n DESC LIMIT 10",
        "Full path: Lot → Outcome + Alarms": "MATCH (lot:Lot {lot_id:'LOT_0042'})-[:HAS_OUTCOME]->(out:YieldOutcome) OPTIONAL MATCH (lot)-[r:TRIGGERED_ALARM]->(alm:SPCAlarm) RETURN lot.lot_id, out.outcome_id, alm.alarm_id, r.sigma_deviation",
        "Alarm count stats": "MATCH (lot:Lot) RETURN min(lot.n_spc_alarms) AS min, max(lot.n_spc_alarms) AS max, avg(lot.n_spc_alarms) AS avg",
    }

    selected = st.selectbox("Load example", ["(custom)"] + list(examples.keys()))
    default = examples.get(selected, "MATCH (n:Lot) RETURN n LIMIT 5")
    cypher_input = st.text_area("Cypher", value=default, height=120)

    if st.button("Run query", type="primary"):
        try:
            result = q(cypher_input)
            if result.empty:
                st.info("No results.")
            else:
                st.success(f"{len(result)} rows returned.")
                st.dataframe(result, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Query error: {exc}")
