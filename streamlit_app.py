# streamlit_app.py
import sqlite3
import pandas as pd
import streamlit as st
import requests, io, os
from scipy.stats import ttest_ind, sem, t
import pycountry
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from etl_pipeline import run_etl

# Run ETL automatically when app starts
run_etl()


DB_PATH = "vaccination.db"
TABLE_RAW = "owid_raw"
TABLE_CLEAN = "immunization"
OWID_URL = (
    "https://ourworldindata.org/grapher/global-vaccination-coverage.csv"
    "?v=1&csvType=full&useColumnShortNames=true"
)

# -----------------------------
# HELPER: Get emoji flag from country name
# -----------------------------
def country_to_flag(country_name: str) -> str:
    try:
        country = pycountry.countries.lookup(country_name)
        return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country.alpha_2)
    except Exception:
        return "🏳️"

# -----------------------------
# HELPER: Compute 95% CI
# -----------------------------
def mean_ci(data, confidence=0.95):
    if len(data) < 2:
        return np.nan, np.nan
    mean = np.mean(data)
    se = sem(data, nan_policy="omit")
    h = se * t.ppf((1 + confidence) / 2, len(data) - 1)
    return mean - h, mean + h

# -----------------------------
# ETL FUNCTION (ALL COUNTRIES)
# -----------------------------
def run_etl():
    resp = requests.get(OWID_URL, timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content))

    coverage_cols = [c for c in df.columns if c.startswith("coverage__")]
    df_tidy = df.melt(
        id_vars=["Entity", "Year"],
        value_vars=coverage_cols,
        var_name="antigen",
        value_name="coverage_pct",
    ).dropna()
    df_tidy = df_tidy.rename(columns={"Entity": "country", "Year": "year"})
    df_tidy = df_tidy[df_tidy["year"].between(1980, 2100)]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    df.to_sql(TABLE_RAW, conn, if_exists="replace", index=False)
    cur.execute(f"DROP TABLE IF EXISTS {TABLE_CLEAN};")
    cur.execute(
        f"""
        CREATE TABLE {TABLE_CLEAN} (
            country TEXT,
            antigen TEXT,
            year INTEGER,
            coverage_pct REAL,
            PRIMARY KEY (country, antigen, year)
        );
        """
    )
    df_tidy.to_sql(TABLE_CLEAN, conn, if_exists="append", index=False)
    conn.commit()
    conn.close()
    return True

# -----------------------------
# STREAMLIT CONFIG
# -----------------------------
st.set_page_config(page_title="World Vaccination Coverage ETL", layout="wide")
st.title("World Vaccination Coverage - ETL & Analysis")

# Sidebar inputs
st.sidebar.header("Configuration")
campaign_start = st.sidebar.number_input("Campaign start year", value=2017)
pre_years = st.sidebar.number_input("Years before", value=5, min_value=1)
post_years = st.sidebar.number_input("Years after", value=5, min_value=1)

# -----------------------------
# BOOTSTRAP DB (if missing)
# -----------------------------
if not os.path.exists(DB_PATH):
    with st.spinner("Running initial ETL..."):
        run_etl()
    st.success("Database initialized ✅")

# -----------------------------
# REFRESH DATA BUTTON
# -----------------------------
if st.sidebar.button("🔄 Refresh Data from OWID (All Countries)"):
    run_etl()
    st.success("ETL pipeline refreshed with all countries!")

