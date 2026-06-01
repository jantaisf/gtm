"""
cACV Executive Dashboard
Prisma Cloud · Consumed ACV North Star Metric

Six tabs, one per audience from product_spec.md §11:
  1. Portfolio Overview     — VP of Sales, CFO
  2. By Region              — Regional VPs, Sales Ops
  3. By Rep                 — Sales Managers
  4. Renewal Risk           — CFO, CS Leadership
  5. Expansion & Activation — AEs, Sales Managers
  6. Account Detail         — CS Leads, AEs

Data loading: BigQuery-first, falls back to CSV snapshots for demo / Streamlit Cloud.
"""

from datetime import date, timedelta
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

def _chart(*, exclude: tuple = (), **overrides) -> dict:
    """Merge CHART_THEME with per-chart overrides without duplicate keyword errors.

    Nested dicts (xaxis, yaxis, legend, margin, hoverlabel) are shallow-merged so
    per-chart additions extend the theme rather than replace it wholesale.
    Keys listed in `exclude` are dropped entirely (e.g. exclude=("xaxis","yaxis")
    for pie/donut charts that have no axes).
    """
    layout = {k: v for k, v in CHART_THEME.items() if k not in exclude}
    for key, val in overrides.items():
        if key in layout and isinstance(layout[key], dict) and isinstance(val, dict):
            layout[key] = {**layout[key], **val}
        else:
            layout[key] = val
    return layout


