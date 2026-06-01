"""
cACV Executive Dashboard
Prisma Cloud · Consumed ACV North Star Metric

Data loading: tries BigQuery first (local dev with GCP credentials),
falls back automatically to committed CSV snapshots (Streamlit Cloud / demo).

Run locally:
    streamlit run dashboard/app.py
    streamlit run dashboard/app.py -- --as-of-date 2025-06-30

Deploy:
    Streamlit Community Cloud → connect GitHub repo → set main file to dashboard/app.py
    No secrets required for demo mode; BigQuery creds optional via st.secrets.
"""

from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

GCP_PROJECT   = "openclaw-gateway-491103"
DEMO_DATA_DIR = Path(__file__).parent / "demo_data"

HEALTH_COLORS = {
    "Expansion": "#10b981",
    "Healthy":   "#3b82f6",
    "At Risk":   "#f59e0b",
    "Shelfware": "#f97316",
    "Inactive":  "#ef4444",
    "Ramping":   "#8b5cf6",
}

st.set_page_config(
    page_title="cACV Executive Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# BigQuery client — optional; gracefully absent in demo mode
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _get_bq_client():
    """Return a BigQuery client or None if credentials are unavailable."""
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=GCP_PROJECT)
        # Cheap probe — fails fast if credentials are missing or insufficient
        client.query("SELECT 1").result()
        return client
    except Exception:
        return None


def _bq() -> object:
    return _get_bq_client()


# ─────────────────────────────────────────────────────────────────────────────
# Demo-mode detection (set once at startup)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _is_demo() -> bool:
    return _bq() is None


# ─────────────────────────────────────────────────────────────────────────────
# Data loading — BigQuery first, CSV fallback
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner="Loading rep data…")
def load_rep_rollup(as_of_date: str) -> pd.DataFrame:
    client = _bq()
    if client is not None:
        DS = f"`{GCP_PROJECT}.gtm`"
        sql = f"""
        SELECT * FROM {DS}.cacv_rep_rollup
        WHERE DATE(as_of_date) = DATE '{as_of_date}'
        """
        df = client.query(sql).to_dataframe()
        if not df.empty:
            return df
        # Fall back to latest available date
        return client.query(
            f"SELECT * FROM {DS}.cacv_rep_rollup ORDER BY calculated_at DESC LIMIT 1000"
        ).to_dataframe()

    # CSV fallback
    df = pd.read_csv(DEMO_DATA_DIR / "rep_rollup.csv")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
    match = df[df["as_of_date"].astype(str) == as_of_date]
    return match if not match.empty else df


@st.cache_data(ttl=300, show_spinner="Loading account detail…")
def load_accounts(
    as_of_date: str,
    region: Optional[str] = None,
    employee_id: Optional[str] = None,
) -> pd.DataFrame:
    client = _bq()
    if client is not None:
        DS     = f"`{GCP_PROJECT}.gtm`"
        DS_RAW = f"`{GCP_PROJECT}.raw`"
        sql = f"""
        SELECT ca.*, sr.name AS rep_name, sr.region, sr.segment
        FROM {DS}.cacv_account ca
        JOIN {DS_RAW}.sales_reps sr ON sr.employee_id = ca.employee_id
        WHERE DATE(ca.as_of_date) = DATE '{as_of_date}'
        """
        if region and region != "All":
            sql += f"\n    AND sr.region = '{region}'"
        if employee_id and employee_id != "All":
            sql += f"\n    AND ca.employee_id = '{employee_id}'"
        try:
            return client.query(sql).to_dataframe()
        except Exception:
            df = client.query(f"""
                SELECT ca.*, sr.name AS rep_name, sr.region, sr.segment
                FROM {DS}.cacv_account ca
                JOIN {DS_RAW}.sales_reps sr ON sr.employee_id = ca.employee_id
            """).to_dataframe()
            if region and region != "All":
                df = df[df["region"] == region]
            if employee_id and employee_id != "All":
                df = df[df["employee_id"] == employee_id]
            return df

    # CSV fallback
    df = pd.read_csv(DEMO_DATA_DIR / "accounts.csv")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
    match = df[df["as_of_date"].astype(str) == as_of_date]
    df = match if not match.empty else df
    if region and region != "All":
        df = df[df["region"] == region]
    if employee_id and employee_id != "All":
        df = df[df["employee_id"] == employee_id]
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_available_dates() -> list:
    client = _bq()
    if client is not None:
        DS = f"`{GCP_PROJECT}.gtm`"
        try:
            df = client.query(f"""
                SELECT DISTINCT DATE(as_of_date) AS d
                FROM {DS}.cacv_rep_rollup
                ORDER BY 1 DESC LIMIT 30
            """).to_dataframe()
            return [str(d) for d in df["d"].tolist()]
        except Exception:
            pass

    # CSV fallback
    df = pd.read_csv(DEMO_DATA_DIR / "rep_rollup.csv")
    dates = sorted(df["as_of_date"].astype(str).unique(), reverse=True)
    return dates[:30]


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
        help="Pipeline snapshot date",
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
    if _is_demo():
        st.sidebar.caption("📊 **Demo mode** — cached snapshot")
        st.sidebar.caption("Connect BigQuery for live data")
    else:
        st.sidebar.caption(f"**Project:** {GCP_PROJECT}")
        st.sidebar.caption("**Datasets:** raw · staging · gtm")

    return as_of_date, region, rep_name, employee_id


