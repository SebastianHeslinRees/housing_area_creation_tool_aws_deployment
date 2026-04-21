# Housing Market Areas Dashboard

Housing Market Areas Dashboard: an interactive Dash app for generating Housing Market Areas from commuting and migration flows.

## Features
- Existing GLA-styled layout, sidebar, dark mode and responsive behaviour preserved
- HMA generation using commuting self-containment and migration self-containment thresholds
- Interactive HMA map, summary metrics, largest-HMA chart and CSV download

## Data files
- A geometry source with `LAD23CD`, `LAD23NM` and valid boundary geometry
- Commuting flows CSV, default path `flow_data/commuting_flow_la_2023.csv`
- Migration flows CSV, default path `flow_data/migration_flow_la_2023.csv`

## Optional Environment Variables
- `HMA_GEOMETRY_FILE` — override the default geometry source
- `HMA_COMMUTING_FLOW_FILE` — override the default commuting flow CSV path
- `HMA_MIGRATION_FLOW_FILE` — override the default migration flow CSV path
- `HMA_PRECOMPUTED_S3_PREFIX` — S3 prefix containing precomputed threshold outputs for the deployed app
- `HMA_DATASET_VERSION` — dataset version folder to read from under the precomputed S3 prefix

## App Modes
- [app_local.py](/Users/user1/Documents/household_zone_dashboard_update/app_local.py) keeps the original local-compute version of the dashboard.
- [app.py](/Users/user1/Documents/household_zone_dashboard_update/app.py) loads precomputed HMA outputs from S3 at runtime.

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

3. Run locally with enviroment variable (development server).

Before the first local run in a new shell, authenticate with AWS SSO

```bash
python
export AWS_PROFILE= XXX AWS_REGION= XXX HMA_PRECOMPUTED_S3_PREFIX=s3://dpa-population-projection-data/dpa-apps/housing_zones_precomputed HMA_DATASET_VERSION=2026-04-15 PORT=8050 && /opt/anaconda3/envs/env/bin/python app.py
```

Open http://127.0.0.1:8050 in your browser.


## Production / App Runner
The repository contains an `apprunner.yaml` configured to run the app with Gunicorn on port `8080`.

Use an App Runner instance role with read access to:

```text
s3://dpa-population-projection-data/dpa-apps/housing_zones_precomputed/*
```

## Glue Precompute Job
Use [scripts/precompute_hmas_glue.py](scripts/precompute_hmas_glue.py) to precompute all threshold combinations in AWS Glue instead of running the HMA algorithm inside the Dash callback, less commute, faster and cheaper.

Example arguments:

```bash
spark-submit scripts/precompute_hmas_glue.py \
	--commuting-s3-uri s3://dpa-population-projection-data/dpa-apps/housing_zones_data/commuting_flow_la_2023.csv \
	--migration-s3-uri s3://dpa-population-projection-data/dpa-apps/housing_zones_data/migration_flow_la_2023.csv \
	--geometry-s3-uri s3://dpa-population-projection-data/dpa-apps/housing_zones_data/Local_Authority_Districts_December_2023_Boundaries_UK_BGC_2537431731774104276_simplified.geojson \
	--output-s3-prefix s3://dpa-population-projection-data/dpa-apps/housing_zones_precomputed \
	--dataset-version 2026-04-15
```

For a single validation run before computing all 289 threshold pairs, add:

```bash
	--single-commuting-threshold 0.725 \
	--single-migration-threshold 0.550
```

To generate the full threshold grid used by the sliders, remove both single-threshold arguments as stated above. With the default settings this computes:

- commuting thresholds from `0.500` to `0.900` in steps of `0.025`
- migration thresholds from `0.300` to `0.700` in steps of `0.025`
- `289` total threshold combinations

Data folder structure:

```text
housing_zones_precomputed/
  dataset_version=2026-04-15/
    commuting_threshold=0.500/
      migration_threshold=0.300/
      migration_threshold=0.325/
      migration_threshold=0.350/...
```

The deployed app expects each threshold folder to contain:

```text
summary.json
hma_boundaries.geojson.gz
assignments.csv
```

Where:
- `summary.json` contains the summary metrics and largest-HMA data for the app display
- `hma_boundaries.geojson.gz` contains the geometries of the resulting HMAs
- `assignments.csv` contains the LA-to-HMA assignments for data users to download and check
- `assignments.parquet` more efficient storage for the app use

## Architecture Diagrams
The diagrams below explain the deployment and runtime flow.

