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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"]  {
        font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif !important;
    }
    .block-container { padding-top: 1rem; max-width: 100%; }
    div[data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 600; color: #253858; }
    h1 { color: #0052CC !important; font-weight: 700 !important; }
    h2, h3 { color: #253858 !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
</style>
"""
st.markdown(_TRUST_CSS, unsafe_allow_html=True)


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

# --- Top KPI row ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Years covered", f"{yr_min}–{yr_max}", help="Observed calendar span in OWID clean table.")
k2.metric("Latest coverage", f"{latest:.1f}%", delta=f"{delta:+.1f} pp vs first year", delta_color="normal")
k3.metric("First year in series", f"{earliest:.1f}%")
k4.metric("Observations (years)", f"{n_obs:,}", help="GiveWell-style audit: count of annual data points.")

st.info(
    "**Transparency:** Use **Download CSV** under each table or chart to replicate numbers offline."
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
fig.update_layout(
    title="Coverage over time",
    xaxis_title="Year",
    yaxis_title="Coverage (%)",
    yaxis=dict(range=[0, 100]),
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

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Mean before", f"{avg_before:.1f}%", help=f"95% CI: [{ci_before[0]:.1f}%, {ci_before[1]:.1f}%]")
    m2.metric("Mean after", f"{avg_after:.1f}%", help=f"95% CI: [{ci_after[0]:.1f}%, {ci_after[1]:.1f}%]")
    m3.metric("Difference (after − before)", f"{diff:+.1f} pp", delta=f"p = {p_val:.4f}")
    m4.metric("t-statistic", f"{t_stat:.3f}")

    if p_val < 0.05:
        st.success(
            "**Signal:** At α = 0.05, mean coverage differs between windows. "
            "Causality still requires domain review (program intensity, demographics, data gaps)."
        )
    else:
        st.warning(
            "**No strong evidence** of a mean shift at α = 0.05. Consider widening windows or checking coverage volatility."
        )

    avg_df = pd.DataFrame(
        {
            "Period": ["Before window", "After window"],
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
            marker_color=["#93c5fd", "#86efac"],
            text=[f"{avg_before:.1f}%", f"{avg_after:.1f}%"],
            textposition="outside",
            error_y=dict(
                type="data",
                symmetric=False,
                array=[ci_before[1] - avg_before, ci_after[1] - avg_after],
                arrayminus=[avg_before - ci_before[0], avg_after - ci_after[0]],
                visible=True,
                thickness=2,
                color="#253858",
            ),
            name="Mean %",
        )
    )
    bar_fig.update_layout(
        title="Mean coverage by window with 95% CI error bars",
        yaxis=dict(range=[0, 100]),
        template="plotly_white",
        height=400,
        showlegend=False,
    )
    st.plotly_chart(bar_fig, use_container_width=True)
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