# ─────────────────────────────────────────────────────────────────────────────
# Page: Overview
# ─────────────────────────────────────────────────────────────────────────────

def page_overview(rep_df: pd.DataFrame, acct_df: pd.DataFrame, region: str):
    st.header("Portfolio Overview")

    total_acv        = rep_df["total_acv"].sum()
    total_cacv       = rep_df["total_cacv"].sum()
    total_risk       = rep_df["total_acv_at_risk"].sum()
    att_rate         = total_cacv / total_acv if total_acv else 0
    expansion_signal = (
        rep_df["total_expansion_signal_acv"].sum()
        if "total_expansion_signal_acv" in rep_df.columns else 0
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total ACV",          fmt_m(total_acv))
    c2.metric("Total cACV",         fmt_m(total_cacv))
    c3.metric("cACV Attainment",    fmt_pct(att_rate))
    c4.metric("ACV at Risk",        fmt_m(total_risk),
              delta=f"-{fmt_m(total_risk)}", delta_color="inverse")
    c5.metric("Expansion Signal",   fmt_m(expansion_signal),
              delta=fmt_m(expansion_signal), delta_color="normal",
              help="Over-commit consumption — upsell pipeline signal")

    st.markdown("---")
    col_left, col_right = st.columns(2)

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
            x=region_df["region"], y=region_df["total_acv"], name="ACV",
            marker_color="#e2e8f0",
            text=[fmt_m(v) for v in region_df["total_acv"]], textposition="outside",
        )
        fig.add_bar(
            x=region_df["region"], y=region_df["total_cacv"], name="cACV",
            marker_color="#3b82f6",
            text=[f"{fmt_m(v)}<br>{fmt_pct(r)}"
                  for v, r in zip(region_df["total_cacv"], region_df["attainment"])],
            textposition="inside", textfont_color="white",
        )
        fig.update_layout(
            barmode="overlay", plot_bgcolor="white",
            margin=dict(t=20, b=40), legend=dict(orientation="h", y=-0.15),
            yaxis_tickprefix="$", yaxis_tickformat=",", height=340,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("Account Health Mix")
        health_counts = acct_df["health_tier"].value_counts().reset_index()
        health_counts.columns = ["health_tier", "count"]

        fig2 = px.pie(
            health_counts, names="health_tier", values="count",
            color="health_tier", color_discrete_map=HEALTH_COLORS, hole=0.55,
        )
        fig2.update_traces(textposition="outside", textinfo="label+percent")
        fig2.update_layout(showlegend=False, margin=dict(t=20, b=20, l=20, r=20), height=340)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("cACV Attainment vs. ACV — by Rep")
    scatter_df = rep_df.copy()
    scatter_df["attainment_pct"] = scatter_df["cacv_attainment_rate"].fillna(0) * 100
    scatter_df["bubble_size"] = (
        scatter_df["total_acv"] / scatter_df["total_acv"].max() * 40
    ).clip(lower=5)

    fig3 = px.scatter(
        scatter_df, x="total_acv", y="attainment_pct",
        size="bubble_size", color="region",
        hover_name="rep_name",
        hover_data={
            "total_acv": ":.3s", "total_cacv": ":.3s",
            "attainment_pct": ":.1f", "total_accounts": True,
            "accounts_at_risk": True, "bubble_size": False,
        },
        labels={"total_acv": "Total ACV ($)", "attainment_pct": "cACV Attainment (%)", "region": "Region"},
        height=380,
    )
    fig3.add_hline(y=100, line_dash="dash", line_color="gray",   annotation_text="100% target")
    fig3.add_hline(y=80,  line_dash="dot",  line_color="#f59e0b", annotation_text="80% floor")
    fig3.update_layout(plot_bgcolor="white", margin=dict(t=10))
    st.plotly_chart(fig3, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Region Breakdown
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
    for col in ["ACV", "cACV", "ACV at Risk", "Expansion Pipeline"]:
        display[col] = display[col].apply(fmt_m)
    display["Attainment"] = display["Attainment"].apply(fmt_pct)
    display["Risk %"]     = display["Risk %"].apply(fmt_pct)
    st.dataframe(display, use_container_width=True, hide_index=True)

    st.subheader("Health Tier Mix by Region")
    tier_cols   = ["accounts_expansion", "accounts_healthy", "accounts_at_risk",
                   "accounts_shelfware", "accounts_inactive", "accounts_ramping"]
    tier_labels = ["Expansion", "Healthy", "At Risk", "Shelfware", "Inactive", "Ramping"]

    region_health = rep_df.groupby("region", as_index=False)[tier_cols].sum()
    region_health_pct = region_health.copy()
    row_totals = region_health[tier_cols].sum(axis=1)
    for col in tier_cols:
        region_health_pct[col] = region_health[col] / row_totals * 100

    fig = go.Figure()
    for col, label in zip(tier_cols, tier_labels):
        fig.add_bar(
            name=label, x=region_health_pct["region"], y=region_health_pct[col],
            marker_color=HEALTH_COLORS[label],
            text=region_health_pct[col].apply(lambda v: f"{v:.0f}%"),
            textposition="inside",
        )
    fig.update_layout(
        barmode="stack", plot_bgcolor="white", yaxis_title="% of Accounts",
        margin=dict(t=10, b=40), legend=dict(orientation="h", y=-0.2), height=360,
    )
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Rep Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

def page_reps(rep_df: pd.DataFrame, region: str):
    st.header("Rep Leaderboard")

    filtered = rep_df.sort_values("total_cacv", ascending=False).reset_index(drop=True)

    c1, c2 = st.columns(2)
    if not filtered.empty:
        top = filtered.iloc[0]
        bot = filtered.iloc[-1]
        with c1:
            st.success(
                f"**#1 {top['rep_name']}** ({top['region']})  \n"
                f"cACV: **{fmt_m(top['total_cacv'])}** · Attainment: **{fmt_pct(top['cacv_attainment_rate'])}**"
            )
        with c2:
            att = bot["cacv_attainment_rate"]
            msg = (
                f"**{bot['rep_name']}** ({bot['region']})  \n"
                f"cACV: **{fmt_m(bot['total_cacv'])}** · Attainment: **{fmt_pct(att)}**"
            )
            if pd.notna(att) and att < 0.6:
                st.error(msg)
            else:
                st.info(msg)

    chart_df = filtered.nlargest(20, "total_cacv")
    fig = go.Figure()
    fig.add_bar(
        y=chart_df["rep_name"], x=chart_df["total_acv"], name="ACV",
        orientation="h", marker_color="#e2e8f0",
    )
    fig.add_bar(
        y=chart_df["rep_name"], x=chart_df["total_cacv"], name="cACV",
        orientation="h", marker_color="#3b82f6",
        text=[f"{fmt_m(v)}  {fmt_pct(r)}"
              for v, r in zip(chart_df["total_cacv"], chart_df["cacv_attainment_rate"])],
        textposition="inside", textfont_color="white",
    )
    fig.update_layout(
        barmode="overlay", plot_bgcolor="white",
        margin=dict(t=10, l=140), legend=dict(orientation="h", y=-0.1),
        xaxis_tickprefix="$", xaxis_tickformat=",",
        height=max(300, len(chart_df) * 28), yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Full Rep Table")
    extra_cols   = ["total_expansion_signal_acv"] if "total_expansion_signal_acv" in filtered.columns else []
    extra_labels = ["Exp Signal"] if extra_cols else []
    tbl = filtered[[
        "org_rank", "region_rank", "rep_name", "region", "segment",
        "total_accounts", "ramping_accounts", "mature_accounts",
        "total_acv", "total_cacv", "cacv_attainment_rate",
        "total_acv_at_risk", "expansion_opportunities", "expansion_acv_pipeline",
    ] + extra_cols + [
        "accounts_expansion", "accounts_healthy", "accounts_at_risk",
        "accounts_shelfware", "accounts_inactive",
    ]].copy()
    tbl.columns = (
        ["Org#", "Rgn#", "Rep", "Region", "Segment",
         "Accts", "Ramping", "Mature",
         "ACV", "cACV", "Attainment",
         "ACV at Risk", "Exp Opps", "Exp Pipeline"]
        + extra_labels
        + ["Expansion", "Healthy", "At Risk", "Shelfware", "Inactive"]
    )
    for col in ["ACV", "cACV", "ACV at Risk", "Exp Pipeline"] + extra_labels:
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

    tiers    = ["All"] + sorted(acct_df["health_tier"].dropna().unique().tolist())
    sel_tier = st.selectbox("Health Tier", tiers, key="acct_tier_filter")
    view     = acct_df if sel_tier == "All" else acct_df[acct_df["health_tier"] == sel_tier]

    fig = px.scatter(
        view.dropna(subset=["trailing_90d_avg_rate"]),
        x="annual_commit_dollars", y="trailing_90d_avg_rate",
        color="health_tier", color_discrete_map=HEALTH_COLORS,
        size="annual_commit_dollars", size_max=22,
        hover_name="company_name",
        hover_data={
            "annual_commit_dollars": ":.3s",
            "trailing_90d_avg_rate": ":.2f",
            "cacv": ":.3s",
            "rep_name": True, "health_tier": True,
        },
        labels={
            "annual_commit_dollars": "ACV ($)",
            "trailing_90d_avg_rate": "Consumption Rate (90-day avg)",
        },
        height=400,
    )
    fig.add_hline(y=1.0,  line_dash="dash", line_color="gray",   annotation_text="100% commit")
    fig.add_hline(y=0.80, line_dash="dot",  line_color="#f59e0b", annotation_text="80% floor")
    fig.update_layout(plot_bgcolor="white", margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    exp_signal_cols   = ["expansion_signal_acv"] if "expansion_signal_acv" in view.columns else []
    exp_signal_labels = ["Exp Signal"] if exp_signal_cols else []
    tbl = view[[
        "company_name", "rep_name", "region", "health_tier",
        "annual_commit_dollars", "trailing_90d_avg_rate", "cacv",
    ] + exp_signal_cols + [
        "acv_at_risk", "months_of_data",
        "expansion_flag", "is_spike_drop", "is_new_account",
        "contract_start_date", "contract_end_date",
    ]].copy()
    tbl.columns = (
        ["Account", "Rep", "Region", "Health",
         "ACV", "Cons Rate", "cACV"]
        + exp_signal_labels
        + ["ACV at Risk", "Months Data",
           "Expansion?", "Spike/Drop?", "Ramping?",
           "Contract Start", "Contract End"]
    )
    for col in ["ACV", "cACV", "ACV at Risk"] + exp_signal_labels:
        tbl[col] = tbl[col].apply(fmt_m)
    tbl["Cons Rate"] = tbl["Cons Rate"].apply(
        lambda v: f"{v:.2f}" if pd.notna(v) else "—"
    )

    color_map = {
        "Expansion": "#d1fae5", "Healthy": "#dbeafe", "At Risk": "#fef3c7",
        "Shelfware": "#ffedd5", "Inactive": "#fee2e2", "Ramping": "#ede9fe",
    }
    styled = tbl.style.map(lambda v: f"background-color: {color_map.get(v, '')}", subset=["Health"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.title("Prisma Cloud · cACV Executive Dashboard")
    st.caption("Consumed Annual Contract Value — North Star Metric for the Hybrid Consumption Model")

    if _is_demo():
        st.info(
            "📊 **Demo mode** — displaying a cached snapshot of pipeline output. "
            "All filters, charts, and tables are fully interactive. "
            "Connect GCP credentials locally for live BigQuery data.",
            icon=None,
        )

    available_dates = load_available_dates()
    initial_date    = available_dates[0] if available_dates else "2026-06-01"
    rep_df_full     = load_rep_rollup(initial_date)

    if rep_df_full.empty:
        st.warning("No data found in snapshot. Run `python3 pipeline_and_tests/run_pipeline.py` to rebuild.")
        st.stop()

    as_of_date, region, rep_name, employee_id = render_sidebar(rep_df_full)

    rep_df      = load_rep_rollup(as_of_date)
    rep_df_view = rep_df.copy()
    if region != "All":
        rep_df_view = rep_df_view[rep_df_view["region"] == region]
    if employee_id:
        rep_df_view = rep_df_view[rep_df_view["employee_id"] == employee_id]

    acct_df = load_accounts(as_of_date, region, employee_id)

    tab_overview, tab_region, tab_reps, tab_accounts = st.tabs([
        "📊 Overview", "🗺️ By Region", "👤 By Rep", "🏢 Accounts"
    ])

    with tab_overview:
        page_overview(rep_df_view, acct_df, region)
    with tab_region:
        page_region(rep_df)
    with tab_reps:
        page_reps(rep_df_view, region)
    with tab_accounts:
        page_accounts(acct_df, rep_name)


if __name__ == "__main__":
    main()
