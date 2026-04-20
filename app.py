"""Housing Market Areas dashboard entrypoint.

This app keeps the existing dashboard shell and styling while replacing the
fertility-specific functionality with Housing Market Areas (HMA) generation.
External commuting and migration flow files are configurable via environment
variables so the app can still start cleanly when those files are not yet
present in the workspace.
"""

import os
import gzip
import json
from io import StringIO
from pathlib import Path

import boto3
import dash
import dash_bootstrap_components as dbc
from botocore.exceptions import ClientError
from dash import Input, Output, State, dcc, html
import geopandas as gpd
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


PORT = int(os.environ.get("PORT", 8012))
DEFAULT_COMMUTING_FLOW = os.environ.get(
    "HMA_COMMUTING_FLOW_FILE",
    "flow_data/commuting_flow_la_2023.csv",
)
DEFAULT_MIGRATION_FLOW = os.environ.get(
    "HMA_MIGRATION_FLOW_FILE",
    "flow_data/migration_flow_la_2023.csv",
)
PRECOMPUTED_RESULTS_PREFIX = os.environ.get(
    "HMA_PRECOMPUTED_S3_PREFIX",
    "s3://dpa-population-projection-data/dpa-apps/housing_zones_precomputed",
)
DATASET_VERSION = os.environ.get("HMA_DATASET_VERSION")
S3_CLIENT = boto3.client("s3")

current_results = None
current_meta = None
current_assignments = None


def parse_css_colours(css_file="assets/styles.css"):
    """Parse CSS variables from stylesheet to avoid duplication."""
    colours = {}
    chart_colours = []
    chart_dark_colours = []
    map_light_colours = []
    map_dark_colours = []

    try:
        with open(css_file, "r", encoding="utf-8") as file_handle:
            for line in file_handle:
                line = line.strip()
                if line.startswith("--map-color-light-") and ":" in line:
                    map_light_colours.append(line.split(":", 1)[1].split(";", 1)[0].strip())
                elif line.startswith("--map-color-dark-") and ":" in line:
                    map_dark_colours.append(line.split(":", 1)[1].split(";", 1)[0].strip())
                elif line.startswith("--chart-dark-color-") and ":" in line:
                    chart_dark_colours.append(line.split(":", 1)[1].split(";", 1)[0].strip())
                elif line.startswith("--chart-color-") and ":" in line:
                    chart_colours.append(line.split(":", 1)[1].split(";", 1)[0].strip())
                elif line.startswith("--color-") and ":" in line:
                    key = line.split(":", 1)[0].replace("--color-", "").replace("-", "_")
                    colours[key] = line.split(":", 1)[1].split(";", 1)[0].strip()
    except FileNotFoundError:
        print(f"Warning: {css_file} not found, using fallback colours")

    if not colours:
        colours = {
            "primary": "#1e3a8a",
            "secondary": "#ea580c",
            "accent": "#3b82f6",
            "background": "#F8F9FA",
            "text": "#2C3E50",
            "warning": "#f59e0b",
            "card_bg": "#ffffff",
            "success": "#16a34a",
        }
    if not chart_colours:
        chart_colours = [
            "#1e3a8a",
            "#ea580c",
            "#3b82f6",
            "#10b981",
            "#f59e0b",
            "#8b5cf6",
            "#ec4899",
            "#06b6d4",
            "#ef4444",
            "#14b8a6",
        ]
    if not chart_dark_colours:
        chart_dark_colours = [
            "#93c5fd",
            "#fbbf24",
            "#60a5fa",
            "#34d399",
            "#fde68a",
            "#c4b5fd",
            "#f9a8d4",
            "#67e8f9",
            "#fca5a5",
            "#5eead4",
        ]
    if not map_light_colours:
        map_light_colours = ["#e8f0f8", "#a8c5e4", "#6a8fc0", "#3d5a80", "#1e3a5f"]
    if not map_dark_colours:
        map_dark_colours = ["#1e3a5f", "#4a6fa5", "#6a8fc0", "#a8c5e4", "#e8f0f8"]

    return colours, chart_colours, chart_dark_colours, map_light_colours, map_dark_colours


COLORS, CHART_COLORS, CHART_DARK_COLORS, MAP_LIGHT_COLORS, MAP_DARK_COLORS = parse_css_colours()
FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
PURPLE_ACCENT = "#06165d"
PURPLE_DARK = "#5100ff"
PURPLE_LIGHT = "#8b9cf6"
HMA_MAP_COLORS = [
    "#ff4fb3",
    "#5b8def",
    "#59d5ff",
    "#74e291",
    "#fff08a",
    "#b87cf6",
    "#ff9a76",
    "#44d4c5",
    "#a7b0ff",
    "#ff7fd1",
    "#85e0d8",
    "#c7b5ff",
    "#f4cc70",
    "#7ee081",
    "#f39ac1",
    "#8ed1ff",
    "#d8f3dc",
    "#c084fc",
    "#38bdf8",
    "#fb7185",
]


