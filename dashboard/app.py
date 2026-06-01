"""
cACV Executive Dashboard
Prisma Cloud · Consumed ACV North Star Metric

Data loading: tries BigQuery first (local dev with GCP credentials),
falls back automatically to committed CSV snapshots (Streamlit Cloud / demo).

Run locally:
    streamlit run dashboard/app.py

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

TIER_ORDER = ["Expansion", "Healthy", "At Risk", "Shelfware", "Inactive", "Ramping"]

# Shared Plotly layout applied to every chart
CHART_THEME = dict(
    font=dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
              color="#374151", size=12),
    plot_bgcolor="white",
    paper_bgcolor="white",
    margin=dict(t=24, b=40, l=8, r=8),
    hoverlabel=dict(bgcolor="white", bordercolor="#e2e8f0",
                    font_size=13,
                    font_family="Inter, -apple-system, sans-serif"),
    xaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0",
               tickfont=dict(size=11, color="#6b7280"), zeroline=False),
    yaxis=dict(gridcolor="#f1f5f9", linecolor="#e2e8f0",
               tickfont=dict(size=11, color="#6b7280"), zeroline=False),
    legend=dict(font=dict(size=11, color="#6b7280")),
)

st.set_page_config(
    page_title="cACV Dashboard · Prisma Cloud",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# CSS injection
# ─────────────────────────────────────────────────────────────────────────────

def inject_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ── Global typography ── */
    html, body, [class*="css"], button, input, select, textarea {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* ── Hide Streamlit chrome ── */
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }

    /* ── Page container ── */
    .main .block-container {
        padding: 1.75rem 2.25rem 3rem;
        max-width: 1440px;
    }

    /* ── Dark sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: none;
    }
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown small,
    [data-testid="stSidebar"] caption {
        color: #94a3b8 !important;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        color: #f1f5f9 !important;
    }
    [data-testid="stSidebar"] label {
        color: #94a3b8 !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background-color: #1e293b !important;
        border-color: #334155 !important;
        color: #e2e8f0 !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: #1e293b !important;
    }

    /* ── KPI cards ── */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 4px solid var(--accent-color, #3b82f6);
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
        height: 100%;
        min-height: 100px;
    }
    .kpi-label {
        font-size: 0.68rem;
        font-weight: 600;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: #94a3b8;
        margin-bottom: 0.55rem;
    }
    .kpi-value {
        font-size: 1.65rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.1;
        margin-bottom: 0.35rem;
        letter-spacing: -0.02em;
    }
    .kpi-sub {
        font-size: 0.75rem;
        font-weight: 500;
        color: #64748b;
    }
    .kpi-sub.neg { color: #ef4444; }
    .kpi-sub.pos { color: #10b981; }

    /* ── Page header ── */
    .page-header {
        padding-bottom: 1.25rem;
        margin-bottom: 0.5rem;
        border-bottom: 1px solid #f1f5f9;
    }
    .page-eyebrow {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #3b82f6;
        margin-bottom: 0.3rem;
    }
    .page-title {
        font-size: 1.6rem;
        font-weight: 700;
        color: #0f172a;
        letter-spacing: -0.03em;
        line-height: 1.2;
    }
    .page-sub {
        font-size: 0.82rem;
        color: #94a3b8;
        margin-top: 0.3rem;
        font-weight: 400;
    }

    /* ── Section headers ── */
    .section-header {
        font-size: 0.875rem;
        font-weight: 600;
        color: #0f172a;
        margin-bottom: 0.75rem;
        letter-spacing: -0.01em;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        background: #f8fafc;
        border-radius: 10px;
        padding: 4px;
        gap: 2px;
        border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-size: 0.875rem;
        font-weight: 500;
        color: #64748b !important;
        padding: 8px 20px !important;
        border: none !important;
        background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background: white !important;
        color: #0f172a !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 1.5rem;
    }

    /* ── Dividers ── */
    hr {
        border: none;
        border-top: 1px solid #f1f5f9;
        margin: 1.5rem 0;
    }

    /* ── Tables ── */
    [data-testid="stDataFrame"] {
        border-radius: 10px !important;
        overflow: hidden;
        border: 1px solid #e2e8f0 !important;
    }

    /* ── Info / alert boxes ── */
    [data-testid="stAlertContainer"] {
        border-radius: 10px !important;
    }

    /* ── Selectbox (main area) ── */
    [data-baseweb="select"] > div {
        border-radius: 8px !important;
        border-color: #e2e8f0 !important;
    }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery client — optional; gracefully absent in demo mode
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def _get_bq_client():
    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=GCP_PROJECT)
        client.query("SELECT 1").result()
        return client
    except Exception:
        return None


def _bq():
    return _get_bq_client()


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
        DS  = f"`{GCP_PROJECT}.gtm`"
        sql = f"SELECT * FROM {DS}.cacv_rep_rollup WHERE DATE(as_of_date) = DATE '{as_of_date}'"
        df  = client.query(sql).to_dataframe()
        if not df.empty:
            return df
        return client.query(
            f"SELECT * FROM {DS}.cacv_rep_rollup ORDER BY calculated_at DESC LIMIT 1000"
        ).to_dataframe()
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
                FROM {DS}.cacv_rep_rollup ORDER BY 1 DESC LIMIT 30
            """).to_dataframe()
            return [str(d) for d in df["d"].tolist()]
        except Exception:
            pass
    df = pd.read_csv(DEMO_DATA_DIR / "rep_rollup.csv")
    return sorted(df["as_of_date"].astype(str).unique(), reverse=True)[:30]


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