st.set_page_config(
    page_title="cACV Dashboard · Prisma Cloud",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

def inject_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"], button, input, select, textarea {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }

    .main .block-container { padding: 1.75rem 2.25rem 3rem; max-width: 1440px; }

    /* Dark sidebar */
    [data-testid="stSidebar"] { background-color: #0f172a !important; border-right: none; }
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown small { color: #94a3b8 !important; }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 { color: #f1f5f9 !important; }
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
    [data-testid="stSidebar"] hr { border-color: #1e293b !important; }

    /* KPI cards */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 4px solid var(--accent-color, #3b82f6);
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        height: 100%;
        min-height: 100px;
    }
    .kpi-label {
        font-size: 0.68rem; font-weight: 600; letter-spacing: 0.07em;
        text-transform: uppercase; color: #94a3b8; margin-bottom: 0.55rem;
    }
    .kpi-value {
        font-size: 1.65rem; font-weight: 700; color: #0f172a;
        line-height: 1.1; margin-bottom: 0.35rem; letter-spacing: -0.02em;
    }
    .kpi-sub { font-size: 0.75rem; font-weight: 500; color: #64748b; }
    .kpi-sub.neg { color: #ef4444; }
    .kpi-sub.pos { color: #10b981; }

    /* Page header */
    .page-header { padding-bottom: 1.25rem; margin-bottom: 0.5rem; border-bottom: 1px solid #f1f5f9; }
    .page-eyebrow { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.1em;
                    text-transform: uppercase; color: #3b82f6; margin-bottom: 0.3rem; }
    .page-title { font-size: 1.6rem; font-weight: 700; color: #0f172a;
                  letter-spacing: -0.03em; line-height: 1.2; }
    .page-sub { font-size: 0.82rem; color: #94a3b8; margin-top: 0.3rem; }

    /* Persona callout */
    .persona-callout {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #3b82f6;
        border-radius: 10px;
        padding: 0.85rem 1.2rem;
        margin-bottom: 1.4rem;
    }
    .persona-label {
        font-size: 0.68rem; font-weight: 600; letter-spacing: 0.07em;
        text-transform: uppercase; color: #94a3b8; margin-bottom: 0.25rem;
    }
    .persona-audience { font-size: 0.875rem; font-weight: 600; color: #0f172a; margin-bottom: 0.2rem; }
    .persona-question { font-size: 0.8rem; color: #64748b; }

    /* Section headers */
    .section-header {
        font-size: 0.875rem; font-weight: 600; color: #0f172a;
        margin-bottom: 0.75rem; letter-spacing: -0.01em;
    }

    /* Pill tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #f8fafc; border-radius: 10px; padding: 4px; gap: 2px; border-bottom: none !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px; font-size: 0.875rem; font-weight: 500;
        color: #64748b !important; padding: 8px 20px !important;
        border: none !important; background: transparent !important;
    }
    .stTabs [aria-selected="true"] {
        background: white !important; color: #0f172a !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
    }
    .stTabs [data-baseweb="tab-panel"] { padding-top: 1.5rem; }

    hr { border: none; border-top: 1px solid #f1f5f9; margin: 1.5rem 0; }
    [data-testid="stDataFrame"] { border-radius: 10px !important; border: 1px solid #e2e8f0 !important; }
    [data-testid="stAlertContainer"] { border-radius: 10px !important; }
    [data-baseweb="select"] > div { border-radius: 8px !important; border-color: #e2e8f0 !important; }
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery — optional
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

def _bq(): return _get_bq_client()

@st.cache_resource
def _is_demo() -> bool: return _bq() is None


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
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
        return client.query(f"SELECT * FROM {DS}.cacv_rep_rollup ORDER BY calculated_at DESC LIMIT 1000").to_dataframe()
    df = pd.read_csv(DEMO_DATA_DIR / "rep_rollup.csv")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
    match = df[df["as_of_date"].astype(str) == as_of_date]
    return match if not match.empty else df


@st.cache_data(ttl=300, show_spinner="Loading account detail…")
def load_accounts(as_of_date: str, region: Optional[str] = None, employee_id: Optional[str] = None) -> pd.DataFrame:
    client = _bq()
    if client is not None:
        DS = f"`{GCP_PROJECT}.gtm`"; DS_RAW = f"`{GCP_PROJECT}.raw`"
        sql = f"""
        SELECT ca.*, sr.name AS rep_name, sr.region, sr.segment
        FROM {DS}.cacv_account ca
        JOIN {DS_RAW}.sales_reps sr ON sr.employee_id = ca.employee_id
        WHERE DATE(ca.as_of_date) = DATE '{as_of_date}'
        """
        if region and region != "All": sql += f"\n    AND sr.region = '{region}'"
        if employee_id and employee_id != "All": sql += f"\n    AND ca.employee_id = '{employee_id}'"
        try:
            return client.query(sql).to_dataframe()
        except Exception:
            df = client.query(f"""
                SELECT ca.*, sr.name AS rep_name, sr.region, sr.segment
                FROM {DS}.cacv_account ca
                JOIN {DS_RAW}.sales_reps sr ON sr.employee_id = ca.employee_id
            """).to_dataframe()
            if region and region != "All": df = df[df["region"] == region]
            if employee_id and employee_id != "All": df = df[df["employee_id"] == employee_id]
            return df
    df = pd.read_csv(DEMO_DATA_DIR / "accounts.csv")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.date
    match = df[df["as_of_date"].astype(str) == as_of_date]
    df = match if not match.empty else df
    if region and region != "All": df = df[df["region"] == region]
    if employee_id and employee_id != "All": df = df[df["employee_id"] == employee_id]
    return df


@st.cache_data(ttl=600, show_spinner=False)
def load_available_dates() -> list:
    client = _bq()
    if client is not None:
        DS = f"`{GCP_PROJECT}.gtm`"
        try:
            df = client.query(f"SELECT DISTINCT DATE(as_of_date) AS d FROM {DS}.cacv_rep_rollup ORDER BY 1 DESC LIMIT 30").to_dataframe()
            return [str(d) for d in df["d"].tolist()]
        except Exception:
            pass
    df = pd.read_csv(DEMO_DATA_DIR / "rep_rollup.csv")
    return sorted(df["as_of_date"].astype(str).unique(), reverse=True)[:30]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_m(v) -> str:
    if pd.isna(v): return "—"
    if abs(v) >= 1_000_000: return f"${v/1_000_000:.1f}M"
    if abs(v) >= 1_000: return f"${v/1_000:.0f}K"
    return f"${v:.0f}"

def fmt_pct(v) -> str:
    return "—" if pd.isna(v) else f"{v:.1%}"

def attainment_color(rate: float) -> str:
    return "#10b981" if rate >= 0.85 else ("#f59e0b" if rate >= 0.70 else "#ef4444")

def kpi_card(label: str, value: str, sub: str = "", sub_cls: str = "",
             accent: str = "#3b82f6", help_text: str = "") -> str:
    sub_html  = f'<div class="kpi-sub {sub_cls}">{sub}</div>' if sub else ""
    title_attr = f'title="{help_text}"' if help_text else ""
    return (f'<div class="kpi-card" style="--accent-color:{accent};" {title_attr}>'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'{sub_html}</div>')

def persona_callout(audience: str, questions: list[str], accent: str = "#3b82f6") -> None:
    qs_html = "".join(f"<li>{q}</li>" for q in questions)
    st.markdown(
        f'<div class="persona-callout" style="border-left-color:{accent};">'
        f'<div class="persona-label">Audience</div>'
        f'<div class="persona-audience">{audience}</div>'
        f'<div class="persona-question"><ul style="margin:0.3rem 0 0 1rem;padding:0;">{qs_html}</ul></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(rep_df: pd.DataFrame):
    st.sidebar.markdown(
        '<p style="color:#f1f5f9;font-size:1rem;font-weight:700;letter-spacing:-0.01em;margin-bottom:0.1rem;">Prisma Cloud</p>'
        '<p style="color:#475569;font-size:0.7rem;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:1.5rem;">cACV Dashboard</p>',
        unsafe_allow_html=True,
    )
    available_dates = load_available_dates()
    as_of_date = st.sidebar.selectbox("As-of Date", options=available_dates, index=0, help="Pipeline snapshot date")
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
        st.sidebar.markdown('<p style="color:#475569;font-size:0.72rem;">📊 Demo mode · cached snapshot<br>Connect BigQuery for live data</p>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f'<p style="color:#475569;font-size:0.72rem;">Project: {GCP_PROJECT}<br>Datasets: raw · staging · gtm</p>', unsafe_allow_html=True)
    return as_of_date, region, rep_name, employee_id


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1: Portfolio Overview  —  VP of Sales · CFO
# ─────────────────────────────────────────────────────────────────────────────

def page_overview(rep_df: pd.DataFrame, acct_df: pd.DataFrame):
    persona_callout(
        "VP of Sales · CFO",
        [
            "How much of our booked ACV is actually being consumed?",
            "What is our total churn exposure right now, in dollars?",
            "Which regions are healthy and which are lagging?",
            "What does our cACV attainment tell us about next renewal cycle NRR?",
        ],
    )

    total_acv        = rep_df["total_acv"].sum()
    total_cacv       = rep_df["total_cacv"].sum()
    total_risk       = rep_df["total_acv_at_risk"].sum()
    att_rate         = total_cacv / total_acv if total_acv else 0
    expansion_signal = rep_df["total_expansion_signal_acv"].sum() if "total_expansion_signal_acv" in rep_df.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(kpi_card("Total ACV",       fmt_m(total_acv),  accent="#64748b"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Total cACV",      fmt_m(total_cacv), accent="#3b82f6"), unsafe_allow_html=True)
    c3.markdown(kpi_card(
        "cACV Attainment", fmt_pct(att_rate),
        sub=("Above target" if att_rate >= 0.85 else "Below 85% target" if att_rate >= 0.70 else "Needs attention"),
        sub_cls=("pos" if att_rate >= 0.85 else "neg"),
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
        sub="Over-commit pipeline" if expansion_signal > 0 else "No signal yet",
        sub_cls="pos" if expansion_signal > 0 else "",
        accent="#10b981",
        help_text="Consumption above committed ACV — upsell indicator",
    ), unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # NRR prediction
    st.markdown('<div class="section-header">NRR Forecast Signal</div>', unsafe_allow_html=True)
    nrr_rows = [
        ("≥ 90%",   "Strong renewal; likely expansion",         att_rate >= 0.90),
        ("70–90%",  "Renewal probable; flat or slight compression", 0.70 <= att_rate < 0.90),
        ("50–70%",  "Renewal at risk; CS intervention required",  0.50 <= att_rate < 0.70),
        ("< 50%",   "High churn probability; executive save plan", att_rate < 0.50),
    ]
    cols = st.columns(4)
    for col, (band, label, active) in zip(cols, nrr_rows):
        bg    = "#fef2f2" if active and att_rate < 0.50 else ("#fefce8" if active else "#f8fafc")
        bord  = "#ef4444" if active and att_rate < 0.50 else ("#f59e0b" if active else "#e2e8f0")
        bold  = "font-weight:700;" if active else ""
        current_tag = ('<div style="font-size:0.7rem;color:#ef4444;margin-top:0.5rem;font-weight:600;">'
                       '← current attainment</div>') if active else ""
        col.markdown(
            f'<div style="background:{bg};border:1px solid {bord};border-radius:10px;'
            f'padding:0.9rem 1rem;height:100%;">'
            f'<div style="font-size:1rem;{bold}color:#0f172a;">{band}</div>'
            f'<div style="font-size:0.78rem;color:#64748b;margin-top:0.3rem;">{label}</div>'
            f'{current_tag}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-header">cACV by Region</div>', unsafe_allow_html=True)
        rdf = rep_df.groupby("region", as_index=False).agg(
            total_acv=("total_acv","sum"), total_cacv=("total_cacv","sum"))
        rdf["attainment"] = rdf["total_cacv"] / rdf["total_acv"]
        rdf = rdf.sort_values("total_cacv", ascending=False)
        fig = go.Figure()
        fig.add_bar(x=rdf["region"], y=rdf["total_acv"], name="ACV",
                    marker_color="#f1f5f9",
                    text=[fmt_m(v) for v in rdf["total_acv"]], textposition="outside",
                    textfont=dict(size=11, color="#94a3b8"))
        fig.add_bar(x=rdf["region"], y=rdf["total_cacv"], name="cACV",
                    marker_color="#3b82f6",
                    text=[f"{fmt_m(v)}  ·  {fmt_pct(r)}" for v, r in zip(rdf["total_cacv"], rdf["attainment"])],
                    textposition="inside", textfont=dict(color="white", size=11))
        fig.update_layout(**_chart(
            barmode="overlay",
            legend=dict(orientation="h", y=-0.18),
            yaxis=dict(tickprefix="$", tickformat=","),
            height=300,
        ))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-header">Account Health Mix</div>', unsafe_allow_html=True)
        hc = acct_df["health_tier"].value_counts().reset_index()
        hc.columns = ["health_tier", "count"]
        total_accts = hc["count"].sum()
        fig2 = px.pie(hc, names="health_tier", values="count",
                      color="health_tier", color_discrete_map=HEALTH_COLORS, hole=0.62)
        fig2.update_traces(textposition="outside", textinfo="label+percent",
                           textfont=dict(size=11),
                           marker=dict(line=dict(color="white", width=2)))
        fig2.add_annotation(
            text=f"<b>{total_accts}</b><br><span style='font-size:11px;color:#94a3b8'>accounts</span>",
            x=0.5, y=0.5, showarrow=False, font=dict(size=20, color="#0f172a"),
            xref="paper", yref="paper", align="center")
        fig2.update_layout(**_chart(
            exclude=("xaxis", "yaxis"),
            showlegend=False, margin=dict(t=20, b=20, l=20, r=20), height=300,
        ))
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown('<div class="section-header">cACV Attainment vs. ACV — by Rep</div>', unsafe_allow_html=True)
    sdf = rep_df.copy()
    sdf["attainment_pct"] = sdf["cacv_attainment_rate"].fillna(0) * 100
    sdf["bubble_size"]    = (sdf["total_acv"] / sdf["total_acv"].max() * 38).clip(lower=6)
    fig3 = px.scatter(sdf, x="total_acv", y="attainment_pct", size="bubble_size", color="region",
                      color_discrete_sequence=["#3b82f6","#10b981","#f59e0b","#8b5cf6","#ef4444"],
                      hover_name="rep_name",
                      hover_data={"total_acv":":.3s","total_cacv":":.3s","attainment_pct":":.1f",
                                  "total_accounts":True,"accounts_at_risk":True,"bubble_size":False},
                      labels={"total_acv":"Total ACV ($)","attainment_pct":"cACV Attainment (%)","region":"Region"},
                      opacity=0.85, height=340)
    fig3.add_hline(y=100, line_dash="dash", line_color="#94a3b8", line_width=1,
                   annotation_text="100%", annotation_font_color="#94a3b8", annotation_font_size=11)
    fig3.add_hline(y=85, line_dash="dot", line_color="#f59e0b", line_width=1,
                   annotation_text="85% target", annotation_font_color="#f59e0b", annotation_font_size=11)
    fig3.update_layout(**_chart(
        xaxis=dict(tickprefix="$", tickformat=","),
        legend=dict(orientation="h", y=-0.18),
        margin=dict(t=10, b=48, l=8, r=8),
    ))
    st.plotly_chart(fig3, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2: By Region  —  Regional VPs · Sales Ops
# ─────────────────────────────────────────────────────────────────────────────

def page_region(rep_df: pd.DataFrame, acct_df: pd.DataFrame):
    persona_callout(
        "Regional VPs · Sales Ops",
        [
            "How does my region compare to others on cACV attainment?",
            "What percentage of my portfolio is at risk of churn?",
            "Which health tiers dominate my region — do I have a shelfware problem or an expansion opportunity?",
            "Where is the expansion pipeline concentrated?",
        ],
    )

    region_agg = rep_df.groupby("region", as_index=False).agg(
        reps=("employee_id","count"), total_accounts=("total_accounts","sum"),
        total_acv=("total_acv","sum"), total_cacv=("total_cacv","sum"),
        total_acv_at_risk=("total_acv_at_risk","sum"),
        accounts_expansion=("accounts_expansion","sum"),
        accounts_at_risk=("accounts_at_risk","sum"),
        expansion_acv_pipeline=("expansion_acv_pipeline","sum"),
        spike_drop_accounts=("spike_drop_accounts","sum"),
    )
    region_agg["att_rate"] = region_agg["total_cacv"] / region_agg["total_acv"]
    region_agg["risk_pct"] = region_agg["total_acv_at_risk"] / region_agg["total_acv"]
    region_agg = region_agg.sort_values("total_cacv", ascending=False)

    display = region_agg.copy()
    for col, src in [("ACV","total_acv"),("cACV","total_cacv"),
                     ("ACV at Risk","total_acv_at_risk"),("Exp Pipeline","expansion_acv_pipeline")]:
        display[col] = display[src].apply(fmt_m)
    display["Attainment"] = display["att_rate"].apply(fmt_pct)
    display["Risk %"]     = display["risk_pct"].apply(fmt_pct)
    st.dataframe(display[["region","reps","total_accounts","ACV","cACV","Attainment",
                           "ACV at Risk","Risk %","accounts_expansion","accounts_at_risk","Exp Pipeline"]]
                 .rename(columns={"region":"Region","reps":"Reps","total_accounts":"Accounts",
                                  "accounts_expansion":"Expansion Accts","accounts_at_risk":"At-Risk Accts"}),
                 use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-header">Health Tier Mix by Region</div>', unsafe_allow_html=True)
        tier_cols = ["accounts_expansion","accounts_healthy","accounts_at_risk",
                     "accounts_shelfware","accounts_inactive","accounts_ramping"]
        rh = rep_df.groupby("region", as_index=False)[tier_cols].sum()
        totals = rh[tier_cols].sum(axis=1)
        rh_pct = rh.copy()
        for col in tier_cols: rh_pct[col] = rh[col] / totals * 100
        fig = go.Figure()
        for col, label in zip(tier_cols, TIER_ORDER):
            fig.add_bar(name=label, x=rh_pct["region"], y=rh_pct[col],
                        marker_color=HEALTH_COLORS[label],
                        text=rh_pct[col].apply(lambda v: f"{v:.0f}%" if v >= 5 else ""),
                        textposition="inside", textfont=dict(color="white", size=11))
        fig.update_layout(**_chart(
            barmode="stack",
            yaxis=dict(title="% of accounts", ticksuffix="%"),
            legend=dict(orientation="h", y=-0.22),
            height=340,
        ))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-header">Expansion Pipeline by Region</div>', unsafe_allow_html=True)
        # Accounts with expansion_flag by region
        exp_by_region = (acct_df[acct_df["expansion_flag"] == True]
                         .groupby("region", as_index=False)
                         .agg(exp_accounts=("account_id","count"),
                              exp_signal_acv=("expansion_signal_acv","sum"),
                              avg_rate=("trailing_90d_avg_rate","mean")))
        if exp_by_region.empty:
            st.info("No expansion-flagged accounts in the current filter. Accounts enter this view once they sustain >120% consumption for 2+ consecutive months.")
        else:
            fig_e = px.bar(exp_by_region.sort_values("exp_signal_acv", ascending=False),
                           x="region", y="exp_signal_acv", color="region",
                           color_discrete_sequence=["#10b981","#3b82f6","#f59e0b","#8b5cf6","#ef4444"],
                           text=exp_by_region.sort_values("exp_signal_acv", ascending=False)["exp_signal_acv"].apply(fmt_m),
                           labels={"region":"Region","exp_signal_acv":"Expansion Signal ACV ($)"},
                           height=340)
            fig_e.update_traces(textposition="outside")
            fig_e.update_layout(**_chart(
                yaxis=dict(tickprefix="$", tickformat=","),
                showlegend=False,
            ))
            st.plotly_chart(fig_e, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3: By Rep  —  Sales Managers
# ─────────────────────────────────────────────────────────────────────────────

def page_reps(rep_df: pd.DataFrame):
    persona_callout(
        "Sales Managers",
        [
            "Who are my top performers this quarter?",
            "Which rep has the most ACV at risk and needs coaching now?",
            "How does each rep's book of business break down by health tier?",
            "Who has expansion opportunities they should be working?",
        ],
    )

    filtered = rep_df.sort_values("total_cacv", ascending=False).reset_index(drop=True)
    if not filtered.empty:
        top = filtered.iloc[0]; bot = filtered.iloc[-1]
        c1, c2 = st.columns(2)
        with c1:
            st.success(f"**#{int(top['org_rank'])} {top['rep_name']}** · {top['region']}  \n"
                       f"cACV **{fmt_m(top['total_cacv'])}** · Attainment **{fmt_pct(top['cacv_attainment_rate'])}**")
        with c2:
            att  = bot["cacv_attainment_rate"]
            body = (f"**{bot['rep_name']}** · {bot['region']}  \n"
                    f"cACV **{fmt_m(bot['total_cacv'])}** · Attainment **{fmt_pct(att)}**")
            st.error(body) if (pd.notna(att) and att < 0.6) else st.info(body)

    st.markdown("<br>", unsafe_allow_html=True)
    chart_df = filtered.nlargest(20, "total_cacv")
    fig = go.Figure()
    fig.add_bar(y=chart_df["rep_name"], x=chart_df["total_acv"], name="ACV",
                orientation="h", marker_color="#f1f5f9",
                marker_line=dict(color="#e2e8f0", width=1))
    fig.add_bar(y=chart_df["rep_name"], x=chart_df["total_cacv"], name="cACV",
                orientation="h", marker_color="#3b82f6",
                text=[f"{fmt_m(v)}  ·  {fmt_pct(r)}"
                      for v, r in zip(chart_df["total_cacv"], chart_df["cacv_attainment_rate"])],
                textposition="inside", textfont=dict(color="white", size=11))
    fig.update_layout(**_chart(
        barmode="overlay",
        xaxis=dict(tickprefix="$", tickformat=","),
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=-0.06),
        margin=dict(t=10, b=48, l=160, r=8),
        height=max(320, len(chart_df) * 30),
    ))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-header">Full Rep Table</div>', unsafe_allow_html=True)
    extra_cols   = ["total_expansion_signal_acv"] if "total_expansion_signal_acv" in filtered.columns else []
    extra_labels = ["Exp Signal"] if extra_cols else []
    tbl = filtered[["org_rank","region_rank","rep_name","region","segment",
                     "total_accounts","ramping_accounts","mature_accounts",
                     "total_acv","total_cacv","cacv_attainment_rate",
                     "total_acv_at_risk","expansion_opportunities","expansion_acv_pipeline"]
                    + extra_cols
                    + ["accounts_expansion","accounts_healthy","accounts_at_risk",
                       "accounts_shelfware","accounts_inactive"]].copy()
    tbl.columns = (["Org#","Rgn#","Rep","Region","Segment",
                    "Accts","Ramping","Mature",
                    "ACV","cACV","Attainment",
                    "ACV at Risk","Exp Opps","Exp Pipeline"]
                   + extra_labels
                   + ["Expansion","Healthy","At Risk","Shelfware","Inactive"])
    for col in ["ACV","cACV","ACV at Risk","Exp Pipeline"] + extra_labels:
        tbl[col] = tbl[col].apply(fmt_m)
    tbl["Attainment"] = tbl["Attainment"].apply(fmt_pct)
    st.dataframe(tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4: Renewal Risk  —  CFO · CS Leadership
# ─────────────────────────────────────────────────────────────────────────────

def page_renewal_risk(acct_df: pd.DataFrame, as_of_date_str: str):
    persona_callout(
        "CFO · CS Leadership",
        [
            "Which accounts are most likely to churn at renewal, and how much ACV is at stake?",
            "Which at-risk accounts expire in the next 90 days — what is our immediate exposure?",
            "Where should CS focus intervention effort before it's too late?",
        ],
        accent="#ef4444",
    )

    try:
        as_of = date.fromisoformat(as_of_date_str)
    except Exception:
        as_of = date.today()

    df = acct_df.copy()
    df["contract_end_date"] = pd.to_datetime(df["contract_end_date"]).dt.date
    df["days_to_renewal"]   = df["contract_end_date"].apply(lambda d: (d - as_of).days)

    window = st.radio("Renewal window", ["90 days", "180 days"], horizontal=True, index=1)
    max_days = 90 if window == "90 days" else 180

    risk_tiers = ["At Risk", "Shelfware", "Inactive"]
    upcoming   = df[(df["days_to_renewal"] >= 0) & (df["days_to_renewal"] <= max_days)].copy()
    at_risk    = upcoming[upcoming["health_tier"].isin(risk_tiers)]

    # KPI row
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card("Accounts Expiring",     str(len(upcoming)),            accent="#64748b"), unsafe_allow_html=True)
    c2.markdown(kpi_card("At-Risk Accounts",      str(len(at_risk)),
                          sub="In At Risk, Shelfware or Inactive tier", sub_cls="neg", accent="#ef4444"), unsafe_allow_html=True)
    c3.markdown(kpi_card("ACV Exposed",           fmt_m(at_risk["acv_at_risk"].sum()),
                          sub="Not backed by consumption", sub_cls="neg", accent="#ef4444"), unsafe_allow_html=True)
    c4.markdown(kpi_card("% of Total ACV",
                          fmt_pct(at_risk["acv_at_risk"].sum() / acct_df["annual_commit_dollars"].sum())
                          if acct_df["annual_commit_dollars"].sum() else "—",
                          sub="Total portfolio ACV at risk", sub_cls="neg", accent="#f97316"), unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    if upcoming.empty:
        st.info(f"No accounts renewing within {max_days} days in the current filter.")
        return

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown('<div class="section-header">ACV at Risk by Time-to-Renewal</div>', unsafe_allow_html=True)
        bins   = [0, 30, 60, 90, 180]
        labels = ["0–30 days", "31–60 days", "61–90 days", "91–180 days"]
        upcoming["bucket"] = pd.cut(upcoming["days_to_renewal"], bins=bins, labels=labels[:3 if max_days==90 else 4])
        bucket_df = (upcoming[upcoming["health_tier"].isin(risk_tiers)]
                     .groupby(["bucket","health_tier"], as_index=False)["acv_at_risk"].sum())
        fig = px.bar(bucket_df, x="bucket", y="acv_at_risk", color="health_tier",
                     color_discrete_map=HEALTH_COLORS,
                     labels={"bucket":"Days to Renewal","acv_at_risk":"ACV at Risk ($)","health_tier":"Health Tier"},
                     height=320)
        fig.update_layout(**_chart(
            barmode="stack",
            yaxis=dict(tickprefix="$", tickformat=","),
            legend=dict(orientation="h", y=-0.22),
        ))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown('<div class="section-header">Health Tier Breakdown — Expiring Accounts</div>', unsafe_allow_html=True)
        hc = upcoming["health_tier"].value_counts().reset_index()
        hc.columns = ["health_tier","count"]
        fig2 = px.pie(hc, names="health_tier", values="count",
                      color="health_tier", color_discrete_map=HEALTH_COLORS, hole=0.58)
        fig2.update_traces(textposition="outside", textinfo="label+percent",
                           textfont=dict(size=11),
                           marker=dict(line=dict(color="white", width=2)))
        fig2.add_annotation(text=f"<b>{len(upcoming)}</b><br><span style='font-size:11px;color:#94a3b8'>expiring</span>",
                             x=0.5, y=0.5, showarrow=False, font=dict(size=20, color="#0f172a"),
                             xref="paper", yref="paper", align="center")
        fig2.update_layout(**_chart(
            exclude=("xaxis", "yaxis"),
            showlegend=False, margin=dict(t=20, b=20, l=20, r=20), height=320,
        ))
        st.plotly_chart(fig2, use_container_width=True)

    # Renewal risk table
    st.markdown('<div class="section-header">Accounts Requiring Intervention</div>', unsafe_allow_html=True)
    tbl = at_risk.sort_values("acv_at_risk", ascending=False)[[
        "company_name","rep_name","region","health_tier",
        "annual_commit_dollars","trailing_90d_avg_rate","acv_at_risk",
        "contract_end_date","days_to_renewal",
    ]].copy()
    tbl.columns = ["Account","Rep","Region","Health","ACV","Cons Rate","ACV at Risk","Renews","Days Left"]
    tbl["ACV"]        = tbl["ACV"].apply(fmt_m)
    tbl["ACV at Risk"]= tbl["ACV at Risk"].apply(fmt_m)
    tbl["Cons Rate"]  = tbl["Cons Rate"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    color_map = {"At Risk":"#fef3c7","Shelfware":"#ffedd5","Inactive":"#fee2e2",
                 "Healthy":"#dbeafe","Expansion":"#d1fae5","Ramping":"#ede9fe"}
    styled = tbl.style.map(lambda v: f"background-color: {color_map.get(v,'')}", subset=["Health"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 5: Expansion & Activation  —  AEs · Sales Managers
# ─────────────────────────────────────────────────────────────────────────────

def page_expansion_activation(acct_df: pd.DataFrame):
    persona_callout(
        "Account Executives · Sales Managers",
        [
            "Which accounts are consistently over-consuming and ready for an expansion conversation?",
            "Which new accounts are ramping on track vs. stalling before the 6-month activation bonus window?",
            "Where should AEs prioritise upsell vs. onboarding effort?",
        ],
        accent="#10b981",
    )

    exp_df  = acct_df[acct_df["expansion_flag"] == True].copy()
    ramp_df = acct_df[acct_df["is_new_account"] == True].copy()
    ramp_df["rate"] = ramp_df["trailing_90d_avg_rate"].fillna(0)

    # ── Section 1: Expansion Pipeline ──────────────────────────────────────
    st.markdown('<div class="section-header">Expansion Pipeline</div>', unsafe_allow_html=True)
    st.caption("Accounts sustaining >120% of committed ACV consumption for 2+ consecutive months. "
               "These represent organic demand that has outgrown the current contract — "
               "high-confidence upsell candidates for AEs.")

    exp_signal_total = exp_df["expansion_signal_acv"].sum() if "expansion_signal_acv" in exp_df.columns else 0
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi_card("Flagged Accounts",    str(len(exp_df)),
                          sub="Sustained >120% consumption", accent="#10b981"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Expansion Signal ACV", fmt_m(exp_signal_total),
                          sub="Consumption above committed ACV", sub_cls="pos", accent="#10b981"), unsafe_allow_html=True)
    c3.markdown(kpi_card("Avg Consumption Rate", fmt_pct(exp_df["trailing_90d_avg_rate"].mean()) if not exp_df.empty else "—",
                          sub="Across flagged accounts", accent="#10b981"), unsafe_allow_html=True)

    if exp_df.empty:
        st.info("No accounts currently flagged for expansion. Accounts enter this view once they sustain >120% consumption for 2+ consecutive months.")
    else:
        tbl = exp_df.sort_values("expansion_signal_acv", ascending=False)[[
            "company_name","rep_name","region",
            "annual_commit_dollars","trailing_90d_avg_rate","cacv","expansion_signal_acv","acv_at_risk",
            "contract_end_date",
        ]].copy()
        tbl.columns = ["Account","Rep","Region","ACV","Cons Rate","cACV","Expansion Signal","ACV at Risk","Contract End"]
        for col in ["ACV","cACV","Expansion Signal","ACV at Risk"]:
            tbl[col] = tbl[col].apply(fmt_m)
        tbl["Cons Rate"] = tbl["Cons Rate"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
        st.dataframe(tbl, use_container_width=True, hide_index=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Section 2: New Account Activation Tracker ─────────────────────────
    st.markdown('<div class="section-header">New Account Activation Tracker</div>', unsafe_allow_html=True)
    st.caption("Accounts in the 90-day ramp window, excluded from cACV until history matures. "
               "AEs earn a one-time activation bonus when a new account sustains ≥80% consumption through month 6. "
               "Accounts below 30% current pace need onboarding attention.")

    on_track   = (ramp_df["rate"] >= 0.50).sum()
    developing = ((ramp_df["rate"] >= 0.20) & (ramp_df["rate"] < 0.50)).sum()
    lagging    = (ramp_df["rate"] < 0.20).sum()
    acv_ramping = ramp_df["annual_commit_dollars"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card("Ramping Accounts", str(len(ramp_df)),
                          sub="In 90-day ramp window", accent="#8b5cf6"), unsafe_allow_html=True)
    c2.markdown(kpi_card("ACV Ramping",      fmt_m(acv_ramping),
                          sub="Excluded from cACV until mature", accent="#8b5cf6"), unsafe_allow_html=True)
    c3.markdown(kpi_card("Strong Start (≥50%)", str(on_track),
                          sub_cls="pos" if on_track > 0 else "", accent="#10b981"), unsafe_allow_html=True)
    c4.markdown(kpi_card("Needs Attention (<20%)", str(lagging),
                          sub="Onboarding intervention recommended",
                          sub_cls="neg" if lagging > 0 else "", accent="#ef4444"), unsafe_allow_html=True)

    if not ramp_df.empty:
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown('<div class="section-header" style="margin-top:1rem;">Activation Pace Distribution</div>', unsafe_allow_html=True)
            bins   = [-0.001, 0.20, 0.50, 0.80, 2.0]
            blabels = ["Lagging (<20%)", "Developing (20–50%)", "On Pace (50–80%)", "Strong (≥80%)"]
            ramp_df["pace"] = pd.cut(ramp_df["rate"], bins=bins, labels=blabels)
            pace_counts = ramp_df["pace"].value_counts().reindex(blabels).fillna(0).reset_index()
            pace_counts.columns = ["Pace", "Count"]
            pace_colors = {"Lagging (<20%)":"#ef4444","Developing (20–50%)":"#f59e0b",
                           "On Pace (50–80%)":"#3b82f6","Strong (≥80%)":"#10b981"}
            fig = px.bar(pace_counts, x="Pace", y="Count",
                         color="Pace", color_discrete_map=pace_colors,
                         text="Count", height=280)
            fig.update_traces(textposition="outside")
            fig.update_layout(**_chart(
                showlegend=False,
                yaxis=dict(title="Accounts"),
            ))
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.markdown('<div class="section-header" style="margin-top:1rem;">ACV at Stake by Pace</div>', unsafe_allow_html=True)
            pace_acv = ramp_df.groupby("pace", as_index=False)["annual_commit_dollars"].sum()
            pace_acv.columns = ["Pace","ACV"]
            pace_acv = pace_acv.reindex(pace_acv["Pace"].map({l:i for i,l in enumerate(blabels)}).sort_values().index)
            fig2 = px.bar(pace_acv, x="Pace", y="ACV",
                          color="Pace", color_discrete_map=pace_colors,
                          text=pace_acv["ACV"].apply(fmt_m), height=280)
            fig2.update_traces(textposition="outside")
            fig2.update_layout(**_chart(
                showlegend=False,
                yaxis=dict(tickprefix="$", tickformat=",", title="ACV ($)"),
            ))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown('<div class="section-header">Ramping Account Detail</div>', unsafe_allow_html=True)
        ramp_tbl = ramp_df.sort_values("rate", ascending=False)[[
            "company_name","rep_name","region",
            "annual_commit_dollars","rate","contract_start_date","contract_end_date",
        ]].copy()
        ramp_tbl.columns = ["Account","Rep","Region","ACV","Current Cons Rate","Contract Start","Contract End"]
        ramp_tbl["ACV"]              = ramp_tbl["ACV"].apply(fmt_m)
        ramp_tbl["Current Cons Rate"] = ramp_tbl["Current Cons Rate"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
        st.dataframe(ramp_tbl, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 6: Account Detail  —  CS Leads · AEs
# ─────────────────────────────────────────────────────────────────────────────

def page_accounts(acct_df: pd.DataFrame, rep_name: str):
    persona_callout(
        "CS Leads · Account Executives",
        [
            "Which of my accounts are shelfware and haven't consumed credits in months?",
            "Which accounts are consistently over-consuming and ready for an expansion conversation?",
            "Which new accounts are ramping as expected vs. stalling?",
            "What is each account's consumption trend heading into renewal?",
        ],
        accent="#8b5cf6",
    )

    if acct_df.empty:
        st.info("No accounts match the current filter.")
        return

    tiers    = ["All"] + [t for t in TIER_ORDER if t in acct_df["health_tier"].unique()]
    sel_tier = st.selectbox("Filter by health tier", tiers, key="acct_tier_filter")
    view     = acct_df if sel_tier == "All" else acct_df[acct_df["health_tier"] == sel_tier]

    fig = px.scatter(
        view.dropna(subset=["trailing_90d_avg_rate"]),
        x="annual_commit_dollars", y="trailing_90d_avg_rate",
        color="health_tier", color_discrete_map=HEALTH_COLORS,
        size="annual_commit_dollars", size_max=20,
        hover_name="company_name",
        hover_data={"annual_commit_dollars":":.3s","trailing_90d_avg_rate":":.2f",
                    "cacv":":.3s","rep_name":True,"health_tier":True},
        labels={"annual_commit_dollars":"ACV ($)","trailing_90d_avg_rate":"Consumption Rate (90-day avg)"},
        opacity=0.80, height=380,
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color="#94a3b8", line_width=1,
                  annotation_text="100% commit", annotation_font_color="#94a3b8", annotation_font_size=11)
    fig.add_hline(y=0.80, line_dash="dot", line_color="#f59e0b", line_width=1,
                  annotation_text="80% floor", annotation_font_color="#f59e0b", annotation_font_size=11)
    fig.update_layout(**_chart(
        xaxis=dict(tickprefix="$", tickformat=","),
        legend=dict(orientation="h", y=-0.2),
        margin=dict(t=10, b=56, l=8, r=8),
    ))
    st.plotly_chart(fig, use_container_width=True)

    exp_cols   = ["expansion_signal_acv"] if "expansion_signal_acv" in view.columns else []
    exp_labels = ["Exp Signal"] if exp_cols else []
    tbl = view[["company_name","rep_name","region","health_tier",
                "annual_commit_dollars","trailing_90d_avg_rate","cacv"]
               + exp_cols
               + ["acv_at_risk","months_of_data",
                  "expansion_flag","is_spike_drop","is_new_account",
                  "contract_start_date","contract_end_date"]].copy()
    tbl.columns = (["Account","Rep","Region","Health","ACV","Cons Rate","cACV"]
                   + exp_labels
                   + ["ACV at Risk","Months","Expansion?","Spike/Drop?","Ramping?","Start","End"])
    for col in ["ACV","cACV","ACV at Risk"] + exp_labels:
        tbl[col] = tbl[col].apply(fmt_m)
    tbl["Cons Rate"] = tbl["Cons Rate"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    color_map = {"Expansion":"#d1fae5","Healthy":"#dbeafe","At Risk":"#fef3c7",
                 "Shelfware":"#ffedd5","Inactive":"#fee2e2","Ramping":"#ede9fe"}
    styled = tbl.style.map(lambda v: f"background-color: {color_map.get(v,'')}", subset=["Health"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 7: Data Health  —  Data Engineering · Finance · RevOps
# ─────────────────────────────────────────────────────────────────────────────

def page_data_health(acct_df: pd.DataFrame, rep_df: pd.DataFrame, as_of_date_str: str):
    persona_callout(
        "Data Engineering · Finance · RevOps",
        [
            "Is the pipeline snapshot fresh? When was the last successful run?",
            "Are any cACV numbers violating the cap rule (cACV > annual commit)?",
            "Do the formula components add up — does cACV + expansion signal equal ACV × rate?",
            "How many accounts are missing a consumption rate, or have a NULL health tier?",
        ],
        accent="#64748b",
    )

    today = date.today()
    try:
        snap_date  = date.fromisoformat(as_of_date_str)
        days_stale = (today - snap_date).days
    except Exception:
        snap_date  = None
        days_stale = None

    # ── Inline DQ checks ─────────────────────────────────────────────────────
    checks = []

    # 1. cACV cap violations
    cap_violations = int((acct_df["cacv"] > acct_df["annual_commit_dollars"] + 1).sum())
    checks.append({"Check": "cACV cap violations", "Severity": "ERROR",
                   "Status": "✓ PASS" if cap_violations == 0 else "✗ FAIL",
                   "Rows": cap_violations,
                   "Detail": "cacv > annual_commit_dollars — formula error in pipeline" if cap_violations else "All cACV values ≤ committed ACV"})

    # 2. Negative ACV at risk
    neg_risk = int((acct_df["acv_at_risk"] < -1).sum())
    checks.append({"Check": "Negative ACV at risk", "Severity": "ERROR",
                   "Status": "✓ PASS" if neg_risk == 0 else "✗ FAIL",
                   "Rows": neg_risk,
                   "Detail": "acv_at_risk = ACV − cACV; should always be ≥ 0" if neg_risk else "All ACV at risk values non-negative"})

    # 3. Negative expansion signal
    neg_exp = int((acct_df.get("expansion_signal_acv", pd.Series(dtype=float)).fillna(0) < -1).sum())
    checks.append({"Check": "Negative expansion signal", "Severity": "ERROR",
                   "Status": "✓ PASS" if neg_exp == 0 else "✗ FAIL",
                   "Rows": neg_exp,
                   "Detail": "expansion_signal_acv should always be ≥ 0" if neg_exp else "All expansion signal values non-negative"})

    # 4. NULL health tier
    null_tier = int(acct_df["health_tier"].isna().sum())
    checks.append({"Check": "NULL health tier", "Severity": "ERROR",
                   "Status": "✓ PASS" if null_tier == 0 else "✗ FAIL",
                   "Rows": null_tier,
                   "Detail": "All accounts must have a health tier assigned" if null_tier else "No NULL health tiers"})

    # 5. Orphaned accounts (no matching rep)
    orphaned = int(acct_df["rep_name"].isna().sum()) if "rep_name" in acct_df.columns else 0
    checks.append({"Check": "Orphaned accounts (no rep)", "Severity": "WARNING",
                   "Status": "✓ PASS" if orphaned == 0 else "⚠ WARN",
                   "Rows": orphaned,
                   "Detail": f"{orphaned} accounts have no matching sales rep — excluded from rep rollup" if orphaned else "All accounts have a rep assignment"})

    # 6. Missing consumption rate on mature accounts
    mature_mask  = acct_df["health_tier"] != "Ramping"
    missing_rate = int(acct_df.loc[mature_mask, "trailing_90d_avg_rate"].isna().sum())
    checks.append({"Check": "Missing cons rate (mature)", "Severity": "WARNING",
                   "Status": "✓ PASS" if missing_rate == 0 else "⚠ WARN",
                   "Rows": missing_rate,
                   "Detail": f"{missing_rate} mature (non-ramping) accounts missing trailing 90-day rate — may indicate missing usage data" if missing_rate else "All mature accounts have a consumption rate"})

    # 7. Shelfware rate vs §9 target (≤8%) and DQ alert (>15%)
    mature_count     = int(mature_mask.sum())
    shelfware_count  = int(acct_df["health_tier"].isin(["Shelfware", "Inactive"]).sum())
    shelfware_rate   = shelfware_count / mature_count if mature_count else 0
    sw_status        = "✓ PASS" if shelfware_rate <= 0.08 else ("⚠ WARN" if shelfware_rate <= 0.15 else "✗ FAIL")
    sw_severity      = "INFO" if shelfware_rate <= 0.08 else ("WARNING" if shelfware_rate <= 0.15 else "ERROR")
    checks.append({"Check": "Shelfware rate (target ≤8%, alert >15%)", "Severity": sw_severity,
                   "Status": sw_status,
                   "Rows": shelfware_count,
                   "Detail": f"{shelfware_rate:.1%} of mature accounts in Shelfware/Inactive tier (target ≤8%; DQ alert at >15%)"})

    # 8. Ramping rate — informational
    ramp_count = int((acct_df["health_tier"] == "Ramping").sum())
    ramp_rate  = ramp_count / len(acct_df) if len(acct_df) else 0
    checks.append({"Check": "Ramping rate", "Severity": "INFO",
                   "Status": "ℹ INFO",
                   "Rows": ramp_count,
                   "Detail": f"{ramp_rate:.1%} of accounts in Ramping status — excluded from cACV (informational)"})

    errors   = [c for c in checks if c["Status"].startswith("✗")]
    warnings = [c for c in checks if c["Status"].startswith("⚠")]
    n_passed = sum(1 for c in checks if c["Status"].startswith("✓"))

    # ── KPI row ───────────────────────────────────────────────────────────────
    if days_stale is not None:
        fresh_ok  = days_stale <= 1
        fresh_val = "Today" if days_stale == 0 else f"{days_stale}d old"
        fresh_sub = "✓ Fresh" if fresh_ok else f"⚠ {days_stale} days stale — run pipeline"
        fresh_cls = "" if fresh_ok else "neg"
        fresh_acc = "#10b981" if fresh_ok else "#f59e0b"
    else:
        fresh_val, fresh_sub, fresh_cls, fresh_acc = "—", "", "", "#64748b"

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(kpi_card("Snapshot Date", as_of_date_str,
                          sub=fresh_sub, sub_cls=fresh_cls, accent=fresh_acc), unsafe_allow_html=True)
    c2.markdown(kpi_card("Checks Passed", f"{n_passed}/{len(checks)}",
                          accent="#10b981" if not errors else "#ef4444"), unsafe_allow_html=True)
    c3.markdown(kpi_card("ERROR Failures", str(len(errors)),
                          sub="Must be 0 before comp platform sync" if errors else "Clean — ready to sync",
                          sub_cls="neg" if errors else "pos",
                          accent="#ef4444" if errors else "#10b981"), unsafe_allow_html=True)
    c4.markdown(kpi_card("Warnings", str(len(warnings)),
                          sub="Review before next pipeline run" if warnings else "No active warnings",
                          accent="#f59e0b" if warnings else "#64748b"), unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # ── Check results table ──────────────────────────────────────────────────
    st.markdown('<div class="section-header">Check Results</div>', unsafe_allow_html=True)
    chk_df = pd.DataFrame(checks)

    def _status_style(v):
        if str(v).startswith("✗"): return "color:#ef4444;font-weight:700"
        if str(v).startswith("⚠"): return "color:#f59e0b;font-weight:700"
        if str(v).startswith("ℹ"): return "color:#6b7280"
        return "color:#10b981;font-weight:600"

    def _sev_style(v):
        return {"ERROR": "color:#ef4444", "WARNING": "color:#f59e0b",
                "INFO": "color:#6b7280"}.get(str(v), "")

    st.dataframe(
        chk_df.style.map(_status_style, subset=["Status"]).map(_sev_style, subset=["Severity"]),
        use_container_width=True, hide_index=True,
    )

    # ── Data coverage summary ─────────────────────────────────────────────────
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-header">Data Coverage</div>', unsafe_allow_html=True)
    tier_counts = acct_df["health_tier"].value_counts().to_dict()
    total_a = len(acct_df)
    total_r = len(rep_df)

    coverage = pd.DataFrame([
        {"Metric": "Accounts in snapshot",               "Value": f"{total_a:,}"},
        {"Metric": "Reps in snapshot",                   "Value": f"{total_r:,}"},
        {"Metric": "Accounts with consumption rate",
         "Value": f'{acct_df["trailing_90d_avg_rate"].notna().sum():,} '
                  f'({acct_df["trailing_90d_avg_rate"].notna().mean():.1%})'},
        {"Metric": "Accounts with cACV > 0",
         "Value": f'{(acct_df["cacv"] > 0).sum():,} '
                  f'({(acct_df["cacv"] > 0).mean():.1%})'},
        {"Metric": "Shelfware + Inactive",
         "Value": f'{tier_counts.get("Shelfware", 0) + tier_counts.get("Inactive", 0):,} '
                  f'({(tier_counts.get("Shelfware", 0) + tier_counts.get("Inactive", 0)) / total_a:.1%})'},
        {"Metric": "Ramping (excluded from cACV)",
         "Value": f'{tier_counts.get("Ramping", 0):,} '
                  f'({tier_counts.get("Ramping", 0) / total_a:.1%})'},
        {"Metric": "Expansion-flagged accounts",
         "Value": f'{int(acct_df["expansion_flag"].sum()):,}'},
    ])
    st.dataframe(coverage, use_container_width=True, hide_index=True)

    st.markdown(
        f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
        f'padding:0.85rem 1.1rem;margin-top:1rem;">'
        f'<span style="font-size:0.72rem;font-weight:600;letter-spacing:0.07em;'
        f'text-transform:uppercase;color:#94a3b8;">Full upstream DQ suite</span><br>'
        f'<span style="font-size:0.8rem;color:#64748b;">The checks above run on the loaded snapshot. '
        f'For full upstream validation against raw BigQuery tables — including NULL primary keys, '
        f'orphaned usage logs, duplicate log IDs, and malformed contracts — run:<br>'
        f'<code style="background:#e2e8f0;border-radius:4px;padding:2px 6px;font-size:0.8rem;">'
        f'python3 pipeline_and_tests/dq_tests.py --as-of-date {as_of_date_str}'
        f'</code></span></div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    inject_css()

    st.markdown("""
    <div class="page-header">
        <div class="page-eyebrow">Prisma Cloud</div>
        <div class="page-title">cACV Executive Dashboard</div>
        <div class="page-sub">Consumed Annual Contract Value · North Star Metric for the Hybrid Consumption Model</div>
    </div>
    """, unsafe_allow_html=True)

    if _is_demo():
        st.info("**Demo mode** — showing a cached pipeline snapshot. All filters, charts, and tables are fully interactive.")

    available_dates = load_available_dates()
    initial_date    = available_dates[0] if available_dates else "2026-06-01"
    rep_df_full     = load_rep_rollup(initial_date)

    if rep_df_full.empty:
        st.warning("No data found. Run `python3 pipeline_and_tests/run_pipeline.py` to populate.")
        st.stop()

    as_of_date, region, rep_name, employee_id = render_sidebar(rep_df_full)

    rep_df      = load_rep_rollup(as_of_date)
    rep_df_view = rep_df.copy()
    if region != "All":      rep_df_view = rep_df_view[rep_df_view["region"] == region]
    if employee_id:          rep_df_view = rep_df_view[rep_df_view["employee_id"] == employee_id]

    acct_df      = load_accounts(as_of_date, region, employee_id)
    acct_df_full = load_accounts(as_of_date)   # unfiltered for renewal risk

    tab_ov, tab_rgn, tab_rep, tab_rnw, tab_exp, tab_acct, tab_dq = st.tabs([
        "📊  Portfolio Overview",
        "🗺  By Region",
        "👤  By Rep",
        "⚠️  Renewal Risk",
        "📈  Expansion & Activation",
        "🏢  Account Detail",
        "📋  Data Health",
    ])

    with tab_ov:   page_overview(rep_df_view, acct_df)
    with tab_rgn:  page_region(rep_df, acct_df_full)
    with tab_rep:  page_reps(rep_df_view)
    with tab_rnw:  page_renewal_risk(acct_df_full, as_of_date)
    with tab_exp:  page_expansion_activation(acct_df_full)
    with tab_acct: page_accounts(acct_df, rep_name)
    with tab_dq:   page_data_health(acct_df_full, rep_df, as_of_date)


if __name__ == "__main__":
    main()