def parse_s3_uri(uri):
    if not uri.startswith("s3://"):
        raise ValueError(f"Expected s3:// URI, got {uri}")
    bucket, _, key = uri[5:].partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def normalise_s3_prefix(prefix):
    return prefix.rstrip("/")


def format_threshold(value):
    return f"{value:.3f}"


def build_threshold_prefix(commuting_threshold, migration_threshold):
    if not DATASET_VERSION:
        raise RuntimeError("HMA_DATASET_VERSION is not set")
    return (
        f"{normalise_s3_prefix(PRECOMPUTED_RESULTS_PREFIX)}/dataset_version={DATASET_VERSION}"
        f"/commuting_threshold={format_threshold(commuting_threshold)}"
        f"/migration_threshold={format_threshold(migration_threshold)}"
    )


def read_s3_bytes(uri):
    bucket, key = parse_s3_uri(uri)
    response = S3_CLIENT.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def read_s3_json(uri):
    return json.loads(read_s3_bytes(uri).decode("utf-8"))


def read_s3_csv(uri):
    csv_body = read_s3_bytes(uri).decode("utf-8")
    return pd.read_csv(StringIO(csv_body))


def s3_object_exists(uri):
    bucket, key = parse_s3_uri(uri)
    try:
        S3_CLIENT.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def load_precomputed_geometry(uri):
    body = read_s3_bytes(uri)
    if uri.endswith(".gz"):
        body = gzip.decompress(body)
    geojson = json.loads(body.decode("utf-8"))
    geometry = gpd.GeoDataFrame.from_features(geojson.get("features", []))
    if geometry.empty:
        return geometry
    if geometry.crs is None:
        geometry = geometry.set_crs("EPSG:4326", allow_override=True)
    else:
        geometry = geometry.to_crs(epsg=4326)
    return geometry


def build_summary_df(map_df):
    if map_df.empty:
        return pd.DataFrame(columns=["HMA_ID", "HMA_Name", "HMA_Size", "Commuting_SC", "Migration_SC", "Stage"])
    summary_df = map_df[["HMA_ID", "HMA_Name", "HMA_Size", "Commuting_SC", "Migration_SC", "Stage"]].copy()
    summary_df = summary_df.drop_duplicates(subset=["HMA_ID"]).sort_values(
        ["HMA_Size", "HMA_Name"],
        ascending=[False, True],
    )
    return summary_df


def load_precomputed_result(commuting_threshold, migration_threshold):
    threshold_prefix = build_threshold_prefix(commuting_threshold, migration_threshold)
    summary_uri = f"{threshold_prefix}/summary.json"
    summary_payload = read_s3_json(summary_uri)

    geometry_uri = summary_payload.get("geometry_s3_uri", f"{threshold_prefix}/hma_boundaries.geojson.gz")
    map_df = load_precomputed_geometry(geometry_uri)
    summary_df = build_summary_df(map_df)

    assignments_candidates = [
        summary_payload.get("assignments_csv_s3_uri"),
        f"{threshold_prefix}/assignments.csv",
    ]
    assignments_df = None
    for candidate in assignments_candidates:
        if candidate and s3_object_exists(candidate):
            assignments_df = read_s3_csv(candidate)
            break

    meta = {
        "passed_regions": summary_payload.get("passed_regions", 0),
        "migration_regions": summary_payload.get("migration_regions", 0),
        "final_hmas": summary_payload.get("final_hmas", 0),
        "commuting_threshold": summary_payload.get("commuting_threshold", commuting_threshold),
        "migration_threshold": summary_payload.get("migration_threshold", migration_threshold),
        "summary_df": summary_df,
        "geometry_s3_uri": geometry_uri,
        "assignments_s3_uri": summary_payload.get("assignments_s3_uri"),
        "assignments_csv_s3_uri": summary_payload.get("assignments_csv_s3_uri"),
    }
    return map_df, assignments_df, meta


