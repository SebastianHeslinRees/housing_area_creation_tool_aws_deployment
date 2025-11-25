# FERTILITY DASHBOARD 
"""UK Fertility Rate Dashboard - Dash app entrypoint

This is the application entrypoint used for local development and production
(gunicorn will import `server` from this module).

Notes:
- Runs on port 8022 by default when executed directly.
- Use `gunicorn --bind 0.0.0.0:8022 --workers 1 app:server` for production.
"""
import os
import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, Input, Output, State
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import geopandas as gpd
import json

# ----------------- Configuration -----------------
PORT = int(os.environ.get('PORT', 8022))
S3_BUCKET = os.environ.get('S3_BUCKET', 'dpa-population-projection-data')
S3_PREFIX = os.environ.get('S3_PREFIX', 'dpa-apps/')
S3_REGION = os.environ.get('AWS_REGION', 'eu-west-2')

# ----------------- CSS Colour Parser -----------------
def parse_css_colours(css_file='assets/styles.css'):
    """Parse CSS variables from stylesheet to avoid duplication"""
    colours = {}
    chart_colours = []
    chart_dark_colours = []
    
    try:
        with open(css_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Parse --chart-dark-color-* variables first (more specific)
                if line.startswith('--chart-dark-color-') and ':' in line:
                    parts = line.split(':')
                    value = parts[1].split(';')[0].strip()
                    chart_dark_colours.append(value)
                # Parse --chart-color-* variables (but not dark ones)
                elif line.startswith('--chart-color-') and ':' in line:
                    parts = line.split(':')
                    value = parts[1].split(';')[0].strip()
                    chart_colours.append(value)
                # Parse --color-* variables
                elif line.startswith('--color-') and ':' in line:
                    parts = line.split(':')
                    key = parts[0].replace('--color-', '').replace('-', '_')
                    value = parts[1].split(';')[0].strip()
                    colours[key] = value
    except FileNotFoundError:
        print(f"⚠ Warning: {css_file} not found, using fallback colours")
    
    # Apply fallbacks if parsing didn't find values
    if not colours:
        colours = {
            'primary': '#1e3a8a', 'secondary': '#ea580c', 'accent': '#3b82f6',
            'background': '#F8F9FA', 'text': '#2C3E50', 'warning': '#f59e0b',
            'card_bg': '#ffffff'
        }
    if not chart_colours:
        chart_colours = ['#1e3a8a', '#ea580c', '#3b82f6', '#10b981', '#f59e0b',
                        '#8b5cf6', '#ec4899', '#06b6d4', '#ef4444', '#14b8a6']
    if not chart_dark_colours:
        chart_dark_colours = ['#93c5fd', '#fbbf24', '#60a5fa', '#34d399', '#fbbf24',
                             '#a78bfa', '#f472b6', '#22d3ee', '#f87171', '#2dd4bf']
    
    return colours, chart_colours, chart_dark_colours

# ----------------- Data Loading Functions for Geojson in S3 -----------------
def download_from_s3_if_needed(filename, bucket=S3_BUCKET, prefix=S3_PREFIX):
    """Download file from S3 if not present locally (for AWS deployment)"""
    if os.path.exists(filename):
        print(f"✓ Using local file: {filename}")
        return filename
    
    try:
        import boto3
        s3_key = f"{prefix}{filename}"
        print(f" Downloading s3://{bucket}/{s3_key}...")
        s3 = boto3.client('s3', region_name=S3_REGION)
        s3.download_file(bucket, s3_key, filename)
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"✓ Downloaded {filename} successfully ({file_size_mb:.1f} MB)")
        return filename
    except Exception as e:
        print(f" Error downloading {filename} from S3: {e}")
        import traceback
        traceback.print_exc()
        raise

# ----------------- Load Data -----------------
print("Loading fertility and geometry data...")

try:
    # Download from S3 if needed (for AWS deployment)
    asfr_file_reduced = download_from_s3_if_needed('asfr_merged_reduced.geojson')
    tfr_file_reduced = download_from_s3_if_needed('tfr_merged_reduced.geojson')

    print(f"Reading ASFR file: {asfr_file_reduced}")
    asfr_merged = gpd.read_file(asfr_file_reduced)
    print(f"✓ Loaded ASFR data: {len(asfr_merged)} features")
    
    print(f"Reading TFR file: {tfr_file_reduced}")
    tfr_merged = gpd.read_file(tfr_file_reduced)
    print(f"✓ Loaded TFR data: {len(tfr_merged)} features")
    
except Exception as e:
    print(f" FATAL ERROR loading data: {e}")
    import traceback
    traceback.print_exc()
    raise


