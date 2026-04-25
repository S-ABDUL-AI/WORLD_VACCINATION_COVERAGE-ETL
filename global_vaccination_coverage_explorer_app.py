"""
Global Vaccination Coverage Explorer
WHO style data coverage monitoring across 190 plus countries.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import streamlit as st
from scipy.stats import sem, t, ttest_ind

from etl_pipeline import DB_PATH, TABLE_CLEAN, run_etl

try:
    from report_generator import build_report_bytes

    REPORT_AVAILABLE = True
except ImportError:
    REPORT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
NAVY = "#0A1F44"
NAVY_MID = "#152B5C"
GOLD = "#C9A84C"
GOLD_LT = "#E8C97A"
INK = "#1A1A1A"
BODY = "#2C3E50"
MUTED = "#6B7280"
RED = "#C8382A"
AMBER = "#B8560A"
GREEN = "#1A7A2E"
RULE = "#E2E6EC"
OFF_WHITE = "#F8F6F1"


st.set_page_config(
    page_title="Global Vaccination Coverage Explorer",
    page_icon="💉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
  html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; background:{OFF_WHITE}; }}
  .hero-wrap {{ background:linear-gradient(135deg,{NAVY} 0%,{NAVY_MID} 60%,#1E3A6E 100%);
                border-left:6px solid {GOLD}; border-radius:6px;
                padding:36px 40px 32px; margin-bottom:22px; }}
  .hero-eye  {{ font-size:11px; font-weight:700; letter-spacing:2.5px; color:{GOLD}; text-transform:uppercase; margin-bottom:10px; }}
  .hero-title{{ font-size:30px; font-weight:800; color:#FFFFFF; line-height:1.3; margin-bottom:12px; }}
  .hero-sub  {{ font-size:14px; color:#B0BFD8; line-height:1.6; max-width:860px; }}
  .scope-box {{ background:#FFFBF0; border:1px solid {AMBER}; border-left:4px solid {AMBER};
                border-radius:4px; padding:10px 16px; font-size:12px; color:{AMBER};
                margin-bottom:20px; }}
  .sec-lbl  {{ font-size:10px; font-weight:700; letter-spacing:2px; color:{GOLD};
               text-transform:uppercase; margin-bottom:4px; }}
  .sec-ttl  {{ font-size:20px; font-weight:700; color:{NAVY}; margin-bottom:4px; }}
  .sec-sub  {{ font-size:13px; color:{MUTED}; margin-bottom:14px; }}
  .kpi-card {{ background:#FFFFFF; border:1px solid {RULE}; border-top:3px solid {NAVY};
               border-radius:4px; padding:16px 20px; min-height:114px; }}
  .kpi-label{{ font-size:11px; font-weight:700; letter-spacing:1px; color:{MUTED};
               text-transform:uppercase; margin-bottom:4px; }}
  .kpi-val  {{ font-size:26px; font-weight:800; color:{NAVY}; line-height:1.1; }}
  .kpi-delta{{ font-size:11px; color:{MUTED}; margin-top:2px; }}
  .brief-risk{{ background:#FFF5F5; border:1px solid #FFC9C9; border-left:4px solid {RED};
                border-radius:4px; padding:16px 18px; }}
  .brief-imp {{ background:#F0F4FF; border:1px solid #C4D0F5; border-left:4px solid {NAVY};
                border-radius:4px; padding:16px 18px; }}
  .brief-act {{ background:#F0FFF4; border:1px solid #A8D5B5; border-left:4px solid {GREEN};
                border-radius:4px; padding:16px 18px; }}
  .brief-head{{ font-size:10px; font-weight:700; letter-spacing:2px;
               text-transform:uppercase; margin-bottom:6px; }}
  .brief-body{{ font-size:13px; color:{BODY}; line-height:1.6; }}
  .byline    {{ background:{NAVY}; border-radius:4px; padding:18px 24px;
               font-size:12px; color:#B0BFD8; line-height:1.8; margin-top:30px; }}
  .byline a  {{ color:{GOLD}; text-decoration:none; }}
  div[data-testid="stButton"] > button {{
    background:{NAVY}; color:#FFFFFF; border:none; border-radius:3px;
    font-weight:600; letter-spacing:0.5px; }}
  div[data-testid="stButton"] > button:hover {{ background:{NAVY_MID}; }}
  .stDownloadButton > button {{
    background:{GOLD} !important; color:{INK} !important; font-weight:700 !important; }}
</style>
""",
    unsafe_allow_html=True,
)


def country_to_flag(country_name: str) -> str:
    try:
        country = pycountry.countries.lookup(country_name)
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country.alpha_2)
    except Exception:
        return "🏳️"