def build_empty_figure(message, is_dark, title):
    background = "rgb(14, 19, 22)" if is_dark else "#ffffff"
    text_color = "#eeeeee" if is_dark else COLORS["text"]
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color=text_color, family=FONT_FAMILY),
    )
    figure.update_layout(
        title=dict(text=title, x=0.02, xanchor="left", font=dict(size=18, family=FONT_FAMILY)),
        paper_bgcolor=background,
        plot_bgcolor=background,
        margin=dict(l=20, r=20, t=80, b=20),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return figure


def build_hma_map(results_df, meta, is_dark):
    if results_df.empty:
        return build_empty_figure("No precomputed HMA geometry found for this threshold pair", is_dark, "Housing Market Areas Map")

    dissolved = results_df.copy()
    dissolved["HMA_ID_str"] = dissolved["HMA_ID"].astype(int).astype(str)

    mapbox_style = "carto-darkmatter" if is_dark else "carto-positron"
    map_palette = CHART_DARK_COLORS * 4 if is_dark else HMA_MAP_COLORS * 4
    figure = px.choropleth_mapbox(
        dissolved,
        geojson=dissolved.__geo_interface__,
        locations="HMA_ID",
        featureidkey="properties.HMA_ID",
        color="HMA_ID_str",
        hover_name="HMA_Name",
        hover_data={
            "HMA_ID": True,
            "HMA_ID_str": False,
            "HMA_Size": True,
            "Commuting_SC": ":.1%",
            "Migration_SC": ":.1%",
        },
        color_discrete_sequence=map_palette,
        mapbox_style=mapbox_style,
        center={"lat": 52.54, "lon": -1.9},
        zoom=4.95,
        opacity=0.92,
    )

    figure.update_traces(
        marker_line_width=1.1,
        marker_line_color=PURPLE_LIGHT if is_dark else "rgba(102, 126, 234, 0.65)",
    )

    background = "rgb(14, 19, 22)" if is_dark else "#ffffff"
    title_color = "#eeeeee" if is_dark else "rgb(53, 61, 67)"
    title_text = (
        "<b>Housing Market Areas</b><br>"
        f"<sub>{meta['final_hmas']} HMAs generated at {meta['commuting_threshold']:.1%} commuting and "
        f"{meta['migration_threshold']:.1%} migration closure</sub>"
    )
    figure.update_layout(
        title=dict(text=title_text, x=0.02, xanchor="left", font=dict(size=17, color=title_color, family=FONT_FAMILY)),
        paper_bgcolor=background,
        plot_bgcolor=background,
        margin=dict(l=5, r=5, t=80, b=5),
        showlegend=False,
    )
    return figure


def build_size_chart(summary_df, is_dark):
    if summary_df.empty:
        return build_empty_figure("Run the algorithm to see HMA size distribution", is_dark, "HMA Sizes")

    chart_df = summary_df.head(15).sort_values("HMA_Size", ascending=True)
    background = "rgb(14, 19, 22)" if is_dark else "#ffffff"
    text_color = "#eeeeee" if is_dark else "rgb(53, 61, 67)"
    grid_color = "rgba(255,255,255,0.08)" if is_dark else "#e5e5e5"
    stage_colors = {
        "Passed commuting and migration": PURPLE_LIGHT,
        "Re-grouped by migration": PURPLE_DARK if is_dark else PURPLE_ACCENT,
    }

    figure = px.bar(
        chart_df,
        x="HMA_Size",
        y="HMA_Name",
        color="Stage",
        orientation="h",
        color_discrete_map=stage_colors,
    )
    figure.update_layout(
        title=dict(text="<b>Largest HMAs</b><br><sub>Top 15 areas by number of local authorities</sub>", x=0.02, xanchor="left"),
        paper_bgcolor=background,
        plot_bgcolor=background,
        font=dict(color=text_color, family=FONT_FAMILY),
        xaxis=dict(title="Local authorities", gridcolor=grid_color, zeroline=False),
        yaxis=dict(title=None, showgrid=False, automargin=True),
        margin=dict(l=20, r=20, t=80, b=30),
        legend=dict(
            orientation="h",
            x=-0.02,
            xanchor="left",
            y=-0.12,
            yanchor="bottom",
            bgcolor="rgba(255, 255, 255, 0)" if not is_dark else "rgba(14, 19, 22, 0)",
        ),
    )
    return figure


def build_summary_panel(summary_df, meta):
    if summary_df.empty:
        return html.P(
            "The dashboard is ready, but the HMA algorithm has not been run yet.",
            style={"marginBottom": 0, "color": COLORS["text"]},
        )

    mean_commuting = summary_df["Commuting_SC"].mean()
    mean_migration = summary_df["Migration_SC"].mean()
    return html.Div(
        [
            html.H4(
                "Algorithm Results",
                style={
                    "marginBottom": "1rem",
                    "paddingLeft": "0.75rem",
                    "fontFamily": FONT_FAMILY,
                    "fontWeight": 700,
                },
            ),
            html.Div(
                [
                    html.P(
                        [
                            "Passed both stages directly: ",
                            html.Strong(f"{meta['passed_regions']} regions"),
                        ],
                        style={"marginBottom": 0, "padding": "0.75rem 0"},
                    ),
                    html.P(
                        [
                            "Re-grouped by migration: ",
                            html.Strong(f"{meta['migration_regions']} regions"),
                        ],
                        style={"marginBottom": 0, "padding": "0.75rem 0"},
                    ),
                    html.P(
                        [
                            "Mean commuting closure: ",
                            html.Strong(f"{mean_commuting:.1%}"),
                        ],
                        style={"marginBottom": 0, "padding": "0.75rem 0"},
                    ),
                    html.P(
                        [
                            "Mean migration closure: ",
                            html.Strong(f"{mean_migration:.1%}"),
                        ],
                        style={"marginBottom": 0, "padding": "0.75rem 0"},
                    ),
                ],
                style={
                    "backgroundColor": "rgba(30, 58, 138, 0.05)",
                    "padding": "0.25rem 1rem",
                    "borderRadius": "8px",
                },
            ),
        ]
    )


def build_preview_table(summary_df):
    if summary_df.empty:
        return html.P("Run the algorithm to populate the HMA preview table.", style={"marginBottom": 0})

    preview = summary_df[["HMA_Name", "HMA_Size", "Commuting_SC", "Migration_SC", "Stage"]].head(9).copy()
    preview["Commuting_SC"] = preview["Commuting_SC"].map(lambda value: f"{value:.3f}")
    preview["Migration_SC"] = preview["Migration_SC"].map(lambda value: f"{value:.3f}")
    return dbc.Table.from_dataframe(
        preview,
        striped=False,
        bordered=False,
        hover=True,
        responsive=True,
        class_name="mb-0",
    )


def metric_card(card_id, title, value_id, footer, value_class, border_class):
    return dbc.Card(
        dbc.CardBody(
            html.Div(
                [
                    html.H4(title, id=card_id, className="metric-title"),
                    html.H2(id=value_id, children="--", className=value_class),
                    html.P(footer, className="text-muted"),
                ],
                className="text-center",
            )
        ),
        className=f"metric-card metric-card-bg {border_class}",
    )


app = dash.Dash(
    __name__,
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
    ],
)
app.title = "Housing Market Areas Dashboard"
server = app.server