# Clean TFR data
tfr_clean = tfr_merged[['LAD23CD', 'LAD23NM', 'geometry', 'year', 'tfr']].copy()
if tfr_clean.crs is None:
    tfr_clean = tfr_clean.set_crs("EPSG:27700", allow_override=True)
tfr_clean = tfr_clean.to_crs(epsg=4326)
tfr_clean['geometry'] = tfr_clean['geometry'].simplify(tolerance=0.007, preserve_topology=True)
tfr_clean = tfr_clean[tfr_clean.is_valid].reset_index(drop=True)

# Clean ASFR data  
asfr_clean = asfr_merged[['LAD23CD','LAD23NM','geometry','age','year','fertility_rate']].copy()
if asfr_clean.crs is None:
    asfr_clean = asfr_clean.set_crs("EPSG:27700", allow_override=True)
asfr_clean = asfr_clean.to_crs(epsg=4326)
asfr_clean['geometry'] = asfr_clean['geometry'].simplify(tolerance=0.007, preserve_topology=True)
asfr_clean = asfr_clean[asfr_clean.is_valid].reset_index(drop=True)

# Convert to strings for serialisation
years = sorted([str(year) for year in tfr_clean['year'].unique()])
ages = sorted([str(age) for age in asfr_clean['age'].unique()])
lads = sorted(tfr_clean['LAD23NM'].unique())

# Ensure string columns
tfr_clean['year'] = tfr_clean['year'].astype(str)
asfr_clean['year'] = asfr_clean['year'].astype(str) 
asfr_clean['age'] = asfr_clean['age'].astype(str)

print(f"  dashboard ready: {len(years)} years, {len(ages)} ages, {len(lads)} LADs")

# Initialise Dash App
app = dash.Dash(
    __name__, 
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
    ]
)
app.title = "UK Fertility Dashboard"
server = app.server  # Expose server for gunicorn