### Detailed HMA Deployment Architecture

The Python Dash app in `app.py` reads precomputed outputs from S3. The Glue script in `scripts/precompute_hmas_glue.py` uses PySpark for distributed reads and writes, then runs the core HMA merge logic in Python before saving the result set. The Dockerfile builds the runtime container, ECR stores it, and App Runner hosts it. The YAML file documents the source-based deployment path.

```mermaid
flowchart LR
	subgraph LocalRepo[Local repository]
		A1[app.py<br/>Python<br/>Dash + boto3 + GeoPandas]
		A2[app_local.py<br/>Python<br/>Local compute fallback]
		A3[scripts/precompute_hmas_glue.py<br/>Python + PySpark<br/>Batch precompute job]
		A4[Dockerfile<br/>Docker build recipe]
		A5[apprunner.yaml<br/>YAML deployment manifest]
		A6[requirements.txt<br/>Python dependency spec]
		A7[assets/styles.css<br/>CSS styling]
	end

	subgraph Packaging[Container packaging]
		B1[Docker build]
		B2[Linux container image]
		B3[ECR repository]
	end

	subgraph Batch[Batch compute layer]
		C1[AWS Glue job runtime]
		C2[Spark readers / reducers<br/>PySpark distributed stage]
		C3[HMA merge loop<br/>Python serial stage]
		C4[S3 output writer]
	end

	subgraph Storage[Storage layer]
		D1[S3 raw inputs<br/>commuting CSV<br/>migration CSV<br/>boundary GeoJSON]
		D2[S3 precomputed outputs<br/>dataset_version=...<br/>commuting_threshold=...<br/>migration_threshold=...]
		D3[summary.json]
		D4[assignments.csv / parquet]
		D5[hma_boundaries.geojson.gz]
	end

	subgraph Runtime[Serving layer]
		E1[App Runner service]
		E2[Gunicorn process]
		E3[Dash app from app.py]
		E4[Browser user]
	end

	subgraph IAM[IAM roles]
		F1[App Runner ECR access role]
		F2[App Runner instance role<br/>S3 read]
		F3[Glue execution role]
	end

	A4 --> B1
	A6 --> B1
	A1 --> B1
	A7 --> B1
	B1 --> B2 --> B3
	F1 --> B3
	B3 --> E1
	E1 --> E2 --> E3
	E4 --> E3
	F2 --> D2
	E3 --> D2

	A3 --> C1
	F3 --> C1
	D1 --> C2
	C1 --> C2 --> C3 --> C4 --> D2
	D2 --> D3
	D2 --> D4
	D2 --> D5

	A5 -.used in source-based App Runner path.-> E1
	A2 -.local-only development path.-> E4
```

### Detailed Runtime Flow

This sequence shows what happens after deployment. The expensive work does not happen inside App Runner. The browser sends threshold values, the Python callback builds the S3 path, reads the precomputed files, and returns the map, metrics, and tables.

```mermaid
sequenceDiagram
	participant U as User
	participant W as Browser UI
	participant AR as App Runner
	participant G as Gunicorn
	participant APP as app.py (Python)
	participant S3 as S3 precomputed outputs
	participant GL as Glue job (PySpark + Python)

	Note over GL,S3: Precompute stage happens before app usage
	GL->>S3: write summary.json per threshold pair
	GL->>S3: write assignments.csv/parquet per threshold pair
	GL->>S3: write hma_boundaries.geojson.gz per threshold pair

	U->>W: Move commuting / migration sliders
	U->>W: Click Run HMA algorithm
	W->>AR: HTTP request / Dash callback
	AR->>G: Route request to container process
	G->>APP: Execute callback in Python
	APP->>APP: Build S3 prefix from selected thresholds
	APP->>S3: Read summary.json
	APP->>S3: Read assignments.csv if present
	APP->>S3: Read hma_boundaries.geojson.gz
	APP->>APP: Build figures and summary tables
	APP-->>G: Return callback payload
	G-->>AR: HTTP response
	AR-->>W: Updated map, chart, metrics, preview
	W-->>U: Render HMA result for selected thresholds
```

For a standalone export-friendly version, open `architecture_diagrams.html`, can print to PDF or take a screenshot.

## Troubleshooting
- If the app loads but the algorithm cannot run, the commuting and migration flow CSVs are missing or do not contain the expected columns.
- Geometry inputs must contain `LAD23CD` and valid boundary geometry.
- If you are using Python 3.12, install from the updated `requirements.txt` before running the app.

