# Global Vaccination Coverage Explorer  
WHO Data Across 190+ Countries

Global Vaccination Coverage Explorer is a production style Streamlit app for vaccination program monitoring and policy prioritization using OWID based ETL data, trend analysis, and before/after window comparisons.

## Hero framing

**580 million children missed routine vaccinations in 2023. Where are the gaps?**

This app helps policy and program teams identify where coverage risk appears highest and where additional review or intervention may be needed.

## Target users

- Public health program managers
- WHO and UNICEF partner teams
- Government immunization planners
- Global health researchers and policy analysts

## What the app delivers

- Navy and gold McKinsey style UI
- Hero banner with decision framing
- Scope note with context and caveat
- KPI cards for executive snapshot
- Policy brief cards in Risk, Implication, Action format
- Plotly exhibits with clean styling and no gridlines
- Data table and CSV download
- McKinsey style downloadable PDF report
- Credentialed byline with cross portfolio links

## Data and ETL

The app uses:

- `etl_pipeline.py` to load and normalize OWID vaccination coverage data into SQLite (`vaccination.db`)
- `TABLE_CLEAN` records with fields:
  - `country`
  - `antigen`
  - `year`
  - `coverage_pct`

If the local database is missing, the app initializes it from ETL.

## Statistical method

The app compares pre and post windows around a selected reference year:

- Welch two sample t-test
- Window means
- Difference in percentage points
- Confidence interval support via SEM and t distribution

This is evidence support for policy review and does not establish causal effect by itself.

## Files delivered

- `global_vaccination_coverage_explorer_app.py` — complete redesigned app
- `report_generator.py` — PDF report engine with `build_report_bytes`
- `app.py` — launcher entrypoint
- `requirements.txt` — standardized dependency set

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## PDF report pattern

The app uses:

```python
try:
    from report_generator import build_report_bytes
    REPORT_AVAILABLE = True
except ImportError:
    REPORT_AVAILABLE = False
```

and provides:

- `Generate Report PDF`
- `Download PDF Report`

## Disclaimer

This app is decision support, not a replacement for national policy systems, country program verification, or final governance approval.  
Use outputs with local implementation context and partner review.