# Developer Info
st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    ### 👨‍💻 About the Developer  
    **Sherriff Abdul-Hamid**  
    AI Engineer | Data Scientist | Economist  

    **Contact:**  
    [GitHub](https://github.com/S-ABDUL-AI) | 
    [LinkedIn](https://www.linkedin.com/in/abdul-hamid-sherriff-08583354/) |  
    📧 Sherriffhamid001@gmail.com
    """
)

# -----------------------------
# LOAD DATA
# -----------------------------
conn = sqlite3.connect(DB_PATH)
df_meta = pd.read_sql_query(
    f"SELECT DISTINCT country, antigen FROM {TABLE_CLEAN} ORDER BY country, antigen;", conn
)
countries = sorted(df_meta["country"].unique())
country = st.selectbox(
    "Select Country", countries, index=countries.index("India") if "India" in countries else 0
)

antigens = sorted(df_meta[df_meta["country"] == country]["antigen"].unique())
antigen = st.selectbox("Select Antigen", antigens, index=0)

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

# -----------------------------
# ANALYSIS
# -----------------------------
if not series.empty:
    st.markdown(f"### {country} {country_to_flag(country)}")

    # Interactive line chart with shaded regions
    st.subheader("Coverage Over Time (Interactive)")
    fig = go.Figure()

    # Add line trace
    fig.add_trace(go.Scatter(
        x=series["year"], y=series["coverage_pct"],
        mode="lines+markers",
        name="Coverage (%)",
        line=dict(color="blue")
    ))

    # Shaded before region
    fig.add_vrect(
        x0=campaign_start - pre_years, x1=campaign_start,
        fillcolor="lightblue", opacity=0.3,
        layer="below", line_width=0,
        annotation_text="Before", annotation_position="top left"
    )

    # Shaded after region
    fig.add_vrect(
        x0=campaign_start, x1=campaign_start + post_years,
        fillcolor="lightgreen", opacity=0.3,
        layer="below", line_width=0,
        annotation_text="After", annotation_position="top right"
    )

    # Campaign line
    fig.add_vline(
        x=campaign_start, line_dash="dash", line_color="red",
        annotation_text=f"Campaign {campaign_start}", annotation_position="bottom right"
    )

    fig.update_layout(
        title=f"{country} — {antigen} coverage over time",
        xaxis_title="Year",
        yaxis_title="Coverage (%)",
        yaxis=dict(range=[0, 100])
    )
    st.plotly_chart(fig, use_container_width=True)

    # -----------------------------
    # T-Test
    # -----------------------------
    st.subheader("Statistical Test (t-test)")
    before_vals = series[
        (series["year"] >= campaign_start - pre_years) & (series["year"] <= campaign_start - 1)
    ]["coverage_pct"]
    after_vals = series[
        (series["year"] >= campaign_start) & (series["year"] <= campaign_start + post_years)
    ]["coverage_pct"]

    if len(before_vals) > 1 and len(after_vals) > 1:
        t_stat, p_val = ttest_ind(before_vals, after_vals, equal_var=False)
        st.write(f"**t-statistic:** {t_stat:.3f}")
        st.write(f"**p-value:** {p_val:.5f}")

        # Non-technical explanation
        if p_val < 0.05:
            st.success(
                "✅ The p-value is below 0.05 → This means the difference in coverage "
                "before vs after the campaign is **statistically significant**. "
                "In simple terms: the campaign likely made a real difference."
            )
        else:
            st.warning(
                "ℹ️ The p-value is above 0.05 → This means there is **no strong evidence** "
                "that coverage changed because of the campaign. The change might just be random."
            )

        # -----------------------------
        # Bar chart comparison with CI
        # -----------------------------
        st.subheader("Average Coverage Before vs After (with 95% CI)")
        avg_before = before_vals.mean()
        avg_after = after_vals.mean()
        diff = avg_after - avg_before

        ci_before = mean_ci(before_vals)
        ci_after = mean_ci(after_vals)

        avg_df = pd.DataFrame({
            "Period": ["Before Campaign", "After Campaign"],
            "Average Coverage (%)": [avg_before, avg_after],
            "Lower CI": [ci_before[0], ci_after[0]],
            "Upper CI": [ci_before[1], ci_after[1]],
        })

        bar_fig = px.bar(
            avg_df,
            x="Period",
            y="Average Coverage (%)",
            color="Period",
            text="Average Coverage (%)",
            error_y=avg_df["Upper CI"] - avg_df["Average Coverage (%)"],
            error_y_minus=avg_df["Average Coverage (%)"] - avg_df["Lower CI"],
            title="Comparison of Average Vaccination Coverage (with 95% CI)",
        )
        bar_fig.update_traces(texttemplate='%{text:.1f}%', textposition="outside")
        bar_fig.update_layout(showlegend=False, yaxis=dict(range=[0, 100]))
        st.plotly_chart(bar_fig, use_container_width=True)

        # Highlight difference
        if diff >= 0:
            st.success(f"📈 Coverage increased by **{diff:.1f}% points** after the campaign.")
        else:
            st.error(f"📉 Coverage decreased by **{abs(diff):.1f}% points** after the campaign.")

    else:
        st.warning("Not enough data points in one of the periods to run t-test.")

    # -----------------------------
    # Raw Data + Download
    # -----------------------------
    st.subheader("Raw Data")
    st.dataframe(series)

    csv = series.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download CSV",
        data=csv,
        file_name=f"{country}_{antigen}_coverage.csv".replace(" ", "_"),
        mime="text/csv",
    )

conn.close()