@server.route("/health")
def health_check():
    return "OK", 200


app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" href="https://dev.ldn-gis.co.uk/sector-explorer/favicon.ico">
        {%css%}
    </head>
    <body>
        <div id="loading-overlay" class="loading-overlay">
            <div class="loading-logo">
                <img src="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png" alt="GLA Logo">
            </div>
            <div class="spinner"></div>
            <div class="loading-text">Housing Market Areas Dashboard</div>
            <div class="loading-subtext">Loading geography, controls and map layers...</div>
        </div>

        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>

        <script>
            window.addEventListener('load', function() {
                setTimeout(function() {
                    const overlay = document.getElementById('loading-overlay');
                    if (overlay) {
                        overlay.style.opacity = '0';
                        setTimeout(function() {
                            overlay.style.display = 'none';
                        }, 500);
                    }
                }, 1200);
            });

            document.addEventListener('DOMContentLoaded', function() {
                const checkDashReady = setInterval(function() {
                    const dashContainer = document.querySelector('[data-dash-is-loading="false"]');
                    if (dashContainer) {
                        clearInterval(checkDashReady);
                        setTimeout(function() {
                            const overlay = document.getElementById('loading-overlay');
                            if (overlay && overlay.style.display !== 'none') {
                                overlay.style.opacity = '0';
                                setTimeout(function() {
                                    overlay.style.display = 'none';
                                }, 500);
                            }
                        }, 600);
                    }
                }, 100);
            });
        </script>
    </body>