# loading spinner
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" type="image/png" href="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png">
        <link rel="shortcut icon" type="image/png" href="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png">
        <link rel="apple-touch-icon" href="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png">
        {%css%}
    </head>
    <body>
        <!--   Loading Overlay -->
        <div id="loading-overlay" class="loading-overlay">
            <div class="loading-logo">
                <img src="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png" alt="GLA Logo">
            </div>
            <div class="spinner"></div>
            <div class="loading-text">UK Fertility Dashboard</div>
            <div class="loading-subtext">Loading fertility rate analysis and interactive visualisations...</div>
        </div>
        
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        
        <script>
            //   loading overlay management
            window.addEventListener('load', function() {
                setTimeout(function() {
                    const overlay = document.getElementById('loading-overlay');
                    if (overlay) {
                        overlay.style.opacity = '0';
                        setTimeout(function() {
                            overlay.style.display = 'none';
                        }, 500);
                    }
                }, 1200); // Extended display for   feel
            });
            
            // Dash readiness detection
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
'''

# Note: Colour scheme is defined in assets/styles.css and parsed here to avoid duplication
COLORS, CHART_COLORS, CHART_DARK_COLORS = parse_css_colours()

# Font configuration - Using Inter font from LDN-Viz theme
FONT_FAMILY = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
FONT_FAMILY_BOLD = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

#Layout
app.layout = html.Div([
    
    # Hidden stores for clientside callbacks
    dcc.Store(id='animation-trigger', data={'count': 0}),
    dcc.Store(id='last-update-time', data={'timestamp': 0}),
    dcc.Store(id='dark-mode-state', data={'isDark': False}),  # Track dark mode state
    dcc.Store(id='sidebar-collapsed', data=False),  # Track sidebar state
    html.Div(id='card-animation-target', style={'display': 'none'}),
    
    # Sidebar toggle button (outside sidebar so always visible)
    html.Button([
        html.Span("☰", className="hamburger-icon")
    ], id="sidebar-toggle", className="sidebar-toggle-btn"),
    
    # Collapsible Sidebar
    html.Div([
        # Sidebar content
        html.Div([
            # Sidebar header
            html.Div([
                html.H4("Filters", className="sidebar-title"),
                html.Button("×", id="sidebar-close", className="sidebar-close-btn")
            ], className="sidebar-header"),
            
            # Year Dropdown
            html.Div([
                html.Label("Select Year", className="fw-bold mb-2 control-label"),
                dcc.Dropdown(
                    id='year-dropdown',
                    options=[{'label': year, 'value': year} for year in years],
                    value=years[-1],
                    clearable=False,
                    className="dropdown-container"
                )
            ], className="mb-4"),
            
            # Age Dropdown
            html.Div([
                html.Label("Select Age (ASFR)", className="fw-bold mb-2 control-label"),
                dcc.Dropdown(
                    id='age-dropdown',
                    options=[{'label': f"Age {age}", 'value': age} for age in ages],
                    value="30",
                    clearable=False,
                    className="dropdown-container"
                )
            ], className="mb-4"),
            
            # LAD Dropdown
            html.Div([
                html.Label("Local Authorities (Select Multiple)", className="fw-bold mb-2 control-label"),
                dcc.Dropdown(
                    id='lad-dropdown',
                    options=[{'label': lad, 'value': lad} for lad in lads],
                    value=["Manchester"],
                    multi=True,
                    placeholder="Search Local Authorities...",
                    className="dropdown-container"
                )
            ], className="mb-4"),
            
            # Clear Selections Button
            html.Div([
                html.Button([
                    html.Span(style={"marginRight": "8px"}),
                    "Clear Selections"
                ], id="clear-selections-btn", className="button-styling")
            ], className="mt-4"),
            
            # Dark mode toggle below clear button
            html.Div([
                html.Label([
                    html.Span("☀", className="theme-icon-light"),
                    dbc.Checklist(
                        options=[{"label": "", "value": 1}],
                        value=[],
                        id="theme-toggle-button",
                        switch=True,
                        className="theme-toggle-switch"
                    ),
                    html.Span("☾", className="theme-icon-dark")
                ], className="theme-toggle-label")
            ], className="sidebar-theme-toggle-below-button")
            
        ], id="sidebar", className="sidebar")
    ], className="sidebar-container"),
    
    # Main content area
    html.Div([
        #   Banner Header
        html.Div([
            # Banner header
            html.Div([
                html.Div([
                    html.H1("UK Fertility Rate Dashboard", className="banner-title"),
                    html.H5("Analysis of Total & Age-Specific Fertility Rates (1993-2023)",
                           className="banner-subtitle")
                ], className="banner-content")
            ], className="banner-header")
        ]),
        
        # Main content container
        dbc.Container([
            # Summary Metrics
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.H4(id="tfr-title", children="Total Fertility Rate", className="metric-title"),
                                html.H2(id="current-tfr", children="--", className="metric-value-primary"),
                                html.P("Based on first selected Local Authority", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="metric-card metric-card-bg metric-border-secondary")
                ], xs=12, sm=12, md=4, lg=4),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.H4(id="comparison-title", children="vs UK Average", className="metric-title"),
                                html.H2(id="tfr-comparison", children="--", className="metric-value-accent"),
                                html.P("Based on first selected Local Authority", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="metric-card metric-card-bg metric-border-accent")
                ], xs=12, sm=12, md=4, lg=4),
                
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.H4("Replacement Level", className="metric-title"),
                                html.H2("2.1", className="metric-value-warning"),
                                html.P(id="replacement-status", children="--", className="text-muted")
                            ], className="text-center")
                        ])
                    ], className="metric-card metric-card-bg metric-border-warning")
                ], xs=12, sm=12, md=4, lg=4)
            ], className="mb-4 g-3"),
            
            #   Maps Section
            dbc.Row([
                # TFR Map
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("Total Fertility Rate Map", className="text-center mb-0 card-header-title")
                        ], className="card-header-bg"),
                        dbc.CardBody([
                            dcc.Graph(id='tfr-map', style={'height': '520px'})
                        ], style={'padding': '0'})
                    ], className="graph-container")
                ], width=6),
                
                # ASFR Map 
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("Age-Specific Fertility Rate Map", className="text-center mb-0 card-header-title")
                        ], className="card-header-bg"),
                        dbc.CardBody([
                            dcc.Graph(id='asfr-map', style={'height': '520px'})
                        ], style={'padding': '0'})
                    ], className="graph-container")
                ], width=6)
            ], className="mb-4"),
            
            #   Trend Analysis
            dbc.Row([
                # TFR Trend 
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("TFR Trend Analysis", className="text-center mb-0 card-header-title")
                        ], className="card-header-bg"),
                        dbc.CardBody([
                            dcc.Graph(id='tfr-trend', style={'height': '420px'})
                        ], style={'padding': '0'})
                    ], className="graph-container")
                ], width=6),
                
                # ASFR Trend 
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H5("ASFR Trend Analysis", className="text-center mb-0 card-header-title")
                        ], className="card-header-bg"),
                        dbc.CardBody([
                            dcc.Graph(id='asfr-trend', style={'height': '420px'})
                        ], style={'padding': '0'})
                    ], className="graph-container")
                ], width=6)
            ], className="mb-4"),
            
            # Footer
            dbc.Row([
                dbc.Col([
                    html.Hr(className="footer-divider"),
                    dbc.Alert([
                        html.H5("About This Dashboard", className="alert-heading footer-alert-heading"),
                        html.P([
                                 "This dashboard provides analysis of UK fertility rates using the GLA Fertility Estimates. ",
                                    "The code used to produce these estimates is available on ",
                                    html.A("GitHub", 
                                        href="https://github.com/Greater-London-Authority/fertility_rate_estimation/tree/main",
                                        target="_blank",
                                        className="footer-link"),
                                html.Br(),
                            html.Strong("TFR (Total Fertility Rate)"), " Total fertility rate (TFR) is a commonly used measure of overall fertility calculated as the sum of all age-specific fertility rates across all reproductive age groups. It represents the average number of children that a woman would have if she were to experience current age-specific fertility rates over the course of her life. For 2023, we estimate the TFR in Inner London to have been 1.16 compared to 1.54 in Outer London, and 1.41 for England as whole.",
                                html.Br(),
                            html.Strong("ASFR (Age-Specific Fertility Rate, 15 to 49)"), " measures the number of births per woman within specific age groups. For example, in England, the peak childbearing age is currently 32, with an ASFR of 0.107, meaning 107 babies were born for each 1,000 women aged 32.",
                            "The UK replacement fertility rate is approximately ", html.Strong("2.1 children per woman"), "."
                        ], className="mb-2 footer-text"),
                        html.P([
                            "Use the controls above to explore different years, ages, and local authorities. ",
                            "Interactive maps maintain their fertility-specific colour schemes. ",
                            "Compare trends across time and regions with visualisations. Visualisations can be easily downloaded using the camera icon in the top-right corner of each graph."
                        ], className="mb-0 footer-text")
                    ], className="mb-3 footer-alert-bg"),
                    
                    html.P([
                        "GLA Fertility Dashboard | Data: ",
                        html.A("GLA Fertility Rate Output", 
                              href="https://data.london.gov.uk/dataset/age-specific-fertility-rates-vd4q4/", 
                              target="_blank",
                              className="footer-link"),
                        " | ONS | ",
                        html.A("Office for National Statistics", 
                              href="https://www.ons.gov.uk", 
                              target="_blank",
                              className="footer-link")
                    ], className="text-center footer-credits")
                ], width=12)  # Close dbc.Col
            ])  # Close dbc.Row
        ], fluid=True, className="main-container")  # Close dbc.Container
        
    ], id="main-content", className="main-content")  # Close main content div
    
], className="dashboard-wrapper")  # Close outer wrapper div


# ==========   CALLBACKS ==========


# Update metrics with formatting
@app.callback(
    [Output('current-tfr', 'children'),
     Output('tfr-comparison', 'children'),
     Output('replacement-status', 'children')],
    [Input('year-dropdown', 'value'),
     Input('lad-dropdown', 'value')]
)
def update_metrics(selected_year, selected_lads):
    try:
        if selected_lads and selected_year and len(selected_lads) > 0:
            # Use first selected LAD for metrics
            selected_lad = selected_lads[0] if isinstance(selected_lads, list) else selected_lads
            
            lad_tfr = tfr_clean[
                (tfr_clean['year'] == selected_year) & 
                (tfr_clean['LAD23NM'] == selected_lad)
            ]['tfr']
            
            if not lad_tfr.empty:
                current_tfr = lad_tfr.iloc[0]
                tfr_display = f"{current_tfr:.2f}"
                
                #   comparison formatting
                uk_avg = tfr_clean[tfr_clean['year'] == selected_year]['tfr'].mean()
                diff = current_tfr - uk_avg
                comparison = f"{diff:+.2f}"
                
                #   status indicators
                if current_tfr >= 2.1:
                    status = "Above replacement level"
                elif current_tfr >= 1.8:
                    status = f"Below by {2.1 - current_tfr:.2f}"
                else:
                    status = f"Below by {2.1 - current_tfr:.2f}"
                    
                return tfr_display, comparison, status
        
        return "Select Data", "N/A", "Choose LAD & Year"
        
    except Exception as e:
        print(f"  metrics error: {e}")
        return "Error", "Error", "Data Error"

# Clear selections button callback
@app.callback(
    Output('lad-dropdown', 'value'),
    [Input('clear-selections-btn', 'n_clicks')],
    prevent_initial_call=True
)
def clear_selections(n_clicks):
    if n_clicks:
        return []
    return ["Manchester"]

#   TFR map (keeping RdYlBu_r colour scheme)
@app.callback(
    Output('tfr-map', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('dark-mode-state', 'data')]
)
def update_tfr_map(selected_year, dark_mode_data):
    try:
        is_dark = dark_mode_data.get('isDark', False) if dark_mode_data else False
        
        if not selected_year:
            return go.Figure().add_annotation(text="Please select a year", showarrow=False, 
                                           font=dict(size=16, color='#eeeeee' if is_dark else COLORS['text']))
        
        filtered_tfr = tfr_clean[tfr_clean['year'] == selected_year]
        
        if filtered_tfr.empty:
            return go.Figure().add_annotation(text="No data available for selected year", 
                                           showarrow=False, font=dict(size=16, color='#eeeeee' if is_dark else COLORS['text']))
        
        # Choose mapbox style based on theme
        mapbox_style = 'carto-darkmatter' if is_dark else 'carto-positron'
        
        #maps
        fig = px.choropleth_mapbox(
            filtered_tfr,
            geojson=filtered_tfr.__geo_interface__,
            locations='LAD23CD',
            featureidkey='properties.LAD23CD',
            color='tfr',
            hover_name='LAD23NM',
            hover_data={'tfr': ':.3f', 'LAD23CD': False},
            color_continuous_scale='RdYlBu_r',  
            mapbox_style=mapbox_style,
            zoom=5.3,
            center={"lat": 54.5, "lon": -2.5},
            opacity=0.85
        )
        
        # Dark mode styling
        title_color = '#eeeeee' if is_dark else COLORS['primary']
        paper_bg = '#16213e' if is_dark else 'white'
        
        fig.update_layout(
            title=dict(
                text=f"Total Fertility Rate ({selected_year})",
                x=0.5,
                font=dict(size=18, color=title_color, family=FONT_FAMILY_BOLD)
            ),
            margin={"r":5,"t":60,"l":5,"b":5},
            paper_bgcolor=paper_bg,
            coloraxis_colorbar=dict(
                title="TFR",
                title_font=dict(size=14, color=title_color),
                tickfont=dict(color=title_color),
                len=0.8,
                thickness=20
            )
        )
        
        return fig
        
    except Exception as e:
        print(f"  TFR map error: {e}")
        return go.Figure().add_annotation(text=f"Map Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))

#   ASFR map 
@app.callback(
    Output('asfr-map', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('age-dropdown', 'value'),
     Input('dark-mode-state', 'data')]
)
def update_asfr_map(selected_year, selected_age, dark_mode_data):
    try:
        is_dark = dark_mode_data.get('isDark', False) if dark_mode_data else False
        
        if not selected_year or not selected_age:
            return go.Figure().add_annotation(text="Please select year and age", 
                                           showarrow=False, font=dict(size=16, color='#eeeeee' if is_dark else COLORS['text']))
        
        filtered_asfr = asfr_clean[
            (asfr_clean['year'] == selected_year) &
            (asfr_clean['age'] == selected_age)
        ]
        
        if filtered_asfr.empty:
            return go.Figure().add_annotation(text="No data available for selection", 
                                           showarrow=False, font=dict(size=16, color='#eeeeee' if is_dark else COLORS['text']))
        
        # Choose mapbox style based on theme
        mapbox_style = 'carto-darkmatter' if is_dark else 'carto-positron'
        
        #   ASFR map 
        fig = px.choropleth_mapbox(
            filtered_asfr,
            geojson=filtered_asfr.__geo_interface__,
            locations='LAD23CD',
            featureidkey='properties.LAD23CD',
            color='fertility_rate',
            hover_name='LAD23NM',
            hover_data={'fertility_rate': ':.4f', 'LAD23CD': False},
            color_continuous_scale='Plasma',  
            mapbox_style=mapbox_style,
            zoom=5.3,
            center={"lat": 54.5, "lon": -2.5},
            opacity=0.85
        )
        
        # Dark mode styling
        title_color = '#eeeeee' if is_dark else COLORS['primary']
        paper_bg = '#16213e' if is_dark else 'white'
        
        fig.update_layout(
            title=dict(
                text=f"ASFR Age {selected_age} ({selected_year})",
                x=0.5,
                font=dict(size=18, color=title_color, family=FONT_FAMILY_BOLD)
            ),
            margin={"r":5,"t":60,"l":5,"b":5},
            paper_bgcolor=paper_bg,
            coloraxis_colorbar=dict(
                title=f"ASFR (Age {selected_age})",
                title_font=dict(size=14, color=title_color),
                tickfont=dict(color=title_color),
                len=0.8,
                thickness=20
            )
        )
        
        return fig
        
    except Exception as e:
        print(f"  ASFR map error: {e}")
        return go.Figure().add_annotation(text=f"Map Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))

#   TFR trend with styling 
@app.callback(
    Output('tfr-trend', 'figure'),
    [Input('lad-dropdown', 'value'),
     Input('dark-mode-state', 'data')]
)
def update_tfr_trend(selected_lads, dark_mode_data):
    try:
        is_dark = dark_mode_data.get('isDark', False) if dark_mode_data else False
        
        if not selected_lads or len(selected_lads) == 0:
            return go.Figure().add_annotation(text="Please select at least one Local Authority", 
                                           showarrow=False, font=dict(size=16, color='#eeeeee' if is_dark else COLORS['text']))
        
        fig = go.Figure()
        
        # Choose color palette based on theme
        active_chart_colors = CHART_DARK_COLORS if is_dark else CHART_COLORS
        
        # Add trace for each selected LAD
        for idx, lad in enumerate(selected_lads):
            lad_data = tfr_clean[tfr_clean['LAD23NM'] == lad].copy()
            
            if not lad_data.empty:
                lad_data['year_int'] = lad_data['year'].astype(int)
                lad_data = lad_data.sort_values('year_int')
                
                marker_line_color = '#1a1a2e' if is_dark else 'white'
                
                fig.add_trace(
                    go.Scatter(
                        x=lad_data['year_int'],
                        y=lad_data['tfr'],
                        mode='lines+markers',
                        name=lad,
                        line=dict(color=active_chart_colors[idx % len(active_chart_colors)], width=3),
                        marker=dict(size=6, line=dict(color=marker_line_color, width=1))
                    )
                )
        
        #   UK average
        uk_avg_by_year = tfr_clean.groupby('year')['tfr'].mean().reset_index()
        uk_avg_by_year['year_int'] = uk_avg_by_year['year'].astype(int)
        uk_avg_by_year = uk_avg_by_year.sort_values('year_int')
        
        avg_line_color = '#888888' if is_dark else 'gray'
        
        fig.add_trace(
            go.Scatter(
                x=uk_avg_by_year['year_int'],
                y=uk_avg_by_year['tfr'],
                mode='lines',
                name='UK Average',
                line=dict(color=avg_line_color, width=3, dash='dash'),
                opacity=0.8
            )
        )
        
        #   replacement level line
        fig.add_hline(y=2.1, line_dash="dot", line_color=COLORS['warning'], line_width=3,
                     annotation_text="UK Replacement Level (2.1)", 
                     annotation_font=dict(color=COLORS['warning'], size=12))
        
        title_text = f"TFR Trend Analysis: {', '.join(selected_lads[:3])}"
        if len(selected_lads) > 3:
            title_text += f" (+{len(selected_lads)-3} more)"
        
        # Dark mode styling
        title_color = '#eeeeee' if is_dark else COLORS['primary']
        axis_color = '#aaaaaa' if is_dark else COLORS['text']
        plot_bg = 'rgba(26,26,46,0.8)' if is_dark else 'rgba(248,249,250,0.8)'
        paper_bg = '#16213e' if is_dark else 'white'
        legend_bg = 'rgba(15,52,96,0.8)' if is_dark else 'rgba(255,255,255,0.8)'
        grid_color = 'rgba(255,255,255,0.1)' if is_dark else 'rgba(0,0,0,0.1)'
        
        fig.update_layout(
            title=dict(
                text=title_text,
                x=0.5,
                font=dict(size=16, color=title_color, family=FONT_FAMILY_BOLD)
            ),
            xaxis_title="Year",
            yaxis_title="Total Fertility Rate",
            xaxis=dict(
                color=axis_color,
                gridcolor=grid_color
            ),
            yaxis=dict(
                color=axis_color,
                gridcolor=grid_color
            ),
            height=400,
            hovermode='x unified',
            plot_bgcolor=plot_bg,
            paper_bgcolor=paper_bg,
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor=legend_bg,
                font=dict(color=title_color)
            )
        )
        
        return fig
        
    except Exception as e:
        print(f"  TFR trend error: {e}")
        return go.Figure().add_annotation(text=f"Trend Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))

#   ASFR trend with styling 
@app.callback(
    Output('asfr-trend', 'figure'),
    [Input('lad-dropdown', 'value'),
     Input('year-dropdown', 'value'),
     Input('dark-mode-state', 'data')]
)
def update_asfr_trend(selected_lads, selected_year, dark_mode_data):
    try:
        is_dark = dark_mode_data.get('isDark', False) if dark_mode_data else False
        
        if not selected_lads or len(selected_lads) == 0 or not selected_year:
            return go.Figure().add_annotation(text="Please select at least one LAD and a year", 
                                           showarrow=False, font=dict(size=16, color='#eeeeee' if is_dark else COLORS['text']))
        
        fig = go.Figure()
        
        # Choose color palette based on theme
        active_chart_colors = CHART_DARK_COLORS if is_dark else CHART_COLORS
        
        # Add trace for each selected LAD
        for idx, lad in enumerate(selected_lads):
            lad_year_data = asfr_clean[
                (asfr_clean['LAD23NM'] == lad) &
                (asfr_clean['year'] == selected_year)
            ].copy()
            
            if not lad_year_data.empty:
                # Convert age to int for plotting
                lad_year_data['age_int'] = lad_year_data['age'].astype(int)
                lad_year_data = lad_year_data.sort_values('age_int')
                
                # LAD ASFR by age 
                fig.add_trace(
                    go.Scatter(
                        x=lad_year_data['age_int'],
                        y=lad_year_data['fertility_rate'],
                        mode='lines',  # Changed from 'lines+markers' to 'lines'
                        name=lad,
                        line=dict(color=active_chart_colors[idx % len(active_chart_colors)], width=3)
                    )
                )
        
        # UK average by age for selected year
        uk_avg_age = asfr_clean[asfr_clean['year'] == selected_year].groupby('age')['fertility_rate'].mean().reset_index()
        uk_avg_age['age_int'] = uk_avg_age['age'].astype(int)
        uk_avg_age = uk_avg_age.sort_values('age_int')
        
        avg_line_color = '#888888' if is_dark else 'gray'
        
        fig.add_trace(
            go.Scatter(
                x=uk_avg_age['age_int'],
                y=uk_avg_age['fertility_rate'],
                mode='lines',
                name='UK Average',
                line=dict(color=avg_line_color, width=3, dash='dash'),
                opacity=0.8
            )
        )
        
        title_text = f"ASFR by Age ({selected_year}): {', '.join(selected_lads[:3])}"
        if len(selected_lads) > 3:
            title_text += f" (+{len(selected_lads)-3} more)"
        
        # Dark mode styling
        title_color = '#eeeeee' if is_dark else COLORS['primary']
        axis_color = '#aaaaaa' if is_dark else COLORS['text']
        plot_bg = 'rgba(26,26,46,0.8)' if is_dark else 'rgba(248,249,250,0.8)'
        paper_bg = '#16213e' if is_dark else 'white'
        legend_bg = 'rgba(15,52,96,0.8)' if is_dark else 'rgba(255,255,255,0.8)'
        grid_color = 'rgba(255,255,255,0.1)' if is_dark else 'rgba(0,0,0,0.1)'
        
        fig.update_layout(
            title=dict(
                text=title_text,
                x=0.5,
                font=dict(size=16, color=title_color, family=FONT_FAMILY_BOLD)
            ),
            xaxis_title="Age",
            yaxis_title="Age-Specific Fertility Rate",
            xaxis=dict(
                tickmode='linear',
                tick0=15,
                dtick=5,
                range=[14, 50],
                color=axis_color,
                gridcolor=grid_color
            ),
            yaxis=dict(
                color=axis_color,
                gridcolor=grid_color
            ),
            height=400,
            hovermode='x unified',
            plot_bgcolor=plot_bg,
            paper_bgcolor=paper_bg,
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor=legend_bg,
                font=dict(color=title_color)
            )
        )
        
        return fig
        
    except Exception as e:
        print(f"  ASFR trend error: {e}")
        return go.Figure().add_annotation(text=f"Trend Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))


# CLIENTSIDE CALLBACKS JavaScript for Performance & Animations

# Clientside callback 1: Animate cards on dropdown change with smooth transitions
app.clientside_callback(
    """
    function(year, age, lad) {
        // Animate metric cards when any control changes
        const cards = document.querySelectorAll('.metric-card');
        cards.forEach((card, index) => {
            // Add staggered animation effect
            setTimeout(() => {
                card.style.transform = 'scale(1.05)';
                card.style.transition = 'transform 0.3s ease-out';
                
                setTimeout(() => {
                    card.style.transform = 'scale(1)';
                }, 200);
            }, index * 100);
        });
        
        // Pulse effect on control panel
        const controlPanel = document.querySelector('.control-panel');
        if (controlPanel) {
            controlPanel.style.boxShadow = '0 8px 30px rgba(30, 58, 138, 0.3)';
            setTimeout(() => {
                controlPanel.style.boxShadow = '0 4px 15px rgba(0,0,0,0.1)';
            }, 500);
        }
        
        // Return timestamp to trigger store update
        return {timestamp: Date.now(), changed: true};
    }
    """,
    Output('last-update-time', 'data'),
    [Input('year-dropdown', 'value'),
     Input('age-dropdown', 'value'),
     Input('lad-dropdown', 'value')]
)

# Clientside callback 2: Add ripple effect to graphs on hover
app.clientside_callback(
    """
    function(timestamp) {
        // Only add event listeners once
        if (!window.graphHoverListenersAdded) {
            const graphs = document.querySelectorAll('.graph-container');
            
            graphs.forEach(graph => {
                graph.addEventListener('mouseenter', function(e) {
                    this.style.transform = 'translateY(-5px)';
                    this.style.transition = 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)';
                });
                
                graph.addEventListener('mouseleave', function(e) {
                    this.style.transform = 'translateY(0)';
                });
            });
            
            // Mark as added
            window.graphHoverListenersAdded = true;
        }
        
        return window.dash_clientside.no_update;
    }
    """,
    Output('card-animation-target', 'children'),
    [Input('last-update-time', 'data')]
)

# Clientside callback 3: Add loading shimmer effect during graph updates
app.clientside_callback(
    """
    function(year) {
        // Add shimmer effect to graphs while loading
        const graphs = document.querySelectorAll('.js-plotly-plot');
        
        graphs.forEach(graph => {
            const parent = graph.closest('.graph-container');
            if (parent) {
                parent.style.opacity = '0.7';
                parent.style.transition = 'opacity 0.2s ease-in';
                
                setTimeout(() => {
                    parent.style.opacity = '1';
                    parent.style.transition = 'opacity 0.4s ease-out';
                }, 300);
            }
        });
        
        // Add sparkle effect to the updated graphs
        setTimeout(() => {
            graphs.forEach((graph, idx) => {
                setTimeout(() => {
                    const parent = graph.closest('.graph-container');
                    if (parent) {
                        parent.style.boxShadow = '0 10px 40px rgba(30, 58, 138, 0.4)';
                        setTimeout(() => {
                            parent.style.boxShadow = '0 6px 20px rgba(0,0,0,0.12)';
                        }, 400);
                    }
                }, idx * 150);
            });
        }, 500);
        
        return {count: Math.random()};
    }
    """,
    Output('animation-trigger', 'data'),
    [Input('year-dropdown', 'value')]
)

# Clientside callback 4: Dark Mode Toggle, Updates toggle state and store
app.clientside_callback(
    """
    function(toggleValue) {
        // Check if this is initial load
        if (toggleValue === undefined) {
            // On initial load, check localStorage for saved preference
            const savedTheme = localStorage.getItem('darkMode');
            const isDark = savedTheme === 'true';
            if (isDark) {
                document.body.classList.add('dark-mode');
            }
            return [isDark ? [1] : [], {isDark: isDark}];
        }
        
        // Toggle is on if value array has length > 0
        const isDark = toggleValue && toggleValue.length > 0;
        
        // Apply dark mode class to body
        if (isDark) {
            document.body.classList.add('dark-mode');
        } else {
            document.body.classList.remove('dark-mode');
        }
        
        // Save preference to localStorage
        localStorage.setItem('darkMode', isDark);
        
        // Update store
        return [toggleValue, {isDark: isDark}];
    }
    """,
    [Output('theme-toggle-button', 'value'),
     Output('dark-mode-state', 'data')],
    [Input('theme-toggle-button', 'value')]
)

# Clientside callback 5: Sidebar Toggle
app.clientside_callback(
    """
    function(toggleClicks, closeClicks) {
        const sidebar = document.getElementById('sidebar');
        const sidebarContainer = document.querySelector('.sidebar-container');
        const toggleBtn = document.getElementById('sidebar-toggle');
        
        if (!sidebar || !sidebarContainer) {
            return window.dash_clientside.no_update;
        }
        
        // Check if either button was clicked
        const ctx = window.dash_clientside.callback_context;
        if (!ctx.triggered || ctx.triggered.length === 0) {
            // Initial load - check localStorage
            const savedState = localStorage.getItem('sidebarCollapsed');
            if (savedState === 'true') {
                sidebar.classList.add('collapsed');
                sidebarContainer.classList.add('collapsed');
                if (toggleBtn) toggleBtn.classList.remove('hidden');
            } else {
                if (toggleBtn) toggleBtn.classList.add('hidden');
            }
            return window.dash_clientside.no_update;
        }
        
        // Toggle the sidebar
        const isCollapsed = sidebar.classList.toggle('collapsed');
        sidebarContainer.classList.toggle('collapsed');
        
        // Toggle button visibility
        if (toggleBtn) {
            if (isCollapsed) {
                toggleBtn.classList.remove('hidden');
            } else {
                toggleBtn.classList.add('hidden');
            }
        }
        
        // Save state
        localStorage.setItem('sidebarCollapsed', isCollapsed);
        
        // On mobile, also toggle 'open' class
        if (window.innerWidth <= 768) {
            sidebar.classList.toggle('open');
        }
        
        return window.dash_clientside.no_update;
    }
    """,
    Output('sidebar-collapsed', 'data'),
    [Input('sidebar-toggle', 'n_clicks'),
     Input('sidebar-close', 'n_clicks')]
)


if __name__ == '__main__':
    print(f"Starting UK Fertility Dashboard on port {PORT}...")
    app.run(debug=True, port=PORT)

