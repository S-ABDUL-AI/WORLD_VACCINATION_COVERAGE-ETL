# streamlit_app.py — World Vaccination Coverage (OWID) ETL & analysis
import os
import sqlite3

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pycountry
import streamlit as st
from scipy.stats import sem, t, ttest_ind

from etl_pipeline import DB_PATH, TABLE_CLEAN, run_etl

st.set_page_config(
    page_title="World Vaccination Coverage",
    layout="wide",
    page_icon="💉",
    initial_sidebar_state="expanded",
)

_TRUST_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
    }
    .block-container { padding-top: 1rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 600; color: #253858; }
    h1 { color: #0052CC !important; font-weight: 700 !important; }
    h2, h3 { color: #253858 !important; }
    .wv-kpi-row { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 10px; }
    .wv-kpi-card {
        flex: 1 1 200px;
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border-radius: 10px;
        padding: 16px 18px;
        box-shadow: 0 1px 3px rgba(37,56,88,0.08);
        border: 1px solid #e2e8f0;
        border-left-width: 5px;
        border-left-style: solid;
        min-height: 108px;
    }
    .wv-kpi-label { color: #64748b; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase; }
    .wv-kpi-value { color: #253858; font-size: 1.45rem; font-weight: 700; line-height: 1.2; margin-top: 6px; }
    .wv-kpi-sub { color: #475569; font-size: 0.86rem; margin-top: 8px; line-height: 1.35; }
    .wv-insight-box {
        border-radius: 12px;
        padding: 20px 22px;
        margin: 18px 0 10px 0;
        border: 1px solid #e2e8f0;
        background: #f8fafc;
        border-left-width: 5px;
        border-left-style: solid;
    }
    .wv-insight-kicker { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
    .wv-insight-lead { color: #253858; font-size: 1.2rem; font-weight: 800; line-height: 1.35; margin: 10px 0 12px 0; }
    .wv-insight-body { color: #334155; font-size: 0.98rem; line-height: 1.55; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
</style>
"""
st.markdown(_TRUST_CSS, unsafe_allow_html=True)

COL_BEFORE = "#64748b"
COL_AFTER = "#0052CC"
COL_WIN = "#0d9488"
COL_CAUTION = "#d97706"
COL_NEUTRAL = "#475569"


def _kpi_card_html(label: str, value: str, sub: str, accent: str) -> str:
    return (
        f'<div class="wv-kpi-card" style="border-left-color:{accent};">'
        f'<div class="wv-kpi-label">{label}</div>'
        f'<div class="wv-kpi-value">{value}</div>'
        f'<div class="wv-kpi-sub">{sub}</div></div>'
    )


def country_to_flag(country_name: str) -> str:
    try:
        country = pycountry.countries.lookup(country_name)
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country.alpha_2)
    except Exception:
        return "🏳️"


def mean_ci(data, confidence=0.95):
    if len(data) < 2:
        return np.nan, np.nan
    mean = np.mean(data)
    se = sem(data, nan_policy="omit")
    h = se * t.ppf((1 + confidence) / 2, len(data) - 1)
    return mean - h, mean + h


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


st.title("World Vaccination Coverage — Decision View")
st.caption(
    "ETL from OWID global coverage data. Compare pre/post campaign windows, export for audit trails."
)

# --- Sidebar: all controls ---
st.sidebar.header("Campaign window")
campaign_start = st.sidebar.number_input("Campaign / reference year", value=2017, min_value=1980, max_value=2030)
pre_years = st.sidebar.number_input("Years before", value=5, min_value=1, max_value=30)
post_years = st.sidebar.number_input("Years after", value=5, min_value=1, max_value=30)

if st.sidebar.button("🔄 Refresh data from OWID", type="primary"):
    with st.spinner("Refreshing full dataset (may take a minute)…"):
        try:
            run_etl()
            load_country_antigen_index.clear()
            load_coverage_series.clear()
            st.session_state.etl_ok = True
            st.success("Database updated.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(str(e))

st.sidebar.divider()
st.sidebar.caption(
    "Data: [Our World in Data — vaccination coverage](https://ourworldindata.org/vaccination). "
    "For analysis and transparency workflows — not a substitute for national policy systems."
)

if not os.path.exists(DB_PATH):
    st.warning(
        "Database not initialized in this environment yet.\n\n"
        "Click **Initialize database** to download OWID data and build the local SQLite DB.\n"
        "(This can take a few minutes.)"
    )
    if st.button("Initialize database", type="primary"):
        with st.spinner("Downloading OWID data and building SQLite database…"):
            try:
                run_etl()
                st.success("Database initialized ✅")
                st.rerun()
            except Exception as e:
                st.error(f"ETL failed: {e}")
                st.info("If this keeps failing, redeploy the app and try again. Network access may be restricted.")
    st.stop()

try:
    df_meta = load_country_antigen_index(DB_PATH)
except Exception as e:
    st.error(f"Could not read database: {e}")
    st.stop()

if df_meta.empty:
    st.warning("No rows in the clean table. Click **Refresh data from OWID** in the sidebar.")
    st.stop()

countries = sorted(df_meta["country"].unique())
default_idx = countries.index("India") if "India" in countries else 0
st.sidebar.header("Geography & program")
country = st.sidebar.selectbox("Country", countries, index=default_idx)

antigens = sorted(df_meta[df_meta["country"] == country]["antigen"].unique())
antigen = st.sidebar.selectbox("Antigen / vaccine program", antigens, index=0)

series = load_coverage_series(DB_PATH, country, antigen)

if series.empty:
    st.info("No time series for this selection.")
    st.stop()

latest = float(series["coverage_pct"].iloc[-1])
earliest = float(series["coverage_pct"].iloc[0])
yr_min, yr_max = int(series["year"].min()), int(series["year"].max())
delta = latest - earliest
n_obs = len(series)

# --- Top KPI row (executive cards) ---
kpi_top = (
    '<div class="wv-kpi-row">'
    + _kpi_card_html(
        "Years covered",
        f"{yr_min}–{yr_max}",
        "Calendar span in OWID clean series",
        COL_NEUTRAL,
    )
    + _kpi_card_html(
        "Latest coverage",
        f"{latest:.1f}%",
        f"<strong>{delta:+.1f} pp</strong> vs first year in series",
        COL_WIN if delta > 0 else (COL_CAUTION if delta < 0 else COL_NEUTRAL),
    )
    + _kpi_card_html(
        "First year in series",
        f"{earliest:.1f}%",
        "Baseline observation in this extract",
        COL_BEFORE,
    )
    + _kpi_card_html(
        "Annual observations",
        f"{n_obs:,}",
        "Audit trail: count of year rows used in charts",
        COL_AFTER,
    )
    + "</div>"
)
st.markdown(kpi_top, unsafe_allow_html=True)

st.info(
    "Transparency: use **Download CSV** under each chart or table to replicate numbers offline."
)

st.divider()

st.subheader("Input parameters")
st.caption("Selections below mirror the **sidebar**.")
p1, p2, p3 = st.columns(3)
p1.write(f"**Country:** {country} {country_to_flag(country)}")
p2.write(f"**Program:** {antigen.replace('coverage__', '')}")
p3.write(f"**Windows:** {pre_years} yrs before / {post_years} yrs after reference **{campaign_start}**")

st.divider()

st.subheader("Visual analysis")
st.markdown(f"#### {country} — {antigen.replace('coverage__', '')}")

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=series["year"],
        y=series["coverage_pct"],
        mode="lines+markers",
        name="Coverage %",
        line=dict(color="#0052CC", width=2),
        marker=dict(size=6),
    )
)
fig.add_vrect(
    x0=campaign_start - pre_years,
    x1=campaign_start,
    fillcolor="rgba(0,82,204,0.12)",
    layer="below",
    line_width=0,
    annotation_text="Before window",
    annotation_position="top left",
)
fig.add_vrect(
    x0=campaign_start,
    x1=campaign_start + post_years,
    fillcolor="rgba(37,56,88,0.10)",
    layer="below",
    line_width=0,
    annotation_text="After window",
    annotation_position="top right",
)
fig.add_vline(
    x=campaign_start,
    line_dash="dash",
    line_color="#C62828",
    annotation_text=f"Reference {campaign_start}",
    annotation_position="bottom right",
)
_axis_bold = dict(tickangle=0, tickfont=dict(size=13, color="#253858", family="Inter, Segoe UI, sans-serif"))
fig.update_layout(
    title="Coverage over time",
    xaxis_title="Year",
    yaxis_title="Coverage (%)",
    xaxis=dict(
        title=dict(font=dict(size=14, color="#253858", family="Inter, Segoe UI, sans-serif")),
        **_axis_bold,
    ),
    yaxis=dict(
        range=[0, 100],
        title=dict(font=dict(size=14, color="#253858", family="Inter, Segoe UI, sans-serif")),
        tickfont=dict(size=12, color="#334155", family="Inter, Segoe UI, sans-serif"),
    ),
    hovermode="x unified",
    template="plotly_white",
    height=480,
)
st.plotly_chart(fig, use_container_width=True)
st.download_button(
    "Download time series CSV (chart data)",
    data=series.to_csv(index=False).encode("utf-8"),
    file_name=f"{country}_{antigen}_timeseries.csv".replace(" ", "_").replace("/", "-"),
    mime="text/csv",
)

st.markdown("#### Statistical comparison (Welch t-test)")
before_vals = series[
    (series["year"] >= campaign_start - pre_years) & (series["year"] <= campaign_start - 1)
]["coverage_pct"]
after_vals = series[
    (series["year"] >= campaign_start) & (series["year"] <= campaign_start + post_years)
]["coverage_pct"]

if len(before_vals) > 1 and len(after_vals) > 1:
    t_stat, p_val = ttest_ind(before_vals, after_vals, equal_var=False)
    avg_before = float(before_vals.mean())
    avg_after = float(after_vals.mean())
    diff = avg_after - avg_before
    ci_before = mean_ci(before_vals)
    ci_after = mean_ci(after_vals)
    sig = p_val < 0.05
    lift_positive = diff > 0

    if sig and lift_positive:
        narrative_accent = COL_WIN
        bar_colors = [COL_BEFORE, COL_WIN]
    elif sig and not lift_positive:
        narrative_accent = COL_CAUTION
        bar_colors = [COL_WIN, COL_CAUTION]
    else:
        narrative_accent = COL_NEUTRAL
        bar_colors = [COL_BEFORE, COL_AFTER]

    win_row = (
        '<div class="wv-kpi-row">'
        + _kpi_card_html(
            "Mean · before window",
            f"{avg_before:.1f}%",
            f"95% CI: {ci_before[0]:.1f}% – {ci_before[1]:.1f}%",
            bar_colors[0],
        )
        + _kpi_card_html(
            "Mean · after window",
            f"{avg_after:.1f}%",
            f"95% CI: {ci_after[0]:.1f}% – {ci_after[1]:.1f}%",
            bar_colors[1],
        )
        + _kpi_card_html(
            "Difference (after − before)",
            f"{diff:+.1f} pp",
            f"Welch two-sample t-test · p = {p_val:.4f}",
            narrative_accent,
        )
        + _kpi_card_html(
            "t-statistic",
            f"{t_stat:.3f}",
            "Effect direction follows sign of difference",
            COL_NEUTRAL,
        )
        + "</div>"
    )
    st.markdown(win_row, unsafe_allow_html=True)

    if sig:
        st.success(
            "**STATISTICALLY SIGNIFICANT** — Mean coverage differs between the **before** and **after** "
            f"windows at α = 0.05 (p = {p_val:.4f}). Interpretation still requires domain context "
            "(program scale, demographics, reporting changes)."
        )
    else:
        st.error(
            "**NOT STATISTICALLY SIGNIFICANT** — Mean shift is **inconclusive** at α = 0.05 "
            f"(p = {p_val:.4f}). **Recommendation:** widen windows, check data quality, or gather more years."
        )

    avg_df = pd.DataFrame(
        {
            "Period": ["Before", "After"],
            "Average (%)": [avg_before, avg_after],
            "ci_low": [ci_before[0], ci_after[0]],
            "ci_high": [ci_before[1], ci_after[1]],
        }
    )
    bar_fig = go.Figure()
    bar_fig.add_trace(
        go.Bar(
            x=avg_df["Period"],
            y=avg_df["Average (%)"],
            marker_color=bar_colors,
            text=[f"{avg_before:.1f}%", f"{avg_after:.1f}%"],
            textfont=dict(size=14, color="#253858", family="Inter, Segoe UI, sans-serif"),
            textposition="outside",
            error_y=dict(
                type="data",
                symmetric=False,
                array=[ci_before[1] - avg_before, ci_after[1] - avg_after],
                arrayminus=[avg_before - ci_before[0], avg_after - ci_after[0]],
                visible=True,
                thickness=2.5,
                color="#253858",
            ),
            name="Mean %",
        )
    )
    bar_fig.update_layout(
        title="Mean coverage by window — 95% confidence intervals",
        yaxis=dict(range=[0, 100], title=dict(font=dict(size=14, color="#253858")), tickfont=dict(size=12, color="#334155")),
        xaxis=dict(
            title=dict(text="Window", font=dict(size=14, color="#253858")),
            tickangle=0,
            tickfont=dict(size=15, color="#253858", family="Inter, Segoe UI, sans-serif"),
            categoryorder="array",
            categoryarray=["Before", "After"],
        ),
        template="plotly_white",
        height=420,
        showlegend=False,
    )
    st.plotly_chart(bar_fig, use_container_width=True)

    chip_b, chip_a = bar_colors[0], bar_colors[1]
    if sig and lift_positive:
        insight_lead = (
            f"After <strong>{campaign_start}</strong>, mean coverage runs about <strong>{diff:+.1f} pp</strong> "
            f"higher than the pre-window average — a statistically discernible shift for <strong>{country}</strong>."
        )
        insight_body = (
            "Use this as a <strong>monitoring signal</strong>, not proof of causality. Next: validate with "
            "program milestones, denominator changes, and subnational slices; export CSVs for audit."
        )
    elif sig and not lift_positive:
        insight_lead = (
            f"Mean coverage in the <strong>after</strong> window is <strong>{abs(diff):.1f} pp</strong> "
            f"below the <strong>before</strong> window — statistically significant at α = 0.05."
        )
        insight_body = (
            "Investigate whether this reflects policy pullback, stock-outs, survey changes, or demographic shifts. "
            "Pair with external program data before concluding program failure."
        )
    else:
        insight_lead = (
            "The two windows <strong>do not separate</strong> clearly at α = 0.05 — treat the apparent gap "
            f"({diff:+.1f} pp) as <strong>noise-level</strong> until you add power or tighten hypotheses."
        )
        insight_body = (
            "Next: widen or shift the reference year, confirm <strong>n per window</strong>, and document "
            "assumptions for stakeholders who need a clear go / no-go."
        )

    st.markdown(
        f"""
<div class="wv-insight-box" style="border-left-color:{narrative_accent};">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">
    <span style="font-weight:800;font-size:1rem;color:{chip_b};letter-spacing:0.04em;">BEFORE</span>
    <span style="color:#cbd5e1;font-weight:600;">·</span>
    <span style="font-weight:800;font-size:1rem;color:{chip_a};letter-spacing:0.04em;">AFTER</span>
  </div>
  <div class="wv-insight-kicker" style="color:{narrative_accent};">Executive insight</div>
  <div class="wv-insight-lead">{insight_lead}</div>
  <div class="wv-insight-body">{insight_body}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.download_button(
        "Download window means CSV",
        data=avg_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{country}_{antigen}_window_means.csv".replace(" ", "_"),
        mime="text/csv",
    )
else:
    st.warning("Not enough observations in one or both windows for a t-test. Adjust the campaign window in the sidebar.")

st.divider()

st.subheader("Raw data")
st.dataframe(series, use_container_width=True, hide_index=True)
st.download_button(
    label="Download full series CSV",
    data=series.to_csv(index=False).encode("utf-8"),
    file_name=f"{country}_{antigen}_coverage.csv".replace(" ", "_").replace("/", "-"),
    mime="text/csv",
)

with st.expander("Technical methodology & assumptions"):
    st.markdown(
        """
- **ETL:** OWID vaccination coverage files normalized into SQLite (`run_etl` in repo). Refresh pulls latest upstream.
- **Welch t-test:** Compares independent samples with unequal variances; assumes approximate normality of annual means
  within each short window — sensitive to small *n* and autocorrelation across years.
- **Campaign window:** User-defined pre/post spans; not a causal identification strategy on its own.
- **CIs on means:** Standard error of the mean × t critical value (df = n−1 per window).
        """
    )

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Developer:** Sherriff Abdul-Hamid  \n"
    "[GitHub](https://github.com/S-ABDUL-AI) · "
    "[LinkedIn](https://www.linkedin.com/in/abdul-hamid-sherriff-08583354/)"
)