</html>
"""


app.layout = html.Div(
    [
        dcc.Store(id="last-update-time", data={"timestamp": 0}),
        dcc.Store(id="dark-mode-state", data={"isDark": False}),
        dcc.Store(id="sidebar-collapsed", data=False),
        html.Div(id="card-animation-target", style={"display": "none"}),
        html.Button([html.Span("☰", className="hamburger-icon")], id="sidebar-toggle", className="sidebar-toggle-btn"),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.H4("Controls", className="sidebar-title"),
                                html.Button("×", id="sidebar-close", className="sidebar-close-btn"),
                            ],
                            className="sidebar-header",
                        ),
                        html.Div(
                            [
                                html.Label("Commuting self-containment", className="fw-bold mb-2 control-label"),
                                dcc.Slider(
                                    id="commuting-slider",
                                    min=0.5,
                                    max=0.9,
                                    step=0.025,
                                    value=0.725,
                                    marks={value / 100: f"{value}%" for value in range(50, 91, 10)},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                    className="range-slider",
                                ),
                            ],
                            className="mb-4",
                        ),
                        html.Div(
                            [
                                html.Label("Migration self-containment", className="fw-bold mb-2 control-label"),
                                dcc.Slider(
                                    id="migration-slider",
                                    min=0.3,
                                    max=0.7,
                                    step=0.025,
                                    value=0.55,
                                    marks={value / 100: f"{value}%" for value in range(30, 71, 10)},
                                    tooltip={"placement": "bottom", "always_visible": True},
                                    className="range-slider",
                                ),
                            ],
                            className="mb-4",
                        ),
                        html.Div(
                            [
                                html.Button("Run HMA algorithm", id="run-button", className="button-styling"),
                            ],
                            className="mt-4",
                        ),
                        html.Div(
                            [
                                html.Button("Download results CSV", id="download-button", className="button-styling"),
                                dcc.Download(id="download-dataframe-csv"),
                            ],
                            className="mt-3",
                            style={"marginTop": "18px"},
                        ),
                        html.Div(
                            [
                                html.Label(
                                    [
                                        html.Span("☀", className="theme-icon-light"),
                                        dbc.Checklist(
                                            options=[{"label": "", "value": 1}],
                                            value=[],
                                            id="theme-toggle-button",
                                            switch=True,
                                            className="theme-toggle-switch",
                                        ),
                                        html.Span("☾", className="theme-icon-dark"),
                                    ],
                                    className="theme-toggle-label",
                                )
                            ],
                            className="sidebar-theme-toggle-below-button",
                        ),
                    ],
                    id="sidebar",
                    className="sidebar",
                )
            ],
            className="sidebar-container",
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [html.H1("Housing Market Areas Creator", className="banner-title")],
                                    className="banner-content",
                                )
                            ],
                            className="banner-header",
                        )
                    ]
                ),
                dbc.Container(
                    [
                        html.Hr(className="footer-divider"),
                        html.H3("Dashboard - England and Wales", id="dashboard-heading", className="dashboard-heading"),
                        html.Div(
                            id="status-message",
                            className="status-message-text",
                            children="Ready to load precomputed HMAs. Click Run HMA algorithm.",
                            style={
                                "marginBottom": "1.5rem",
                                "padding": "0.9rem 1rem",
                                "borderRadius": "8px",
                                "backgroundColor": "rgba(30, 58, 138, 0.08)",
                                "color": COLORS["text"],
                            },
                        ),
                        dbc.Row(
                            [
                                dbc.Col(metric_card("total-title", "Total HMAs", "metric-total-hmas", "Areas produced by the current run", "metric-value-primary", "metric-border-secondary"), xs=12, sm=12, md=3, lg=3),
                                dbc.Col(metric_card("mean-title", "Mean HMA Size", "metric-mean-size", "Average local authorities per HMA", "metric-value-accent", "metric-border-accent"), xs=12, sm=12, md=3, lg=3),
                                dbc.Col(metric_card("largest-title", "Largest HMA", "metric-largest-size", "Largest region in local authorities", "metric-value-warning", "metric-border-warning"), xs=12, sm=12, md=3, lg=3),
                            ],
                            className="mb-4 g-3 metric-cards-row",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody(
                                            [
                                                dcc.Graph(id="hma-map", figure=build_empty_figure("Run the algorithm", False, "Housing Market Areas Map"), style={"height": "72vh", "minHeight": "680px"}),
                                                html.Div(
                                                    [
                                                        html.Button(
                                                            [
                                                                html.Span("i", style={"marginRight": "8px", "fontWeight": 700}),
                                                                "View description",
                                                            ],
                                                            id="hma-map-desc-button",
                                                            className="description-button",
                                                        ),
                                                    ],
                                                    className="button-group-bottom",
                                                ),
                                            ],
                                            style={"padding": 0},
                                        ),
                                        className="graph-container full-width-map-card",
                                    ),
                                    xs=12,
                                    sm=12,
                                    md=12,
                                    lg=12,
                                ),
                            ],
                            className="mb-4 g-3 full-bleed-map-row",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody(
                                            [
                                                dcc.Graph(id="hma-size-chart", figure=build_empty_figure("Run the algorithm to view HMA sizes.", False, "Largest HMAs"), style={"height": "460px"}),
                                                html.Div(
                                                    [
                                                        html.Button(
                                                            [
                                                                html.Span("i", style={"marginRight": "8px", "fontWeight": 700}),
                                                                "View description",
                                                            ],
                                                            id="hma-size-chart-desc-button",
                                                            className="description-button",
                                                        ),
                                                    ],
                                                    className="button-group-bottom",
                                                ),
                                            ],
                                            style={"padding": 0},
                                        ),
                                        className="graph-container full-width-chart-card",
                                    ),
                                    xs=12,
                                    sm=12,
                                    md=12,
                                    lg=12,
                                ),
                            ],
                            className="mb-4 full-bleed-chart-row",
                        ),
                        dbc.Row(
                            [
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody(html.Div(id="stats-output", children=build_summary_panel(pd.DataFrame(), {}))),
                                        className="graph-container",
                                    ),
                                     xs=12,
                                     sm=12,
                                     md=4,
                                     lg=4,
                                ), 
                                dbc.Col(
                                    dbc.Card(
                                        dbc.CardBody(
                                            [
                                                html.H4(
                                                    "Preview of Generated HMAs",
                                                    style={
                                                        "marginBottom": "1rem",
                                                        "paddingLeft": "0.75rem",
                                                        "fontFamily": FONT_FAMILY,
                                                        "fontWeight": 700,
                                                    },
                                                ),
                                                html.Div(
                                                    id="results-preview",
                                                    children=build_preview_table(pd.DataFrame()),
                                                    style={
                                                        "backgroundColor": "rgba(30, 58, 138, 0.05)",
                                                        "padding": "0.25rem 1rem",
                                                        "width": "calc(100%)",
                                                        "borderRadius": "8px",
                                                        "fontFamily": FONT_FAMILY,
                                                    },
                                                ),
                                            ]
                                        ),
                                        className="graph-container preview-results-card",
                                    ),
                                     xs=12,
                                     sm=12,
                                     md=8,
                                     lg=8,
                                ),
                            ],
                            className="mb-4 g-3 stats-preview-row",
                            

                        ),
                    ],
                    fluid=True,
                    className="main-container dashboard-grey-line",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Iframe(
                                            id="gla-logo-dark",
                                            src="https://greater-london-authority.github.io/ldn-viz-tools/iframe.html?globals=theme:dark&args=&id=ui-components-logos--ciu",
                                            style={"border": "none", "width": "250px", "height": "60px", "overflow": "hidden"},
                                        )
                                    ],
                                    style={"textAlign": "center", "marginBottom": "1rem"},
                                ),
                                html.P(
                                    [
                                        "GLA Housing Market Areas Dashboard | Inputs: user-supplied commuting and migration flows | Geography: local authority boundaries",
                                    ],
                                    style={"color": "#ffffff", "marginBottom": "0", "textAlign": "center", "fontSize": "13px"},
                                ),
                            ],
                            style={
                                "backgroundColor": "rgb(14, 19, 22)",
                                "padding": "1.5rem 2rem",
                                "marginTop": "3rem",
                                "borderTop": "1px solid #d6d8da",
                            },
                        )
                    ],
                    style={"width": "100vw", "marginLeft": "calc(-50vw + 50%)", "marginRight": "calc(-50vw + 50%)"},
                ),
                dbc.Modal(
                    [
                        dbc.ModalHeader(dbc.ModalTitle("Description"), close_button=True),
                        dbc.ModalBody(
                            [
                                html.P(
                                    "This map shows the Housing Market Areas generated from the current commuting and migration self-containment thresholds. Each coloured area is an HMA built by grouping neighbouring local authorities based on strong functional links."
                                ),
                                html.Br(),
                                html.P(
                                    "Run the algorithm after adjusting the sliders to see how the geography changes. Hover over an HMA to inspect its size and closure metrics."
                                ),
                            ]
                        ),
                    ],
                    id="hma-map-modal",
                    is_open=False,
                    className="description-modal",
                    centered=True,
                    backdrop=True,
                ),
                dbc.Modal(
                    [
                        dbc.ModalHeader(dbc.ModalTitle("Description"), close_button=True),
                        dbc.ModalBody(
                            [
                                html.P(
                                    "This chart shows the largest generated Housing Market Areas by number of local authorities. It compares areas that passed both stages directly with areas that had to be re-grouped during the migration stage."
                                ),
                                html.Br(),
                                html.P(
                                    "Use it to see how concentrated the final HMAs are under the current thresholds and which stage produced each large area."
                                ),
                            ]
                        ),
                    ],
                    id="hma-size-chart-modal",
                    is_open=False,
                    className="description-modal",
                    centered=True,
                    backdrop=True,
                ),
            ],
            id="main-content",
            className="main-content",
        ),
    ],
    className="dashboard-wrapper",
)


@app.callback(
    [
        Output("hma-map", "figure"),
        Output("hma-size-chart", "figure"),
        Output("metric-total-hmas", "children"),
        Output("metric-mean-size", "children"),
        Output("metric-largest-size", "children"),
        Output("stats-output", "children"),
        Output("results-preview", "children"),
        Output("status-message", "children"),
    ],
    Input("run-button", "n_clicks"),
    Input("dark-mode-state", "data"),
    State("commuting-slider", "value"),
    State("migration-slider", "value"),
    prevent_initial_call=False,
)
def update_dashboard(n_clicks, dark_mode_data, commuting_threshold, migration_threshold):
    global current_results, current_meta, current_assignments

    is_dark = dark_mode_data.get("isDark", False) if dark_mode_data else False

    triggered_prop = None
    try:
        if dash.callback_context.triggered:
            triggered_prop = dash.callback_context.triggered[0]["prop_id"]
    except Exception:
        triggered_prop = None

    if not n_clicks:
        if DATASET_VERSION:
            status_text = f"Ready to load precomputed HMAs from dataset version {DATASET_VERSION}. Click Run HMA algorithm."
        else:
            status_text = "Set HMA_DATASET_VERSION, then click Run HMA algorithm to load precomputed HMAs."
        return (
            build_empty_figure("Load a precomputed threshold pair to view the Housing Market Areas map", is_dark, "Housing Market Areas Map"),
            build_empty_figure("Load a precomputed threshold pair to view HMA sizes.", is_dark, "Largest HMAs"),
            "--",
            "--",
            "--",
            build_summary_panel(pd.DataFrame(), {}),
            build_preview_table(pd.DataFrame()),
            status_text,
        )

    if triggered_prop == "dark-mode-state.data" and current_results is not None and current_meta is not None:
        summary_df = current_meta["summary_df"]
        status_text = (
            f"Algorithm complete. Generated {current_meta['final_hmas']} HMAs at "
            f"{current_meta['commuting_threshold']:.1%} commuting and "
            f"{current_meta['migration_threshold']:.1%} migration closure."
        )
        return (
            build_hma_map(current_results, current_meta, is_dark),
            build_size_chart(summary_df, is_dark),
            f"{current_meta['final_hmas']}",
            f"{summary_df['HMA_Size'].mean():.1f}",
            f"{int(summary_df['HMA_Size'].max())}",
            build_summary_panel(summary_df, current_meta),
            build_preview_table(summary_df),
            status_text,
        )

    try:
        results_df, assignments_df, meta = load_precomputed_result(commuting_threshold, migration_threshold)
        current_results = results_df.copy()
        current_meta = meta
        current_assignments = assignments_df.copy() if assignments_df is not None else None

        summary_df = meta["summary_df"]
        status_text = (
            f"Loaded precomputed results. Generated {meta['final_hmas']} HMAs at "
            f"{commuting_threshold:.1%} commuting and {migration_threshold:.1%} migration closure."
        )
        return (
            build_hma_map(results_df, meta, is_dark),
            build_size_chart(summary_df, is_dark),
            f"{meta['final_hmas']}",
            f"{summary_df['HMA_Size'].mean():.1f}",
            f"{int(summary_df['HMA_Size'].max())}",
            build_summary_panel(summary_df, meta),
            build_preview_table(summary_df),
            status_text,
        )
    except Exception as error:
        message = str(error)
        return (
            build_empty_figure(message, is_dark, "Housing Market Areas Map"),
            build_empty_figure("No size summary available", is_dark, "Largest HMAs"),
            "--",
            "--",
            "--",
            html.Div(
                [
                    html.H4("Algorithm unavailable", style={"marginBottom": "1rem"}),
                    html.P(message, style={"marginBottom": 0}),
                ]
            ),
            build_preview_table(pd.DataFrame()),
            f"Unable to run the HMA algorithm: {message}",
        )


@app.callback(
    Output("download-dataframe-csv", "data"),
    Input("download-button", "n_clicks"),
    prevent_initial_call=True,
)
def download_results(n_clicks):
    if not n_clicks or current_assignments is None or current_meta is None:
        return None

    download_df = current_assignments.copy()
    expected_columns = [
        "LAD23CD",
        "LAD23NM",
        "HMA_ID",
        "HMA_Name",
        "HMA_Size",
        "Commuting_SC",
        "Migration_SC",
        "Stage",
    ]
    available_columns = [column for column in expected_columns if column in download_df.columns]
    download_df = download_df[
        available_columns
    ].sort_values(["HMA_ID", "LAD23CD"])
    if "Commuting_SC" in download_df.columns:
        download_df["Commuting_SC"] = download_df["Commuting_SC"].round(3)
    if "Migration_SC" in download_df.columns:
        download_df["Migration_SC"] = download_df["Migration_SC"].round(3)
    return dcc.send_data_frame(download_df.to_csv, "housing_market_areas.csv", index=False)


@app.callback(
    Output("hma-map-modal", "is_open"),
    Input("hma-map-desc-button", "n_clicks"),
    State("hma-map-modal", "is_open"),
)
def toggle_hma_map_modal(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


@app.callback(
    Output("hma-size-chart-modal", "is_open"),
    Input("hma-size-chart-desc-button", "n_clicks"),
    State("hma-size-chart-modal", "is_open"),
)
def toggle_hma_size_chart_modal(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open


app.clientside_callback(
    """
    function(nClicks) {
        const cards = document.querySelectorAll('.metric-card');
        cards.forEach((card, index) => {
            setTimeout(() => {
                card.style.transform = 'scale(1.04)';
                card.style.transition = 'transform 0.25s ease-out';
                setTimeout(() => {
                    card.style.transform = 'scale(1)';
                }, 180);
            }, index * 90);
        });
        return {timestamp: Date.now(), clicks: nClicks || 0};
    }
    """,
    Output("last-update-time", "data"),
    Input("run-button", "n_clicks"),
)


app.clientside_callback(
    """
    function(timestamp) {
        if (!window.hmaHoverListenersAdded) {
            const graphs = document.querySelectorAll('.graph-container');
            graphs.forEach((graph) => {
                graph.addEventListener('mouseenter', function() {
                    this.style.transform = 'translateY(-4px)';
                    this.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
                });
                graph.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateY(0)';
                });
            });
            window.hmaHoverListenersAdded = true;
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("card-animation-target", "children"),
    Input("last-update-time", "data"),
)


