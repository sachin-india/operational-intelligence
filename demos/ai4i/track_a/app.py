"""AI4I Track A — Streamlit graph explorer.

Passive knowledge graph: browse and query the AI4I Manufacturing graph.
No actions, no governance — pure read-only exploration.

Run:
    uv run streamlit run demos/ai4i/track_a/app.py
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from core.ontology.graph import GraphSession


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI4I — Track A: Knowledge Graph",
    page_icon="🔧",
    layout="wide",
)

st.title("🔧 AI4I Predictive Maintenance — Track A")
st.caption(
    "Passive knowledge graph: browse Machine → ToolRun → FailureMode relationships. "
    "No actions, no governance — read-only exploration."
)


# ---------------------------------------------------------------------------
# Connection (cached so we don't reconnect on every interaction)
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
    st.info("Start Neo4j with: `docker compose -f infra/docker-compose.yml up -d`")
    st.stop()


# ---------------------------------------------------------------------------
# Sidebar — page navigation
# ---------------------------------------------------------------------------

page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Machines", "Tool Runs", "Failure Modes", "Cypher Explorer"],
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Graph schema**")
st.sidebar.markdown(
    """
    ```
    (Machine)
       -[:HAS_RUN]->
    (ToolRun)
       -[:HAS_FAILURE]->
    (FailureMode)
    ```
    """
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def query(_graph_key: str, cypher: str, **params) -> pd.DataFrame:
    rows = graph.run(cypher, **params)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def q(cypher: str, **params) -> pd.DataFrame:
    return query(id(graph), cypher, **params)


# ---------------------------------------------------------------------------
# PAGE: Overview
# ---------------------------------------------------------------------------

if page == "Overview":
    st.header("Graph Overview")

    col1, col2, col3, col4, col5 = st.columns(5)

    machines_count = q("MATCH (n:Machine) RETURN count(n) AS cnt")
    tool_runs_count = q("MATCH (n:ToolRun) RETURN count(n) AS cnt")
    failure_modes_count = q("MATCH (n:FailureMode) RETURN count(n) AS cnt")
    has_run_count = q("MATCH ()-[r:HAS_RUN]->() RETURN count(r) AS cnt")
    has_failure_count = q("MATCH ()-[r:HAS_FAILURE]->() RETURN count(r) AS cnt")

    col1.metric("Machine nodes", machines_count["cnt"].iloc[0] if not machines_count.empty else 0)
    col2.metric("ToolRun nodes", f"{tool_runs_count['cnt'].iloc[0]:,}" if not tool_runs_count.empty else 0)
    col3.metric("FailureMode nodes", failure_modes_count["cnt"].iloc[0] if not failure_modes_count.empty else 0)
    col4.metric("HAS_RUN rels", f"{has_run_count['cnt'].iloc[0]:,}" if not has_run_count.empty else 0)
    col5.metric("HAS_FAILURE rels", has_failure_count["cnt"].iloc[0] if not has_failure_count.empty else 0)

    st.markdown("---")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Failure rate by machine type")
        df = q(
            """
            MATCH (m:Machine)-[:HAS_RUN]->(r:ToolRun)
            RETURN m.machine_type AS machine_type,
                   count(r) AS total_runs,
                   sum(CASE WHEN r.machine_failure = true THEN 1 ELSE 0 END) AS failures
            ORDER BY machine_type
            """
        )
        if not df.empty:
            df["failure_rate_pct"] = (df["failures"] / df["total_runs"] * 100).round(2)
            fig = px.bar(
                df,
                x="machine_type",
                y="failure_rate_pct",
                color="machine_type",
                labels={"machine_type": "Machine Type", "failure_rate_pct": "Failure Rate (%)"},
                title="Failure rate by machine quality tier",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("Failure mode distribution")
        df = q(
            """
            MATCH (r:ToolRun)-[:HAS_FAILURE]->(f:FailureMode)
            RETURN f.failure_name AS failure_name, count(r) AS occurrences
            ORDER BY occurrences DESC
            """
        )
        if not df.empty:
            fig = px.pie(
                df,
                names="failure_name",
                values="occurrences",
                title="Breakdown of failure types",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No failure links found — run the loader first.")


# ---------------------------------------------------------------------------
# PAGE: Machines
# ---------------------------------------------------------------------------

elif page == "Machines":
    st.header("Machines")

    df = q(
        """
        MATCH (m:Machine)-[:HAS_RUN]->(r:ToolRun)
        RETURN m.machine_id AS machine_id,
               m.machine_type AS machine_type,
               count(r) AS total_runs,
               sum(CASE WHEN r.machine_failure = true THEN 1 ELSE 0 END) AS failed_runs,
               round(avg(r.tool_wear_min), 1) AS avg_tool_wear_min,
               round(avg(r.torque_nm), 2) AS avg_torque_nm,
               round(avg(r.rotational_speed_rpm), 0) AS avg_rpm
        ORDER BY m.machine_type
        """
    )

    if df.empty:
        st.warning("No machines found — run the loader first.")
    else:
        df["failure_rate_pct"] = (df["failed_runs"] / df["total_runs"] * 100).round(2)
        st.dataframe(df, use_container_width=True, hide_index=True)

        selected = st.selectbox("Drill into machine", df["machine_id"].tolist())

        st.subheader(f"Recent ToolRuns for {selected}")
        runs = q(
            """
            MATCH (m:Machine {machine_id: $mid})-[:HAS_RUN]->(r:ToolRun)
            RETURN r.run_id AS run_id, r.event_time AS event_time,
                   r.air_temp_k AS air_temp_k, r.process_temp_k AS process_temp_k,
                   r.rotational_speed_rpm AS rpm, r.torque_nm AS torque_nm,
                   r.tool_wear_min AS tool_wear_min, r.machine_failure AS failed
            ORDER BY r.run_id DESC
            LIMIT 50
            """,
            mid=selected,
        )
        st.dataframe(runs, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# PAGE: Tool Runs
# ---------------------------------------------------------------------------

elif page == "Tool Runs":
    st.header("Tool Runs")

    col1, col2 = st.columns(2)
    with col1:
        machine_filter = st.selectbox(
            "Filter by machine",
            ["All", "MACHINE_L", "MACHINE_M", "MACHINE_H"],
        )
    with col2:
        failure_only = st.checkbox("Show failures only", value=False)

    where_clauses = []
    params: dict = {}
    if machine_filter != "All":
        where_clauses.append("r.machine_id = $machine_id")
        params["machine_id"] = machine_filter
    if failure_only:
        where_clauses.append("r.machine_failure = true")

    where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    df = q(
        f"""
        MATCH (r:ToolRun)
        {where}
        RETURN r.run_id AS run_id, r.machine_id AS machine_id,
               r.event_time AS event_time,
               r.air_temp_k AS air_temp_k,
               r.process_temp_k AS process_temp_k,
               r.rotational_speed_rpm AS rpm,
               r.torque_nm AS torque_nm,
               r.tool_wear_min AS tool_wear_min,
               r.machine_failure AS failed
        ORDER BY r.run_id DESC
        LIMIT 200
        """,
        **params,
    )

    st.caption(f"Showing up to 200 rows (use Cypher Explorer for full queries)")
    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        st.subheader("Sensor distributions")
        metric = st.selectbox(
            "Metric",
            ["air_temp_k", "process_temp_k", "rpm", "torque_nm", "tool_wear_min"],
        )
        fig = px.histogram(df, x=metric, color="failed", nbins=40,
                           title=f"Distribution of {metric}")
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# PAGE: Failure Modes
# ---------------------------------------------------------------------------

elif page == "Failure Modes":
    st.header("Failure Modes")

    df = q(
        """
        MATCH (f:FailureMode)
        OPTIONAL MATCH (r:ToolRun)-[:HAS_FAILURE]->(f)
        RETURN f.failure_id AS failure_id,
               f.failure_name AS failure_name,
               count(r) AS occurrences
        ORDER BY occurrences DESC
        """
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

    selected_failure = st.selectbox("Drill into failure mode", df["failure_id"].tolist())

    st.subheader(f"Runs with {selected_failure}")
    runs = q(
        """
        MATCH (r:ToolRun)-[:HAS_FAILURE]->(f:FailureMode {failure_id: $fid})
        RETURN r.run_id AS run_id, r.machine_id AS machine_id,
               r.event_time AS event_time,
               r.tool_wear_min AS tool_wear_min,
               r.torque_nm AS torque_nm,
               r.rotational_speed_rpm AS rpm
        ORDER BY r.run_id
        LIMIT 100
        """,
        fid=selected_failure,
    )
    st.dataframe(runs, use_container_width=True, hide_index=True)

    if not runs.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.scatter(
                runs, x="tool_wear_min", y="torque_nm",
                color="machine_id",
                title=f"Tool wear vs Torque for {selected_failure} runs",
            )
            st.plotly_chart(fig, use_container_width=True)
        with col_b:
            machine_counts = runs["machine_id"].value_counts().reset_index()
            machine_counts.columns = ["machine_id", "count"]
            fig = px.bar(machine_counts, x="machine_id", y="count",
                         title="Which machines experience this failure?")
            st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# PAGE: Cypher Explorer
# ---------------------------------------------------------------------------

elif page == "Cypher Explorer":
    st.header("Cypher Explorer")
    st.caption("Run any read-only Cypher query against the AI4I graph.")

    examples = {
        "Top 10 runs by tool wear": "MATCH (r:ToolRun) RETURN r.run_id, r.machine_id, r.tool_wear_min ORDER BY r.tool_wear_min DESC LIMIT 10",
        "Failure counts by type": "MATCH (r:ToolRun)-[:HAS_FAILURE]->(f:FailureMode) RETURN f.failure_name, count(r) AS n ORDER BY n DESC",
        "Runs on MACHINE_H that failed": "MATCH (m:Machine {machine_id:'MACHINE_H'})-[:HAS_RUN]->(r:ToolRun) WHERE r.machine_failure = true RETURN r.run_id, r.event_time, r.tool_wear_min ORDER BY r.tool_wear_min DESC LIMIT 20",
        "All machine nodes": "MATCH (m:Machine) RETURN m",
        "HAS_FAILURE path sample": "MATCH p = (r:ToolRun)-[:HAS_FAILURE]->(f:FailureMode) RETURN r.run_id, f.failure_name LIMIT 10",
    }

    selected_example = st.selectbox("Load example query", ["(custom)"] + list(examples.keys()))
    default_cypher = examples.get(selected_example, "MATCH (n) RETURN n LIMIT 5")

    cypher_input = st.text_area("Cypher", value=default_cypher, height=120)

    if st.button("Run query", type="primary"):
        try:
            result = q(cypher_input)
            if result.empty:
                st.info("Query returned no results.")
            else:
                st.success(f"{len(result)} rows returned.")
                st.dataframe(result, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"Query error: {exc}")
