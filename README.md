# UK Fertility Rate Dashboard

This repository now hosts the UK Fertility Rate Dashboard — an interactive Dash app for exploring Total Fertility Rate (TFR) and Age-Specific Fertility Rate (ASFR) by Local Authority.

## Features
- Interactive choropleth maps for TFR and ASFR
- Metric summary cards (TFR, comparison vs UK average, replacement level)
- ASFR trend charts by Local Authority and age

## Data files
- `tfr_merged.geojson` — TFR per LAD and year with geometry
- `asfr_merged.geojson` — ASFR per LAD, year and age with geometry

## Local Development
1. Create and activate a Python environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run locally (development server):

```bash
python app.py
```

Open http://127.0.0.1:8022 in your browser.

## Production / App Runner
The repository contains an `apprunner.yaml` configured to run the app with Gunicorn on port 8022:

```
gunicorn --bind 0.0.0.0:8022 --workers 1 --timeout 120 app:server
```

Ensure App Runner uses the provided `requirements.txt` so all dependencies are installed during build.

## Troubleshooting
- If maps or metrics show `No data`, check that the files above contain the expected columns (`year`, `LAD23NM`, `LAD23CD`, `fertility_rate`, `age`).
- For deployment issues, review App Runner logs and ensure the `PORT` environment variable matches `8022`.

## Notes
- The app exposes the WSGI `server` variable so Gunicorn can import `app:server`.
- If you want a different port, update both `app.py` (when running directly) and `apprunner.yaml`.