def attainment_color(rate: float) -> str:
    if rate >= 0.85:
        return "#10b981"
    if rate >= 0.70:
        return "#f59e0b"
    return "#ef4444"


# ─────────────────────────────────────────────────────────────────────────────
# KPI card component
# ─────────────────────────────────────────────────────────────────────────────

def kpi_card(label: str, value: str, sub: str = "",
             sub_cls: str = "", accent: str = "#3b82f6",
             help_text: str = "") -> str:
    sub_html = f'<div class="kpi-sub {sub_cls}">{sub}</div>' if sub else ""
    title_attr = f'title="{help_text}"' if help_text else ""
    return f"""
    <div class="kpi-card" style="--accent-color:{accent};" {title_attr}>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(rep_df: pd.DataFrame):
    st.sidebar.markdown(
        '<p style="color:#f1f5f9;font-size:1rem;font-weight:700;'
        'letter-spacing:-0.01em;margin-bottom:0.1rem;">Prisma Cloud</p>'
        '<p style="color:#475569;font-size:0.7rem;font-weight:500;'
        'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:1.5rem;">'
        'cACV Dashboard</p>',
        unsafe_allow_html=True,
    )

    available_dates = load_available_dates()
    as_of_date = st.sidebar.selectbox(
        "As-of Date", options=available_dates, index=0,
        help="Pipeline snapshot date",
    )

    regions    = ["All"] + sorted(rep_df["region"].dropna().unique().tolist())
    region     = st.sidebar.selectbox("Region", regions)
    rep_pool   = rep_df if region == "All" else rep_df[rep_df["region"] == region]
    rep_opts   = ["All"] + sorted(rep_pool["rep_name"].dropna().unique().tolist())
    rep_name   = st.sidebar.selectbox("Sales Rep", rep_opts)

    employee_id = None
    if rep_name != "All":
        row = rep_pool[rep_pool["rep_name"] == rep_name]
        employee_id = row["employee_id"].iloc[0] if not row.empty else None

    st.sidebar.markdown("<hr>", unsafe_allow_html=True)
    if _is_demo():
        st.sidebar.markdown(
            '<p style="color:#475569;font-size:0.72rem;">📊 Demo mode · cached snapshot<br>'
            'Connect BigQuery for live data</p>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<p style="color:#475569;font-size:0.72rem;">'
            f'Project: {GCP_PROJECT}<br>'
            f'Datasets: raw · staging · gtm</p>',
            unsafe_allow_html=True,
        )

    return as_of_date, region, rep_name, employee_id


# ─────────────────────────────────────────────────────────────────────────────
# Page: Overview
# ─────────────────────────────────────────────────────────────────────────────

def page_overview(rep_df: pd.DataFrame, acct_df: pd.DataFrame):
    total_acv        = rep_df["total_acv"].sum()
    total_cacv       = rep_df["total_cacv"].sum()
    total_risk       = rep_df["total_acv_at_risk"].sum()
    att_rate         = total_cacv / total_acv if total_acv else 0
    expansion_signal = (
        rep_df["total_expansion_signal_acv"].sum()
        if "total_expansion_signal_acv" in rep_df.columns else 0
    )

    # KPI cards
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(kpi_card("Total ACV",       fmt_m(total_acv),   accent="#64748b"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Total cACV",      fmt_m(total_cacv),  accent="#3b82f6"), unsafe_allow_html=True)
    c3.markdown(kpi_card(
        "cACV Attainment", fmt_pct(att_rate),
        sub=("Above target" if att_rate >= 0.85 else
             "Below 85% target" if att_rate >= 0.70 else "Needs attention"),
        sub_cls=("pos" if att_rate >= 0.85 else "neg" if att_rate < 0.70 else ""),
        accent=attainment_color(att_rate),
    ), unsafe_allow_html=True)
    c4.markdown(kpi_card(
        "ACV at Risk", fmt_m(total_risk),
        sub=f"{total_risk/total_acv:.1%} of portfolio" if total_acv else "",
        sub_cls="neg", accent="#ef4444",
        help_text="Committed ACV not backed by consumption",
    ), unsafe_allow_html=True)
    c5.markdown(kpi_card(
        "Expansion Signal", fmt_m(expansion_signal),
        sub="Over-commit pipeline" if expansion_signal > 0 else "No signal",
        sub_cls="pos" if expansion_signal > 0 else "",
        accent="#10b981",
        help_text="Consumption above committed ACV — upsell indicator",
    ), unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-header">cACV by Region</div>', unsafe_allow_html=True)
        rdf = (
            rep_df.groupby("region", as_index=False)
            .agg(total_acv=("total_acv", "sum"), total_cacv=("total_cacv", "sum"))
        )
        rdf["attainment"] = rdf["total_cacv"] / rdf["total_acv"]
        rdf = rdf.sort_values("total_cacv", ascending=False)

        fig = go.Figure()
        fig.add_bar(
            x=rdf["region"], y=rdf["total_acv"], name="ACV",
            marker_color="#f1f5f9",
            text=[fmt_m(v) for v in rdf["total_acv"]],
            textposition="outside",
            textfont=dict(size=11, color="#94a3b8"),
        )
        fig.add_bar(
            x=rdf["region"], y=rdf["total_cacv"], name="cACV",
            marker_color="#3b82f6",
            text=[f"{fmt_m(v)}  ·  {fmt_pct(r)}"
                  for v, r in zip(rdf["total_cacv"], rdf["attainment"])],
            textposition="inside", textfont=dict(color="white", size=11),
        )
        fig.update_layout(
            **CHART_THEME,
            barmode="overlay",
            legend=dict(orientation="h", y=-0.18, font=dict(size=11, color="#6b7280")),
            yaxis=dict(**CHART_THEME["yaxis"], tickprefix="$", tickformat=","),
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-header">Account Health Mix</div>', unsafe_allow_html=True)
        hc = acct_df["health_tier"].value_counts().reset_index()
        hc.columns = ["health_tier", "count"]
        total_accts = hc["count"].sum()

        fig2 = px.pie(
            hc, names="health_tier", values="count",
            color="health_tier", color_discrete_map=HEALTH_COLORS, hole=0.62,
        )
        fig2.update_traces(
            textposition="outside", textinfo="label+percent",
            textfont=dict(size=11),
            marker=dict(line=dict(color="white", width=2)),
        )
        fig2.add_annotation(
            text=f"<b>{total_accts}</b><br><span style='font-size:11px;color:#94a3b8'>accounts</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(size=20, color="#0f172a"),
            xref="paper", yref="paper", align="center",
        )
        fig2.update_layout(
            **{k: v for k, v in CHART_THEME.items() if k not in ("xaxis", "yaxis")},
            showlegend=False,
            margin=dict(t=20, b=20, l=20, r=20),
            height=320,
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<div class="section-header">cACV Attainment vs. ACV — by Rep</div>', unsafe_allow_html=True)
    sdf = rep_df.copy()
    sdf["attainment_pct"] = sdf["cacv_attainment_rate"].fillna(0) * 100
    sdf["bubble_size"]    = (sdf["total_acv"] / sdf["total_acv"].max() * 38).clip(lower=6)

    fig3 = px.scatter(
        sdf, x="total_acv", y="attainment_pct",
        size="bubble_size", color="region",
        color_discrete_sequence=["#3b82f6","#10b981","#f59e0b","#8b5cf6","#ef4444"],
        hover_name="rep_name",
        hover_data={
            "total_acv": ":.3s", "total_cacv": ":.3s",
            "attainment_pct": ":.1f", "total_accounts": True,
            "accounts_at_risk": True, "bubble_size": False,
        },
        labels={"total_acv": "Total ACV ($)", "attainment_pct": "cACV Attainment (%)", "region": "Region"},
        opacity=0.85,
        height=360,
    )
    fig3.add_hline(y=100, line_dash="dash", line_color="#94a3b8", line_width=1,
                   annotation_text="100%", annotation_font_color="#94a3b8", annotation_font_size=11)
    fig3.add_hline(y=85,  line_dash="dot",  line_color="#f59e0b", line_width=1,
                   annotation_text="85% target", annotation_font_color="#f59e0b", annotation_font_size=11)
    fig3.update_layout(
        **CHART_THEME,
        xaxis=dict(**CHART_THEME["xaxis"], tickprefix="$", tickformat=","),
        legend=dict(orientation="h", y=-0.18, font=dict(size=11, color="#6b7280")),
        margin=dict(t=10, b=48, l=8, r=8),
    )
    st.plotly_chart(fig3, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Region Breakdown
# ─────────────────────────────────────────────────────────────────────────────

def page_region(rep_df: pd.DataFrame):
    region_agg = (
        rep_df.groupby("region", as_index=False)
        .agg(
            reps=("employee_id", "count"),
            total_accounts=("total_accounts", "sum"),
            total_acv=("total_acv", "sum"),
            total_cacv=("total_cacv", "sum"),
            total_acv_at_risk=("total_acv_at_risk", "sum"),
            accounts_expansion=("accounts_expansion", "sum"),
            accounts_at_risk=("accounts_at_risk", "sum"),
            expansion_acv_pipeline=("expansion_acv_pipeline", "sum"),
        )
    )
    region_agg["att_rate"] = region_agg["total_cacv"] / region_agg["total_acv"]
    region_agg["risk_pct"] = region_agg["total_acv_at_risk"] / region_agg["total_acv"]
    region_agg = region_agg.sort_values("total_cacv", ascending=False)

    display = region_agg.copy()
    display["ACV"]              = display["total_acv"].apply(fmt_m)
    display["cACV"]             = display["total_cacv"].apply(fmt_m)
    display["Attainment"]       = display["att_rate"].apply(fmt_pct)
    display["ACV at Risk"]      = display["total_acv_at_risk"].apply(fmt_m)
    display["Risk %"]           = display["risk_pct"].apply(fmt_pct)
    display["Expansion Pipeline"] = display["expansion_acv_pipeline"].apply(fmt_m)
    st.dataframe(
        display[["region", "reps", "total_accounts", "ACV", "cACV", "Attainment",
                 "ACV at Risk", "Risk %", "accounts_expansion", "accounts_at_risk",
                 "Expansion Pipeline"]].rename(columns={
                     "region": "Region", "reps": "Reps",
                     "total_accounts": "Accounts",
                     "accounts_expansion": "Expansion Accts",
                     "accounts_at_risk": "At-Risk Accts",
                 }),
        use_container_width=True, hide_index=True,
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Health Tier Mix by Region</div>', unsafe_allow_html=True)

    tier_cols = ["accounts_expansion", "accounts_healthy", "accounts_at_risk",
                 "accounts_shelfware", "accounts_inactive", "accounts_ramping"]
    rh     = rep_df.groupby("region", as_index=False)[tier_cols].sum()
    totals = rh[tier_cols].sum(axis=1)
    rh_pct = rh.copy()
    for col in tier_cols:
        rh_pct[col] = rh[col] / totals * 100

    fig = go.Figure()
    for col, label in zip(tier_cols, TIER_ORDER):
        fig.add_bar(
            name=label, x=rh_pct["region"], y=rh_pct[col],
            marker_color=HEALTH_COLORS[label],
            text=rh_pct[col].apply(lambda v: f"{v:.0f}%" if v >= 5 else ""),
            textposition="inside", textfont=dict(color="white", size=11),
        )
    fig.update_layout(
        **CHART_THEME,
        barmode="stack",
        yaxis=dict(**CHART_THEME["yaxis"], title="% of accounts", ticksuffix="%"),
        legend=dict(orientation="h", y=-0.18, font=dict(size=11, color="#6b7280")),
        height=340,
    )
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page: Rep Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

def page_reps(rep_df: pd.DataFrame):
    filtered = rep_df.sort_values("total_cacv", ascending=False).reset_index(drop=True)

    if not filtered.empty:
        top = filtered.iloc[0]
        bot = filtered.iloc[-1]
        c1, c2 = st.columns(2)
        with c1:
            st.success(
                f"**#{int(top['org_rank'])} {top['rep_name']}** · {top['region']}  \n"
                f"cACV **{fmt_m(top['total_cacv'])}** · Attainment **{fmt_pct(top['cacv_attainment_rate'])}**"
            )
        with c2:
            att  = bot["cacv_attainment_rate"]
            body = (
                f"**{bot['rep_name']}** · {bot['region']}  \n"
                f"cACV **{fmt_m(bot['total_cacv'])}** · Attainment **{fmt_pct(att)}**"
            )
            if pd.notna(att) and att < 0.6:
                st.error(body)
            else:
                st.info(body)

    st.markdown("<br>", unsafe_allow_html=True)

    chart_df = filtered.nlargest(20, "total_cacv")
    fig = go.Figure()
    fig.add_bar(
        y=chart_df["rep_name"], x=chart_df["total_acv"], name="ACV",
        orientation="h", marker_color="#f1f5f9",
        marker_line=dict(color="#e2e8f0", width=1),
    )
    fig.add_bar(
        y=chart_df["rep_name"], x=chart_df["total_cacv"], name="cACV",
        orientation="h", marker_color="#3b82f6",
        text=[f"{fmt_m(v)}  ·  {fmt_pct(r)}"
              for v, r in zip(chart_df["total_cacv"], chart_df["cacv_attainment_rate"])],
        textposition="inside", textfont=dict(color="white", size=11),
    )
    fig.update_layout(
        **CHART_THEME,
        barmode="overlay",
        xaxis=dict(**CHART_THEME["xaxis"], tickprefix="$", tickformat=","),
        legend=dict(orientation="h", y=-0.06, font=dict(size=11, color="#6b7280")),
        margin=dict(t=10, b=48, l=160, r=8),
        height=max(320, len(chart_df) * 30),
        yaxis=dict(**CHART_THEME["yaxis"], autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-header">Full Rep Table</div>', unsafe_allow_html=True)
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
    if acct_df.empty:
        st.info("No accounts match the current filter.")
        return

    tiers    = ["All"] + [t for t in TIER_ORDER if t in acct_df["health_tier"].unique()]
    sel_tier = st.selectbox("Filter by health tier", tiers, key="acct_tier_filter")
    view     = acct_df if sel_tier == "All" else acct_df[acct_df["health_tier"] == sel_tier]

    fig = px.scatter(
        view.dropna(subset=["trailing_90d_avg_rate"]),
        x="annual_commit_dollars",
        y="trailing_90d_avg_rate",
        color="health_tier",
        color_discrete_map=HEALTH_COLORS,
        size="annual_commit_dollars",
        size_max=20,
        hover_name="company_name",
        hover_data={
            "annual_commit_dollars": ":.3s",
            "trailing_90d_avg_rate": ":.2f",
            "cacv": ":.3s",
            "rep_name": True,
            "health_tier": True,
        },
        labels={
            "annual_commit_dollars": "ACV ($)",
            "trailing_90d_avg_rate": "Consumption Rate (90-day avg)",
        },
        opacity=0.80,
        height=380,
    )
    fig.add_hline(y=1.0,  line_dash="dash", line_color="#94a3b8", line_width=1,
                  annotation_text="100% commit", annotation_font_color="#94a3b8",
                  annotation_font_size=11)
    fig.add_hline(y=0.80, line_dash="dot",  line_color="#f59e0b", line_width=1,
                  annotation_text="80% floor", annotation_font_color="#f59e0b",
                  annotation_font_size=11)
    fig.update_layout(
        **CHART_THEME,
        xaxis=dict(**CHART_THEME["xaxis"], tickprefix="$", tickformat=","),
        legend=dict(orientation="h", y=-0.2, font=dict(size=11, color="#6b7280")),
        margin=dict(t=10, b=56, l=8, r=8),
    )
    st.plotly_chart(fig, use_container_width=True)

    exp_cols   = ["expansion_signal_acv"] if "expansion_signal_acv" in view.columns else []
    exp_labels = ["Exp Signal"] if exp_cols else []
    tbl = view[[
        "company_name", "rep_name", "region", "health_tier",
        "annual_commit_dollars", "trailing_90d_avg_rate", "cacv",
    ] + exp_cols + [
        "acv_at_risk", "months_of_data",
        "expansion_flag", "is_spike_drop", "is_new_account",
        "contract_start_date", "contract_end_date",
    ]].copy()
    tbl.columns = (
        ["Account", "Rep", "Region", "Health",
         "ACV", "Cons Rate", "cACV"]
        + exp_labels
        + ["ACV at Risk", "Months",
           "Expansion?", "Spike/Drop?", "Ramping?",
           "Start", "End"]
    )
    for col in ["ACV", "cACV", "ACV at Risk"] + exp_labels:
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
    inject_css()

    # Page header
    st.markdown("""
    <div class="page-header">
        <div class="page-eyebrow">Prisma Cloud</div>
        <div class="page-title">cACV Executive Dashboard</div>
        <div class="page-sub">Consumed Annual Contract Value · North Star Metric for the Hybrid Consumption Model</div>
    </div>
    """, unsafe_allow_html=True)

    if _is_demo():
        st.info(
            "**Demo mode** — showing a cached pipeline snapshot. "
            "All filters, charts, and tables are fully interactive. "
            "Run locally with GCP credentials for live BigQuery data."
        )

    available_dates = load_available_dates()
    initial_date    = available_dates[0] if available_dates else "2026-06-01"
    rep_df_full     = load_rep_rollup(initial_date)

    if rep_df_full.empty:
        st.warning("No data found. Run `python3 pipeline_and_tests/run_pipeline.py` to populate the tables.")
        st.stop()

    as_of_date, region, rep_name, employee_id = render_sidebar(rep_df_full)

    rep_df      = load_rep_rollup(as_of_date)
    rep_df_view = rep_df.copy()
    if region != "All":
        rep_df_view = rep_df_view[rep_df_view["region"] == region]
    if employee_id:
        rep_df_view = rep_df_view[rep_df_view["employee_id"] == employee_id]

    acct_df = load_accounts(as_of_date, region, employee_id)

    tab_ov, tab_rgn, tab_rep, tab_acct = st.tabs([
        "📊  Overview", "🗺  By Region", "👤  By Rep", "🏢  Accounts"
    ])

    with tab_ov:
        page_overview(rep_df_view, acct_df)
    with tab_rgn:
        page_region(rep_df)
    with tab_rep:
        page_reps(rep_df_view)
    with tab_acct:
        page_accounts(acct_df, rep_name)


if __name__ == "__main__":
    main()
