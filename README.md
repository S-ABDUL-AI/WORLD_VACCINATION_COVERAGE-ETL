
# 🌍 World Vaccination Coverage — ETL & Dashboard

## 📌 Background
Vaccination coverage is one of the most important indicators for monitoring public health and child survival globally. UNICEF and WHO collect data to assess how immunization programs are performing across countries. To make this data accessible and actionable, we built an **ETL pipeline + interactive dashboard** that automates data updates and enables dynamic exploration.

## 🛑 Problem Statement
- Immunization data is often scattered and updated periodically.  
- Analysts and decision-makers need a **single source of truth** that stays up to date.  
- Manual refreshing of datasets introduces delays and errors.  

## 🎯 Objectives
1. Automate the **extraction, cleaning, and loading** of vaccination coverage data.  
2. Store cleaned data in a **SQLite database** for reproducibility.  
3. Provide an **interactive dashboard** (Streamlit) for visualizing country-specific coverage trends.  
4. Enable **continuous integration / continuous deployment (CI/CD)** via GitHub Actions to refresh datasets automatically.  

## ⚙️ System Architecture
1. **ETL Pipeline (`etl_pipeline.py`)**  
   - Extracts vaccination coverage data from [Our World in Data (OWID)](https://ourworldindata.org/).  
   - Cleans and transforms data (filters by antigen and country).  
   - Loads cleaned results into `vaccination.db`.  

2. **Dashboard (`streamlit_app.py`)**  
   - Reads data directly from `vaccination.db`.  
   - Provides interactive filtering by **country** and **antigen**.  
   - Visualizes vaccination trends over time.
     
3. **Automation (GitHub Actions)**  
   - Workflow runs weekly (every Monday at 03:00 UTC).  
   - Refreshes `vaccination.db` with the latest OWID data.  
   - Saves **artifacts** (`vaccination.db`, cleaned CSVs, plots) for download after each run.  

## 🚀 Features
- 📊 Country & antigen–specific vaccination trends  
- 🗂 SQLite database backend for structured storage  
- ⚡ Automated refresh with GitHub Actions (CI/CD)  
- 📦 Downloadable outputs (DB, CSV, plots) directly from GitHub Artifacts  
- 🌐 Reproducible & lightweight (uses `pandas`, `sqlite3`, `matplotlib`, `scipy`, `streamlit`)
  

## 🛠️ Installation & Setup

Clone the repo:
```bash
git clone https://github.com/S-ABDUL-AI/World_Vaccination_Coverage-ETL.git
cd World_Vaccination_Coverage-ETL
install 
🤖 CI/CD with GitHub Actions
Workflow file: .github/workflows/refresh_vaccination_db.yml

Triggers:

Weekly (cron job every Monday 03:00 UTC)
Manual trigger from GitHub Actions tab
Outputs available in GitHub → Actions → Artifacts:
vaccination.db (latest SQLite database)
clean_*.csv (cleaned datasets)
plot_*.png (visualizations)


 📈 Future Enhancements

Add before/after campaign statistical analysis (t-tests, confidence intervals).
Deploy Streamlit app publicly (Streamlit Cloud, Heroku, or Docker).
Extend pipeline to cover multiple countries and antigens simultaneously.


👨‍💻 Author

Sherriff Abdul-Hamid
Repository: World_Vaccination_Coverage-ETL
