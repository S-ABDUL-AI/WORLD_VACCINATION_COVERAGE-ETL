# streamlit_app.py — World Vaccination Coverage (OWID) ETL & analysis
import io
import os
import sqlite3

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import requests
import streamlit as st
from scipy.stats import sem, t, ttest_ind

from etl_pipeline import DB_PATH, TABLE_CLEAN, run_etl

# -----------------------------------------------------------------------------
# Streamlit must call set_page_config before other Streamlit commands
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="World Vaccination Coverage",
    layout="wide",
    page_icon="💉",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.2rem; }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; }
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


def mean_ci(data, confidence=0.95):
    if len(data) < 2:
        return np.nan, np.nan
    mean = np.mean(data)
    se = sem(data, nan_policy="omit")
    h = se * t.ppf((1 + confidence) / 2, len(data) - 1)
    return mean - h, mean + h


st.title("💉 World Vaccination Coverage")
st.caption(
    "ETL from OWID global coverage data — explore trends, compare before/after a campaign year, "
    "and export results for reporting."
)

# Sidebar
st.sidebar.header("Campaign window")
campaign_start = st.sidebar.number_input("Campaign / reference year", value=2017, min_value=1980, max_value=2030)
pre_years = st.sidebar.number_input("Years before", value=5, min_value=1, max_value=30)
post_years = st.sidebar.number_input("Years after", value=5, min_value=1, max_value=30)

if st.sidebar.button("🔄 Refresh data from OWID", type="primary"):
    with st.spinner("Refreshing full dataset (may take a minute)…"):
        try:
            run_etl()
            st.session_state.etl_ok = True
            st.success("Database updated.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(str(e))

st.sidebar.markdown("---")
st.sidebar.caption(
    "Data: [Our World in Data — vaccination coverage](https://ourworldindata.org/vaccination). "
    "This dashboard is for analysis and education, not clinical or policy decisions."
)

# Bootstrap DB only on demand.
# Streamlit Cloud can time out during cold starts if we download & build at import time.
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

# Load metadata
try:
    conn = sqlite3.connect(DB_PATH)
    df_meta = pd.read_sql_query(
        f"SELECT DISTINCT country, antigen FROM {TABLE_CLEAN} ORDER BY country, antigen;",
        conn,
    )
except Exception as e:
    st.error(f"Could not read database: {e}")
    st.stop()

if df_meta.empty:
    st.warning("No rows in the clean table. Click **Refresh data from OWID** in the sidebar.")
    conn.close()
    st.stop()

countries = sorted(df_meta["country"].unique())
default_idx = countries.index("India") if "India" in countries else 0
country = st.selectbox("Country", countries, index=default_idx)

antigens = sorted(df_meta[df_meta["country"] == country]["antigen"].unique())
antigen = st.selectbox("Antigen / vaccine program", antigens, index=0)

series = pd.read_sql_query(
    f"""
    SELECT year, coverage_pct
    FROM {TABLE_CLEAN}
    WHERE country = ? AND antigen = ?
    ORDER BY year;
    """,
    conn,
    params=(country, antigen),
)
conn.close()

if series.empty:
    st.info("No time series for this selection.")
    st.stop()

latest = float(series["coverage_pct"].iloc[-1])
earliest = float(series["coverage_pct"].iloc[0])
yr_min, yr_max = int(series["year"].min()), int(series["year"].max())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Years covered", f"{yr_min}–{yr_max}")
c2.metric("Latest coverage", f"{latest:.1f}%")
c3.metric("First year in series", f"{earliest:.1f}%")
delta = latest - earliest
c4.metric("Change (first→last)", f"{delta:+.1f} pp")

st.subheader(f"{country} {country_to_flag(country)} — {antigen.replace('coverage__', '')}")

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=series["year"],
        y=series["coverage_pct"],
        mode="lines+markers",
        name="Coverage %",
        line=dict(color="#2563eb", width=2),
        marker=dict(size=6),
    )
)
fig.add_vrect(
    x0=campaign_start - pre_years,
    x1=campaign_start,
    fillcolor="rgba(59,130,246,0.15)",
    layer="below",
    line_width=0,
    annotation_text="Before window",
    annotation_position="top left",
)
fig.add_vrect(
    x0=campaign_start,
    x1=campaign_start + post_years,
    fillcolor="rgba(34,197,94,0.15)",
    layer="below",
    line_width=0,
    annotation_text="After window",
    annotation_position="top right",
)
fig.add_vline(
    x=campaign_start,
    line_dash="dash",
    line_color="#dc2626",
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

st.subheader("Statistical comparison (Welch t-test)")
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

    m1, m2, m3 = st.columns(3)
    m1.metric("Mean before", f"{avg_before:.1f}%")
    m2.metric("Mean after", f"{avg_after:.1f}%")
    m3.metric("Difference", f"{diff:+.1f} pp", delta=f"p={p_val:.4f}")

    st.write(f"**t-statistic:** {t_stat:.3f}  ·  **p-value:** {p_val:.5f}")

    if p_val < 0.05:
        st.success(
            "At α = 0.05, the difference between the two windows is **statistically significant**. "
            "Interpret causality with care — many factors affect vaccination coverage."
        )
    else:
        st.warning(
            "No strong evidence of a difference between windows at α = 0.05. "
            "Overlap in years or noise can hide real effects; widen windows or check data quality."
        )

    ci_before = mean_ci(before_vals)
    ci_after = mean_ci(after_vals)
    avg_df = pd.DataFrame(
        {
            "Period": ["Before window", "After window"],
            "Average (%)": [avg_before, avg_after],
        }
    )
    bar_fig = px.bar(
        avg_df,
        x="Period",
        y="Average (%)",
        color="Period",
        color_discrete_map={"Before window": "#93c5fd", "After window": "#86efac"},
        text="Average (%)",
        title="Mean coverage in each window (95% CI: before "
        f"{ci_before[0]:.1f}–{ci_before[1]:.1f}%, after {ci_after[0]:.1f}–{ci_after[1]:.1f}%)",
    )
    bar_fig.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
    bar_fig.update_layout(showlegend=False, yaxis=dict(range=[0, 100]), template="plotly_white", height=400)
    st.plotly_chart(bar_fig, use_container_width=True)
else:
    st.warning("Not enough observations in one or both windows for a t-test. Adjust the campaign window.")

st.subheader("Data table")
st.dataframe(series, use_container_width=True, hide_index=True)
csv_bytes = series.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download CSV",
    data=csv_bytes,
    file_name=f"{country}_{antigen}_coverage.csv".replace(" ", "_").replace("/", "-"),
    mime="text/csv",
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Developer:** Sherriff Abdul-Hamid  \n"
    "[GitHub](https://github.com/S-ABDUL-AI) · "
    "[LinkedIn](https://www.linkedin.com/in/abdul-hamid-sherriff-08583354/)"
)