def mean_ci(data: pd.Series, confidence: float = 0.95) -> tuple[float, float]:
    if len(data) < 2:
        return np.nan, np.nan
    m = float(np.mean(data))
    se = float(sem(data, nan_policy="omit"))
    h = se * float(t.ppf((1 + confidence) / 2, len(data) - 1))
    return m - h, m + h


@st.cache_data(show_spinner=False, ttl=3600)
def load_country_antigen_index(_db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(_db_path)
    try:
        return pd.read_sql_query(
            f"SELECT DISTINCT country, antigen FROM {TABLE_CLEAN} ORDER BY country, antigen;",
            conn,
        )
    finally:
        conn.close()


@st.cache_data(show_spinner=False, ttl=3600)
def load_coverage_series(_db_path: str, country: str, antigen: str) -> pd.DataFrame:
    conn = sqlite3.connect(_db_path)
    try:
        return pd.read_sql_query(
            f"""
            SELECT year, coverage_pct
            FROM {TABLE_CLEAN}
            WHERE country = ? AND antigen = ?
            ORDER BY year;
            """,
            conn,
            params=(country, antigen),
        )
    finally:
        conn.close()


def _safe_database_init() -> bool:
    if os.path.exists(DB_PATH):
        return True
    with st.spinner("Initializing OWID vaccination database. This may take a few minutes..."):
        try:
            run_etl()
            load_country_antigen_index.clear()
            load_coverage_series.clear()
            return True
        except Exception as exc:
            st.error(f"Database initialization failed: {exc}")
            return False


def _policy_brief_text(
    before_vals: pd.Series,
    after_vals: pd.Series,
    avg_before: float,
    avg_after: float,
    diff: float,
    p_val: float,
) -> tuple[str, str, str]:
    risk = (
        f"The after window changes by <strong>{diff:+.1f} percentage points</strong>. "
        f"Observed p-value is <strong>{p_val:.4f}</strong>. "
        "Potential data risk includes reporting gaps, denominator changes, and lag in national updates."
    )
    implication = (
        f"Before window mean is <strong>{avg_before:.1f}%</strong> and after window mean is <strong>{avg_after:.1f}%</strong>. "
        "This indicates directional movement in coverage but does not establish causality by itself."
    )
    action = (
        "Use this result to prioritize low coverage countries for review, validate with country program teams, "
        "and pair with delivery metrics before final policy decisions."
    )
    if len(before_vals) <= 1 or len(after_vals) <= 1:
        risk = "Insufficient yearly observations in one or both windows for robust significance testing."
        implication = "The current output is descriptive only. A statistical before and after comparison is not reliable yet."
        action = "Increase the pre and post window lengths or use a country and antigen with longer historical coverage series."
    return risk, implication, action


def run() -> None:
    st.markdown(
        """
<div class="hero-wrap">
  <div class="hero-eye">Global Vaccination Coverage Explorer · WHO style ETL monitoring</div>
  <div class="hero-title">580 million children missed routine vaccinations in 2023. Where are the gaps?</div>
  <div class="hero-sub">
    This tool helps public health program managers, WHO and UNICEF partners, and policy teams inspect
    country level coverage trends, compare pre and post windows, and export a structured policy report.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Inputs")
        campaign_start = st.number_input("Reference year", value=2017, min_value=1980, max_value=2030)
        pre_years = st.number_input("Years before", value=5, min_value=1, max_value=30)
        post_years = st.number_input("Years after", value=5, min_value=1, max_value=30)
        if st.button("Refresh OWID data", type="primary", use_container_width=True):
            with st.spinner("Refreshing dataset..."):
                run_etl()
                load_country_antigen_index.clear()
                load_coverage_series.clear()
                st.success("Dataset refreshed.")
                st.rerun()
        st.caption(
            "Data source: OWID global vaccination coverage extract. "
            "Use outputs as decision support, not as a substitute for national program reviews."
        )

    if not _safe_database_init():
        st.stop()

    df_meta = load_country_antigen_index(DB_PATH)
    if df_meta.empty:
        st.warning("No vaccination rows available. Refresh data from the sidebar.")
        st.stop()

    countries = sorted(df_meta["country"].unique())
    default_idx = countries.index("India") if "India" in countries else 0
    with st.sidebar:
        country = st.selectbox("Country", countries, index=default_idx)
        antigens = sorted(df_meta[df_meta["country"] == country]["antigen"].unique())
        antigen = st.selectbox("Antigen / vaccine program", antigens, index=0)

    series = load_coverage_series(DB_PATH, country, antigen)
    if series.empty:
        st.warning("No time series for this country and antigen selection.")
        st.stop()

    # clean and basic stats
    series["year"] = pd.to_numeric(series["year"], errors="coerce")
    series["coverage_pct"] = pd.to_numeric(series["coverage_pct"], errors="coerce")
    series = series.dropna().copy()
    series = series.sort_values("year")

    latest = float(series["coverage_pct"].iloc[-1])
    earliest = float(series["coverage_pct"].iloc[0])
    yr_min, yr_max = int(series["year"].min()), int(series["year"].max())
    delta = latest - earliest
    n_obs = len(series)

    before_vals = series[
        (series["year"] >= campaign_start - pre_years) & (series["year"] <= campaign_start - 1)
    ]["coverage_pct"]
    after_vals = series[
        (series["year"] >= campaign_start) & (series["year"] <= campaign_start + post_years)
    ]["coverage_pct"]

    p_val = np.nan
    t_stat = np.nan
    avg_before = float(before_vals.mean()) if len(before_vals) else np.nan
    avg_after = float(after_vals.mean()) if len(after_vals) else np.nan
    diff = float(avg_after - avg_before) if len(before_vals) and len(after_vals) else np.nan
    ci_before = mean_ci(before_vals) if len(before_vals) > 1 else (np.nan, np.nan)
    ci_after = mean_ci(after_vals) if len(after_vals) > 1 else (np.nan, np.nan)
    if len(before_vals) > 1 and len(after_vals) > 1:
        t_stat, p_val = ttest_ind(before_vals, after_vals, equal_var=False)

    scope_note = (
        f"<strong>Scope note:</strong> Country is <strong>{country} {country_to_flag(country)}</strong>, "
        f"antigen is <strong>{antigen.replace('coverage__', '')}</strong>, years span <strong>{yr_min} to {yr_max}</strong>. "
        "Figures reflect reported coverage and should be interpreted with delivery context."
    )
    st.markdown(f'<div class="scope-box">{scope_note}</div>', unsafe_allow_html=True)

    st.markdown('<div class="sec-lbl">Executive Snapshot</div>', unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    kpi_data = [
        (k1, "Latest coverage", f"{latest:.1f}%", f"{delta:+.1f} pp vs first year"),
        (k2, "Series years", f"{yr_min}-{yr_max}", f"{n_obs} annual observations"),
        (k3, "Before window mean", f"{avg_before:.1f}%" if not np.isnan(avg_before) else "N/A", f"Window: {campaign_start-pre_years} to {campaign_start-1}"),
        (k4, "After window mean", f"{avg_after:.1f}%" if not np.isnan(avg_after) else "N/A", f"Window: {campaign_start} to {campaign_start+post_years}"),
    ]
    for col, lbl, val, sub in kpi_data:
        with col:
            st.markdown(
                f"""
<div class="kpi-card">
  <div class="kpi-label">{lbl}</div>
  <div class="kpi-val">{val}</div>
  <div class="kpi-delta">{sub}</div>
</div>
""",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sec-lbl">Policy Brief</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec-ttl">Risk · Implication · Action</div>', unsafe_allow_html=True)
    risk_txt, imp_txt, act_txt = _policy_brief_text(before_vals, after_vals, avg_before, avg_after, diff, p_val)
    b1, b2, b3 = st.columns(3)
    with b1:
        st.markdown(
            f'<div class="brief-risk"><div class="brief-head" style="color:{RED};">Risk</div><div class="brief-body">{risk_txt}</div></div>',
            unsafe_allow_html=True,
        )
    with b2:
        st.markdown(
            f'<div class="brief-imp"><div class="brief-head" style="color:{NAVY};">Implication</div><div class="brief-body">{imp_txt}</div></div>',
            unsafe_allow_html=True,
        )
    with b3:
        st.markdown(
            f'<div class="brief-act"><div class="brief-head" style="color:{GREEN};">Action</div><div class="brief-body">{act_txt}</div></div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sec-lbl">Charts</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)

    with c1:
        line = go.Figure()
        line.add_trace(
            go.Scatter(
                x=series["year"],
                y=series["coverage_pct"],
                mode="lines+markers",
                name="Coverage percent",
                line=dict(color=NAVY, width=2),
                marker=dict(size=6),
            )
        )
        line.add_vline(
            x=campaign_start,
            line_dash="dash",
            line_color=RED,
            annotation_text=f"Reference {campaign_start}",
            annotation_position="top right",
        )
        line.update_layout(
            title="Coverage trend by year",
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin=dict(t=40, b=20, l=20, r=10),
            xaxis=dict(title="Year", showgrid=False, zeroline=False),
            yaxis=dict(title="Coverage percent", range=[0, 100], showgrid=False, zeroline=False),
            showlegend=False,
            height=380,
        )
        st.plotly_chart(line, use_container_width=True)

    with c2:
        window_df = pd.DataFrame(
            {
                "Window": ["Before", "After"],
                "Mean": [avg_before, avg_after],
                "CI Low": [ci_before[0], ci_after[0]],
                "CI High": [ci_before[1], ci_after[1]],
            }
        )
        bar = go.Figure(
            go.Bar(
                x=window_df["Window"],
                y=window_df["Mean"],
                marker_color=[AMBER, GREEN],
                text=[f"{x:.1f}%" if pd.notna(x) else "N/A" for x in window_df["Mean"]],
                textposition="outside",
            )
        )
        bar.update_layout(
            title="Before vs after average coverage",
            paper_bgcolor="white",
            plot_bgcolor="white",
            margin=dict(t=40, b=20, l=20, r=10),
            xaxis=dict(title="", showgrid=False, zeroline=False),
            yaxis=dict(title="Coverage percent", range=[0, 100], showgrid=False, zeroline=False),
            showlegend=False,
            height=380,
        )
        st.plotly_chart(bar, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sec-lbl">Data table</div>', unsafe_allow_html=True)
    st.dataframe(series, use_container_width=True, height=280)
    st.download_button(
        "📥 Download full series CSV",
        data=series.to_csv(index=False).encode("utf-8"),
        file_name=f"{country}_{antigen}_coverage_series.csv".replace(" ", "_").replace("/", "-"),
        mime="text/csv",
        use_container_width=True,
    )

    st.markdown("---")
    st.markdown('<div class="sec-lbl">Export</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-ttl">Download McKinsey Style Policy Report</div><div class="sec-sub">'
        "Generate a policy memo with executive snapshot, risk implication action cards, chart exhibits, "
        "and methodology notes for country decision reviews."
        "</div>",
        unsafe_allow_html=True,
    )

    if REPORT_AVAILABLE:
        if st.button("📄 Generate Report PDF", type="primary", use_container_width=True):
            with st.spinner("Building your report…"):
                pdf_bytes = build_report_bytes(
                    series=series,
                    country=country,
                    antigen=antigen,
                    campaign_start=int(campaign_start),
                    pre_years=int(pre_years),
                    post_years=int(post_years),
                    p_val=float(p_val) if pd.notna(p_val) else np.nan,
                    avg_before=float(avg_before) if pd.notna(avg_before) else np.nan,
                    avg_after=float(avg_after) if pd.notna(avg_after) else np.nan,
                )
                st.session_state["vacc_report_bytes"] = pdf_bytes
                st.success("Report ready. Use download below.")
        if "vacc_report_bytes" in st.session_state:
            st.download_button(
                "⬇ Download PDF Report",
                data=st.session_state["vacc_report_bytes"],
                file_name=f"global_vaccination_coverage_report_{date.today().isoformat()}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    else:
        st.warning("report_generator.py not found. Add it to enable PDF export.")

    st.markdown(
        f"""
<div class="byline">
  <strong style="color:{GOLD};">Built by Sherriff Abdul-Hamid</strong> — Product leader specializing in government digital services,
  safety net benefits delivery, and decision-support tools for underserved communities. Former Founder &amp; CEO, Poverty 360
  (25,000+ beneficiaries served across West Africa). Partnered with Ghana's National Health Insurance Authority to enroll
  1,250 vulnerable individuals into national health coverage. Directed $200M+ in resource allocation for USAID, UNDP, and UKAID.
  Obama Foundation Leaders Award (Top 1.3%) · Mandela Washington Fellow (Top 0.3%) · Harvard Business School.<br><br>
  <strong style="color:{GOLD};">Related tools:</strong> &nbsp;
  <a href="https://smart-resource-allocation-dashboard-eudzw5r2f9pbu4qyw3psez.streamlit.app">Public Budget Allocation Tool</a> &nbsp;·&nbsp;
  <a href="https://chpghrwawmvddoquvmniwm.streamlit.app">Medicaid Access Risk Monitor</a> &nbsp;·&nbsp;
  <a href="https://povertyearlywarningsystem-7rrmkktbi7bwha2nna8gk7.streamlit.app">Safety Net Risk Monitor</a> &nbsp;·&nbsp;
  <a href="https://impact-allocation-engine-ahxxrbgwmvyapwmifahk2b.streamlit.app">GovFund Allocation Engine</a> &nbsp;·&nbsp;
  <a href="https://worldvaccinationcoverage-etl-ftvwbikifyyx78xyy2j3zv.streamlit.app">Global Vaccination Coverage Explorer</a> &nbsp;·&nbsp;
  <a href="https://www.linkedin.com/in/abdul-hamid-sherriff-08583354/">LinkedIn</a>
</div>
""",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    run()