app.clientside_callback(
    """
    function(toggleValue) {
        if (toggleValue === undefined) {
            const savedTheme = localStorage.getItem('darkMode');
            const isDark = savedTheme === 'true';
            if (isDark) {
                document.body.classList.add('dark-mode');
            }
            return [isDark ? [1] : [], {isDark: isDark}];
        }

        const isDark = toggleValue && toggleValue.length > 0;
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        localStorage.setItem('darkMode', isDark);
        return [toggleValue, {isDark: isDark}];
    }
    """,
    [Output("theme-toggle-button", "value"), Output("dark-mode-state", "data")],
    Input("theme-toggle-button", "value"),
)


app.clientside_callback(
    """
    function(toggleClicks, closeClicks) {
        const sidebar = document.getElementById('sidebar');
        const sidebarContainer = document.querySelector('.sidebar-container');
        const toggleBtn = document.getElementById('sidebar-toggle');

        if (!sidebar || !sidebarContainer) {
            return window.dash_clientside.no_update;
        }

        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered || ctx.triggered.length === 0) {
            const savedState = localStorage.getItem('sidebarCollapsed');
            if (savedState === 'true') {
                sidebar.classList.add('collapsed');
                sidebarContainer.classList.add('collapsed');
                if (toggleBtn) toggleBtn.classList.remove('hidden');
            } else if (toggleBtn) {
                toggleBtn.classList.add('hidden');
            }
            return window.dash_clientside.no_update;
        }

        const isCollapsed = sidebar.classList.toggle('collapsed');
        sidebarContainer.classList.toggle('collapsed');

        if (toggleBtn) {
            if (isCollapsed) {
                toggleBtn.classList.remove('hidden');
            } else {
                toggleBtn.classList.add('hidden');
            }
        }

        localStorage.setItem('sidebarCollapsed', isCollapsed);
        if (window.innerWidth <= 768) {
            sidebar.classList.toggle('open');
        }

        return window.dash_clientside.no_update;
    }
    """,
    Output("sidebar-collapsed", "data"),
    [Input("sidebar-toggle", "n_clicks"), Input("sidebar-close", "n_clicks")],
)


if __name__ == "__main__":
    print(f"Starting Housing Market Areas Dashboard on port {PORT}...")
    app.run(debug=True, port=PORT)
