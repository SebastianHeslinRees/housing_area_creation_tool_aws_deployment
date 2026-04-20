# Architecture Diagrams

This page explains the deployment and runtime flow for the Housing Market Areas dashboard.

## Detailed HMA Deployment Architecture

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

## Detailed Runtime Flow

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

## Export Option

For a standalone export-friendly page, open `architecture_diagrams.html` locally in a browser or VS Code preview and print to PDF or take a screenshot.