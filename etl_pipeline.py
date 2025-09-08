# etl_pipeline.py
"""
ETL Pipeline for Global Vaccination Coverage (OWID/WUENIC)
- Extracts global vaccination coverage data (all countries, all antigens).
- Loads into SQLite DB (vaccination.db).
- If --country and --antigen are provided:
    -> runs before/after campaign analysis with t-test + CI
    -> saves CSV + PNG for GitHub Actions artifacts.
"""

import os
import io
import argparse
import requests
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import ttest_ind, sem, t

# -----------------------------
# CONFIG
# -----------------------------
DB_PATH = "vaccination.db"
TABLE_RAW = "owid_raw"
TABLE_CLEAN = "immunization"

OWID_URL = (
    "https://ourworldindata.org/grapher/global-vaccination-coverage.csv"
    "?v=1&csvType=full&useColumnShortNames=true"
)


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
    print("🔹 Extract: downloading OWID coverage CSV …")
    resp = requests.get(OWID_URL, timeout=60)
    resp.raise_for_status()
    df = pd.read_csv(io.BytesIO(resp.content))

    print("🔹 Transform: tidying dataset …")
    coverage_cols = [c for c in df.columns if c.startswith("coverage__")]
    df_tidy = df.melt(
        id_vars=["Entity", "Year"],
        value_vars=coverage_cols,
        var_name="antigen",
        value_name="coverage_pct",
    ).dropna()
    df_tidy = df_tidy.rename(columns={"Entity": "country", "Year": "year"})
    df_tidy = df_tidy[df_tidy["year"].between(1980, 2100)]

    print("🔹 Load: writing to SQLite …")
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

    print("✅ ETL complete. Database refreshed.")
    return True


# -----------------------------
# ANALYSIS (Optional)
# -----------------------------
def run_analysis(country, antigen, start_year, pre_years, post_years):
    conn = sqlite3.connect(DB_PATH)

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

    if series.empty:
        print(f"⚠️ No data found for {country} / {antigen}")
        return

    before_vals = series[
        (series["year"] >= start_year - pre_years)
        & (series["year"] <= start_year - 1)
    ]["coverage_pct"]
    after_vals = series[
        (series["year"] >= start_year)
        & (series["year"] <= start_year + post_years)
    ]["coverage_pct"]

    print(f"\n📊 Analysis for {country} / {antigen}")
    print(f"   Period: {start_year-pre_years}–{start_year-1} vs {start_year}–{start_year+post_years}")

    if len(before_vals) > 1 and len(after_vals) > 1:
        t_stat, p_val = ttest_ind(before_vals, after_vals, equal_var=False)
        print(f"   t-statistic = {t_stat:.3f}")
        print(f"   p-value     = {p_val:.5f}")

        ci_before = mean_ci(before_vals)
        ci_after = mean_ci(after_vals)
        avg_before = before_vals.mean()
        avg_after = after_vals.mean()
        diff = avg_after - avg_before

        print(f"   Avg Before = {avg_before:.1f}% (95% CI: {ci_before[0]:.1f}–{ci_before[1]:.1f})")
        print(f"   Avg After  = {avg_after:.1f}% (95% CI: {ci_after[0]:.1f}–{ci_after[1]:.1f})")
        print(f"   Difference = {diff:+.1f} percentage points")

        # Save CSV
        out_csv = f"coverage_{country}_{antigen}.csv".replace(" ", "_")
        series.to_csv(out_csv, index=False)
        print(f"   💾 Saved raw series → {out_csv}")

        # Save plot
        plt.figure(figsize=(10, 5))
        plt.plot(series["year"], series["coverage_pct"], marker="o", label="Coverage (%)")
        plt.axvline(start_year, linestyle="--", color="red", label=f"Campaign {start_year}")
        plt.axvspan(start_year - pre_years, start_year, color="lightblue", alpha=0.3, label="Before")
        plt.axvspan(start_year, start_year + post_years, color="lightgreen", alpha=0.3, label="After")
        plt.title(f"{country} — {antigen} coverage over time")
        plt.xlabel("Year")
        plt.ylabel("Coverage (%)")
        plt.ylim(0, 100)
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        out_png = f"plot_{country}_{antigen}.png".replace(" ", "_")
        plt.savefig(out_png, dpi=144, bbox_inches="tight")
        print(f"   💾 Saved plot → {out_png}")

    else:
        print("⚠️ Not enough data points for before/after t-test.")

    conn.close()


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vaccination Coverage ETL & Analysis")
    parser.add_argument("--country", type=str, help="Country to analyze (optional)")
    parser.add_argument("--antigen", type=str, help="Antigen code to analyze (optional)")
    parser.add_argument("--start-year", type=int, default=2017, help="Campaign start year")
    parser.add_argument("--pre-years", type=int, default=5, help="Years before campaign")
    parser.add_argument("--post-years", type=int, default=5, help="Years after campaign")
    args = parser.parse_args()

    run_etl()

    if args.country and args.antigen:
        run_analysis(args.country, args.antigen, args.start_year, args.pre_years, args.post_years)
