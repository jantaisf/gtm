"""
Phase 2 Part 4: cACV Executive Dashboard

Streamlit app connected to BigQuery cacv_account and cacv_rep_rollup tables.
Allows executives to explore Consumed ARR (cACV) performance by Region and Rep.

Run:
    streamlit run app.py
    streamlit run app.py -- --as-of-date 2025-06-30
"""

import sys
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

GCP_PROJECT = "openclaw-gateway-491103"
DS_RAW      = f"`{GCP_PROJECT}.raw`"
DS_GTM      = f"`{GCP_PROJECT}.gtm`"
DS          = DS_GTM   # modelled tables (cacv_account, cacv_rep_rollup)

HEALTH_COLORS = {
    "Expansion": "#10b981",   # emerald
    "Healthy":   "#3b82f6",   # blue
    "At Risk":   "#f59e0b",   # amber
    "Shelfware": "#f97316",   # orange
    "Inactive":  "#ef4444",   # red
    "Ramping":   "#8b5cf6",   # violet
}

st.set_page_config(
    page_title="cACV Executive Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# BigQuery client (cached per session)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=GCP_PROJECT)


# ─────────────────────────────────────────────────────────────────────────────
# Data loading (cached with TTL)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="Loading rep rollup…")
def load_rep_rollup(as_of_date: str) -> pd.DataFrame:
    # Try exact date match first; fall back to latest available data
    sql = f"""
    SELECT *
    FROM {DS}.cacv_rep_rollup
    WHERE DATE(as_of_date) = DATE '{as_of_date}'
    """
    df = get_bq_client().query(sql).to_dataframe()
    if not df.empty:
        return df
    sql_latest = f"SELECT * FROM {DS}.cacv_rep_rollup ORDER BY calculated_at DESC LIMIT 1000"
    return get_bq_client().query(sql_latest).to_dataframe()


@st.cache_data(ttl=300, show_spinner="Loading account detail…")
def load_accounts(as_of_date: str, region: Optional[str] = None, employee_id: Optional[str] = None) -> pd.DataFrame:
    sql = f"""
    SELECT
        ca.*,
        sr.name    AS rep_name,
        sr.region,
        sr.segment
    FROM {DS}.cacv_account ca
    JOIN {DS_RAW}.sales_reps sr ON sr.employee_id = ca.employee_id
    WHERE DATE(ca.as_of_date) = DATE '{as_of_date}'
    """
    if region and region != "All":
        sql += f"\n    AND sr.region = '{region}'"
    if employee_id and employee_id != "All":
        sql += f"\n    AND ca.employee_id = '{employee_id}'"
    try:
        return get_bq_client().query(sql).to_dataframe()
    except Exception:
        sql_latest = f"""
        SELECT ca.*, sr.name AS rep_name, sr.region, sr.segment
        FROM {DS}.cacv_account ca
        JOIN {DS_RAW}.sales_reps sr ON sr.employee_id = ca.employee_id
        """
        df = get_bq_client().query(sql_latest).to_dataframe()
        if region and region != "All":
            df = df[df["region"] == region]
        if employee_id and employee_id != "All":
            df = df[df["employee_id"] == employee_id]
        return df


@st.cache_data(ttl=600, show_spinner=False)
def load_available_dates() -> list[str]:
    sql = f"""
    SELECT DISTINCT DATE(as_of_date) AS d
    FROM {DS}.cacv_rep_rollup
    ORDER BY 1 DESC
    LIMIT 30
    """
    try:
        df = get_bq_client().query(sql).to_dataframe()
        return [str(d) for d in df["d"].tolist()]
    except Exception:
        return [str(date.today())]


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_m(v) -> str:
    if pd.isna(v):
        return "—"
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def fmt_pct(v) -> str:
    if pd.isna(v):
        return "—"
    return f"{v:.1%}"


def delta_color(v) -> str:
    if pd.isna(v) or v == 0:
        return "off"
    return "normal" if v > 0 else "inverse"


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(rep_df: pd.DataFrame):
    st.sidebar.header("Filters")

    available_dates = load_available_dates()
    as_of_date = st.sidebar.selectbox(
        "As-of Date",
        options=available_dates,
        index=0,
        help="Pipeline run date",
    )

    regions = ["All"] + sorted(rep_df["region"].dropna().unique().tolist())
    region = st.sidebar.selectbox("Region", regions)

    rep_pool = rep_df if region == "All" else rep_df[rep_df["region"] == region]
    rep_options = ["All"] + sorted(rep_pool["rep_name"].dropna().unique().tolist())
    rep_name = st.sidebar.selectbox("Sales Rep", rep_options)
    employee_id = None
    if rep_name != "All":
        row = rep_pool[rep_pool["rep_name"] == rep_name]
        employee_id = row["employee_id"].iloc[0] if not row.empty else None

    st.sidebar.markdown("---")
    st.sidebar.caption(f"**Project:** {GCP_PROJECT}")
    st.sidebar.caption("**Datasets:** raw · staging · gtm")

    return as_of_date, region, rep_name, employee_id


# ─────────────────────────────────────────────────────────────────────────────
# Page: Overview
# ─────────────────────────────────────────────────────────────────────────────

def page_overview(rep_df: pd.DataFrame, acct_df: pd.DataFrame, region: str):
    st.header("Portfolio Overview")

    # rep_df is already filtered by region/rep from main()
    total_acv            = rep_df["total_acv"].sum()
    total_cacv           = rep_df["total_cacv"].sum()
    total_risk           = rep_df["total_acv_at_risk"].sum()
    att_rate             = total_cacv / total_acv if total_acv else 0
    expansion_signal     = rep_df["total_expansion_signal_acv"].sum() if "total_expansion_signal_acv" in rep_df.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total ACV",              fmt_m(total_acv))
    c2.metric("Total cACV",             fmt_m(total_cacv))
    c3.metric("cACV Attainment",        fmt_pct(att_rate))
    c4.metric("ACV at Risk",            fmt_m(total_risk),
              delta=f"-{fmt_m(total_risk)}", delta_color="inverse")
    c5.metric("Expansion Signal ARR",   fmt_m(expansion_signal),
              delta=fmt_m(expansion_signal), delta_color="normal",
              help="Over-commit consumption — upsell pipeline signal")

    st.markdown("---")

    col_left, col_right = st.columns(2)

    # cACV by Region waterfall-style bar
    with col_left:
        st.subheader("cACV by Region")
        region_df = (
            rep_df.groupby("region", as_index=False)
            .agg(total_acv=("total_acv", "sum"), total_cacv=("total_cacv", "sum"))
        )
        region_df["attainment"] = region_df["total_cacv"] / region_df["total_acv"]
        region_df = region_df.sort_values("total_cacv", ascending=False)

        fig = go.Figure()
        fig.add_bar(
            x=region_df["region"],
            y=region_df["total_acv"],
            name="ACV",
            marker_color="#e2e8f0",
            text=[fmt_m(v) for v in region_df["total_acv"]],
            textposition="outside",
        )
        fig.add_bar(
            x=region_df["region"],
            y=region_df["total_cacv"],
            name="cACV",
            marker_color="#3b82f6",
            text=[f"{fmt_m(v)}<br>{fmt_pct(r)}" for v, r in zip(region_df["total_cacv"], region_df["attainment"])],
            textposition="inside",
            textfont_color="white",
        )
        fig.update_layout(
            barmode="overlay",
            plot_bgcolor="white",
            margin=dict(t=20, b=40),
            legend=dict(orientation="h", y=-0.15),
            yaxis_tickprefix="$",
            yaxis_tickformat=",",
            height=340,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Health tier donut
    with col_right:
        st.subheader("Account Health Mix")
        health_counts = acct_df["health_tier"].value_counts().reset_index()
        health_counts.columns = ["health_tier", "count"]
        health_counts["color"] = health_counts["health_tier"].map(HEALTH_COLORS)

        fig2 = px.pie(
            health_counts,
            names="health_tier",
            values="count",
            color="health_tier",
            color_discrete_map=HEALTH_COLORS,
            hole=0.55,
        )
        fig2.update_traces(textposition="outside", textinfo="label+percent")
        fig2.update_layout(
            showlegend=False,
            margin=dict(t=20, b=20, l=20, r=20),
            height=340,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Attainment scatter
    st.subheader("cACV Attainment vs. ARR — by Rep")
    scatter_df = rep_df.copy()
    scatter_df["attainment_pct"] = scatter_df["cacv_attainment_rate"].fillna(0) * 100
    scatter_df["bubble_size"] = (scatter_df["total_acv"] / scatter_df["total_acv"].max() * 40).clip(lower=5)

    fig3 = px.scatter(
        scatter_df,
        x="total_acv",
        y="attainment_pct",
        size="bubble_size",
        color="region",
        hover_name="rep_name",
        hover_data={
            "total_acv":        ":.3s",
            "total_cacv":       ":.3s",
            "attainment_pct":   ":.1f",
            "total_accounts":   True,
            "accounts_at_risk": True,
            "bubble_size":      False,
        },
        labels={
            "total_acv":      "Total ARR ($)",
            "attainment_pct": "cACV Attainment (%)",
            "region":         "Region",
        },
        height=380,
    )
    fig3.add_hline(y=100, line_dash="dash", line_color="gray", annotation_text="100% target")
    fig3.add_hline(y=80,  line_dash="dot",  line_color="#f59e0b", annotation_text="80% floor")
    fig3.update_layout(plot_bgcolor="white", margin=dict(t=10))
    st.plotly_chart(fig3, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Region Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

def page_region(rep_df: pd.DataFrame):
    st.header("Region Breakdown")

    region_agg = (
        rep_df.groupby("region", as_index=False)
        .agg(
            reps=("employee_id", "count"),
            total_accounts=("total_accounts", "sum"),
            total_acv=("total_acv", "sum"),
            total_cacv=("total_cacv", "sum"),
            total_acv_at_risk=("total_acv_at_risk", "sum"),
            ramping_accounts=("ramping_accounts", "sum"),
            accounts_expansion=("accounts_expansion", "sum"),
            accounts_at_risk=("accounts_at_risk", "sum"),
            expansion_acv_pipeline=("expansion_acv_pipeline", "sum"),
            spike_drop_accounts=("spike_drop_accounts", "sum"),
        )
    )
    region_agg["att_rate"] = region_agg["total_cacv"] / region_agg["total_acv"]
    region_agg["risk_pct"] = region_agg["total_acv_at_risk"] / region_agg["total_acv"]
    region_agg = region_agg.sort_values("total_cacv", ascending=False)

    # Summary table
    display = region_agg[[
        "region", "reps", "total_accounts", "total_acv", "total_cacv",
        "att_rate", "total_acv_at_risk", "risk_pct",
        "accounts_expansion", "accounts_at_risk", "expansion_acv_pipeline",
    ]].copy()
    display.columns = [
        "Region", "Reps", "Accounts", "ACV", "cACV",
        "Attainment", "ACV at Risk", "Risk %",
        "Expansion Accts", "At-Risk Accts", "Expansion Pipeline",
    ]
    display["ACV"]               = display["ACV"].apply(fmt_m)
    display["cACV"]              = display["cACV"].apply(fmt_m)
    display["Attainment"]        = display["Attainment"].apply(fmt_pct)
    display["ACV at Risk"]       = display["ACV at Risk"].apply(fmt_m)
    display["Risk %"]            = display["Risk %"].apply(fmt_pct)
    display["Expansion Pipeline"]= display["Expansion Pipeline"].apply(fmt_m)

    st.dataframe(display, use_container_width=True, hide_index=True)

    # Health heatmap by region
    st.subheader("Health Tier Mix by Region")
    tier_cols = ["accounts_expansion", "accounts_healthy", "accounts_at_risk",
                 "accounts_shelfware", "accounts_inactive", "accounts_ramping"]
    tier_labels = ["Expansion", "Healthy", "At Risk", "Shelfware", "Inactive", "Ramping"]

    # Pull these from rep_df aggregation
    region_health = (
        rep_df.groupby("region", as_index=False)[tier_cols].sum()
    )
    # Normalize to %
    region_health_pct = region_health.copy()
    row_totals = region_health[tier_cols].sum(axis=1)
    for col in tier_cols:
        region_health_pct[col] = region_health[col] / row_totals * 100

    fig = go.Figure()
    for col, label in zip(tier_cols, tier_labels):
        fig.add_bar(
            name=label,
            x=region_health_pct["region"],
            y=region_health_pct[col],
            marker_color=HEALTH_COLORS[label],
            text=region_health_pct[col].apply(lambda v: f"{v:.0f}%"),
            textposition="inside",
        )
    fig.update_layout(
        barmode="stack",
        plot_bgcolor="white",
        yaxis_title="% of Accounts",
        margin=dict(t=10, b=40),
        legend=dict(orientation="h", y=-0.2),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Rep Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

def page_reps(rep_df: pd.DataFrame, region: str):
    st.header("Rep Leaderboard")

    # rep_df is already filtered by region/rep from main()
    filtered = rep_df.sort_values("total_cacv", ascending=False).reset_index(drop=True)

    # Top/bottom callouts
    c1, c2 = st.columns(2)
    if not filtered.empty:
        top = filtered.iloc[0]
        bot = filtered.iloc[-1]
        with c1:
            st.success(f"**#1 {top['rep_name']}** ({top['region']})  \n"
                       f"cACV: **{fmt_m(top['total_cacv'])}** · Attainment: **{fmt_pct(top['cacv_attainment_rate'])}**")
        with c2:
            att = bot['cacv_attainment_rate']
            msg = f"**{bot['rep_name']}** ({bot['region']})  \ncACV: **{fmt_m(bot['total_cacv'])}** · Attainment: **{fmt_pct(att)}**"
            if pd.notna(att) and att < 0.6:
                st.error(msg)
            else:
                st.info(msg)

    # Horizontal bar chart ranked
    chart_df = filtered.nlargest(20, "total_cacv")
    fig = go.Figure()
    fig.add_bar(
        y=chart_df["rep_name"],
        x=chart_df["total_acv"],
        name="ACV",
        orientation="h",
        marker_color="#e2e8f0",
    )
    fig.add_bar(
        y=chart_df["rep_name"],
        x=chart_df["total_cacv"],
        name="cACV",
        orientation="h",
        marker_color="#3b82f6",
        text=[f"{fmt_m(v)}  {fmt_pct(r)}" for v, r in
              zip(chart_df["total_cacv"], chart_df["cacv_attainment_rate"])],
        textposition="inside",
        textfont_color="white",
    )
    fig.update_layout(
        barmode="overlay",
        plot_bgcolor="white",
        margin=dict(t=10, l=140),
        legend=dict(orientation="h", y=-0.1),
        xaxis_tickprefix="$",
        xaxis_tickformat=",",
        height=max(300, len(chart_df) * 28),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Detailed table
    st.subheader("Full Rep Table")
    extra_cols = ["total_expansion_signal_acv"] if "total_expansion_signal_acv" in filtered.columns else []
    tbl = filtered[[
        "org_rank", "region_rank", "rep_name", "region", "segment",
        "total_accounts", "ramping_accounts", "mature_accounts",
        "total_acv", "total_cacv", "cacv_attainment_rate",
        "total_acv_at_risk", "expansion_opportunities", "expansion_acv_pipeline",
    ] + extra_cols + [
        "accounts_expansion", "accounts_healthy", "accounts_at_risk",
        "accounts_shelfware", "accounts_inactive",
    ]].copy()
    base_labels = [
        "Org#", "Rgn#", "Rep", "Region", "Segment",
        "Accts", "Ramping", "Mature",
        "ACV", "cACV", "Attainment",
        "ACV at Risk", "Exp Opps", "Exp Pipeline",
    ]
    extra_labels = ["Exp Signal ARR"] if extra_cols else []
    tbl.columns = base_labels + extra_labels + ["Expansion", "Healthy", "At Risk", "Shelfware", "Inactive"]
    for col in ["ACV", "cACV", "ACV at Risk", "Exp Pipeline"] + (["Exp Signal ARR"] if extra_labels else []):
        tbl[col] = tbl[col].apply(fmt_m)
    tbl["Attainment"] = tbl["Attainment"].apply(fmt_pct)

    st.dataframe(tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Account Detail
# ─────────────────────────────────────────────────────────────────────────────

def page_accounts(acct_df: pd.DataFrame, rep_name: str):
    title = f"Account Detail — {rep_name}" if rep_name != "All" else "Account Detail"
    st.header(title)

    if acct_df.empty:
        st.info("No accounts match the current filter.")
        return

    # Health tier filter
    tiers = ["All"] + sorted(acct_df["health_tier"].dropna().unique().tolist())
    sel_tier = st.selectbox("Health Tier", tiers, key="acct_tier_filter")
    view = acct_df if sel_tier == "All" else acct_df[acct_df["health_tier"] == sel_tier]

    # Scatter: ARR vs consumption rate, colored by health
    fig = px.scatter(
        view.dropna(subset=["trailing_90d_avg_rate"]),
        x="annual_commit_dollars",
        y="trailing_90d_avg_rate",
        color="health_tier",
        color_discrete_map=HEALTH_COLORS,
        size="annual_commit_dollars",
        size_max=22,
        hover_name="company_name",
        hover_data={
            "annual_commit_dollars": ":.3s",
            "trailing_90d_avg_rate": ":.2f",
            "cacv":                  ":.3s",
            "rep_name":              True,
            "health_tier":           True,
        },
        labels={
            "annual_commit_dollars":  "ACV ($)",
            "trailing_90d_avg_rate":  "Consumption Rate (90d avg)",
        },
        height=400,
    )
    fig.add_hline(y=1.0,  line_dash="dash", line_color="gray",  annotation_text="100% commit")
    fig.add_hline(y=0.80, line_dash="dot",  line_color="#f59e0b", annotation_text="80% floor")
    fig.update_layout(plot_bgcolor="white", margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    # Account table
    exp_signal_cols = ["expansion_signal_acv"] if "expansion_signal_acv" in view.columns else []
    tbl = view[[
        "company_name", "rep_name", "region", "health_tier",
        "annual_commit_dollars", "trailing_90d_avg_rate", "cacv",
    ] + exp_signal_cols + [
        "acv_at_risk",
        "months_of_data", "expansion_flag", "is_spike_drop", "is_new_account",
        "contract_start_date", "contract_end_date",
    ]].copy()
    exp_signal_labels = ["Exp Signal"] if exp_signal_cols else []
    tbl.columns = (
        ["Account", "Rep", "Region", "Health",
         "ACV", "Cons Rate", "cACV"]
        + exp_signal_labels
        + ["ACV at Risk",
           "Months Data", "Expansion?", "Spike/Drop?", "Ramping?",
           "Contract Start", "Contract End"]
    )
    tbl["ACV"]          = tbl["ACV"].apply(fmt_m)
    tbl["cACV"]         = tbl["cACV"].apply(fmt_m)
    tbl["ACV at Risk"]  = tbl["ACV at Risk"].apply(fmt_m)
    if exp_signal_labels:
        tbl["Exp Signal"] = tbl["Exp Signal"].apply(fmt_m)
    tbl["Cons Rate"]  = tbl["Cons Rate"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")

    def color_health(val):
        color_map = {
            "Expansion": "#d1fae5",
            "Healthy":   "#dbeafe",
            "At Risk":   "#fef3c7",
            "Shelfware": "#ffedd5",
            "Inactive":  "#fee2e2",
            "Ramping":   "#ede9fe",
        }
        return f"background-color: {color_map.get(val, '')}"

    styled = tbl.style.applymap(color_health, subset=["Health"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.title("Prisma Cloud cACV Executive Dashboard")
    st.caption("Consumed Annual Recurring Revenue · Prisma Cloud · Powered by BigQuery")

    # Load rep data first (needed for sidebar)
    with st.spinner("Connecting to BigQuery…"):
        try:
            available_dates = load_available_dates()
            initial_date = available_dates[0] if available_dates else str(date.today())
            rep_df_full = load_rep_rollup(initial_date)
        except Exception as e:
            st.error(f"BigQuery connection failed: {e}")
            st.info("Ensure ADC credentials are set: `gcloud auth application-default login`")
            st.stop()

    if rep_df_full.empty:
        st.warning("No data found. Run the pipeline first: `python3 run_pipeline.py --as-of-date YYYY-MM-DD`")
        st.stop()

    as_of_date, region, rep_name, employee_id = render_sidebar(rep_df_full)

    # Full dataset for the selected date (used by region-level charts)
    rep_df = load_rep_rollup(as_of_date)

    # Filtered view: apply region + rep selection for KPIs and rep pages
    rep_df_view = rep_df.copy()
    if region != "All":
        rep_df_view = rep_df_view[rep_df_view["region"] == region]
    if employee_id:
        rep_df_view = rep_df_view[rep_df_view["employee_id"] == employee_id]

    acct_df = load_accounts(as_of_date, region, employee_id)

    # Navigation tabs
    tab_overview, tab_region, tab_reps, tab_accounts = st.tabs([
        "📊 Overview", "🗺️ By Region", "👤 By Rep", "🏢 Accounts"
    ])

    with tab_overview:
        # Pass rep_df_view so KPIs reflect the active filter
        page_overview(rep_df_view, acct_df, region)

    with tab_region:
        # Always show all regions for context
        page_region(rep_df)

    with tab_reps:
        # Pass rep_df_view so leaderboard reflects region/rep filter
        page_reps(rep_df_view, region)

    with tab_accounts:
        page_accounts(acct_df, rep_name)


if __name__ == "__main__":
    main()
