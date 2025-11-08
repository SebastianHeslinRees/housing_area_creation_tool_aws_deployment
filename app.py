# FERTILITY DASHBOARD -     Version
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

# ----------------- Data Loading Functions -----------------
def download_from_s3_if_needed(filename, bucket=S3_BUCKET, prefix=S3_PREFIX):
    """Download file from S3 if not present locally (for AWS deployment)"""
    if os.path.exists(filename):
        print(f"✓ Using local file: {filename}")
        return filename
    
    try:
        import boto3
        s3_key = f"{prefix}{filename}"
        print(f"⬇ Downloading s3://{bucket}/{s3_key}...")
        s3 = boto3.client('s3', region_name=S3_REGION)
        s3.download_file(bucket, s3_key, filename)
        file_size_mb = os.path.getsize(filename) / (1024 * 1024)
        print(f"✓ Downloaded {filename} successfully ({file_size_mb:.1f} MB)")
        return filename
    except Exception as e:
        print(f"❌ Error downloading {filename} from S3: {e}")
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
    print(f"❌ FATAL ERROR loading data: {e}")
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
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE])
app.title = "UK Fertility Dashboard - Enhanced"
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
        <style>
            /*   Loading Spinner Overlay */
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, #1e3a8a 0%, #ea580c 100%);
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                z-index: 9999;
                transition: opacity 0.5s ease-out;
            }
            
            /*   Spinner Animation */
            .spinner {
                width: 80px;
                height: 80px;
                border: 6px solid rgba(255, 255, 255, 0.3);
                border-top: 6px solid white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-bottom: 20px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /*   Loading Text */
            .loading-text {
                color: white;
                font-family: "Arial", sans-serif;
                font-size: 28px;
                font-weight: bold;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                margin-bottom: 10px;
                letter-spacing: 1px;
            }
            
            .loading-subtext {
                color: rgba(255, 255, 255, 0.95);
                font-family: "Arial", sans-serif;
                font-size: 16px;
                text-align: center;
                max-width: 350px;
                font-weight: 300;
            }
            
            /* GLA logo in loading screen */
            .loading-logo {
                width: 70px;
                height: 70px;
                margin-bottom: 30px;
                border-radius: 50%;
                background: white;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 6px 20px rgba(0,0,0,0.25);
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }
            
            .loading-logo img {
                width: 50px;
                height: 50px;
                object-fit: contain;
            }
            
            /*   Card Styling */
            .metric-card {
                transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
                border-radius: 12px !important;
            }
            
            .metric-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15) !important;
            }
            
            /*   Control Panel */
            .control-panel {
                background: linear-gradient(145deg, #ffffff 0%, #f8f9fa 100%);
                border-radius: 15px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }
            
            /*   Graph Containers */
            .graph-container {
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 6px 20px rgba(0,0,0,0.12);
                transition: box-shadow 0.3s ease;
            }
            
            .graph-container:hover {
                box-shadow: 0 8px 25px rgba(0,0,0,0.18);
            }
            
            /*   Typography */
            .dashboard-title {
                background: linear-gradient(45deg, #1e3a8a, #ea580c);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                font-weight: 800;
                letter-spacing: -0.5px;
            }
            
            /* Custom Dropdown Styling */
            .Select-control {
                border-radius: 8px !important;
                border: 2px solid #e9ecef !important;
                transition: all 0.2s ease !important;
            }
            
            .Select-control:hover {
                border-color: #1e3a8a !important;
            }
            
            /* Fade-in animation for logo */
            @keyframes fadeIn {
                0% { opacity: 0; transform: translateY(-10px); }
                100% { opacity: 1; transform: translateY(0); }
            }
        </style>
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

#colour scheme -  Orange & Blue
colors = {
    'primary': '#1e3a8a',      # Deep blue
    'secondary': '#ea580c',    # Stylish orange  
    'accent': '#3b82f6',       # Bright blue accent
    'background': '#F8F9FA',   # Light background
    'text': '#2C3E50',         # Dark text
    'success': '#1d4ed8',      # Success blue
    'warning': '#f59e0b',      # Warning orange
    'card_bg': '#ffffff'       # Pure white cards
}

#Layout
app.layout = dbc.Container([
    
    #   Banner Header with GLA Logo
    html.Div([
        # Banner with gradient background
        html.Div([
            dbc.Row([
                dbc.Col([
                    html.Img(
                        src="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png",
                        style={
                            'height': '210px',
                            'filter': 'brightness(0) invert(1)',  # White logo
                            'animation': 'fadeIn 1s ease-in'
                        }
                    )
                ], width=2, className="d-flex align-items-center justify-content-center"),
                
                dbc.Col([
                    html.H1("UK Fertility Rate Dashboard", 
                           className="text-center mb-2",
                           style={
                               'fontSize': '2.8rem', 
                               'fontWeight': '800', 
                               'color': 'white',
                               'textShadow': '2px 2px 4px rgba(0,0,0,0.3)',
                               'letterSpacing': '-0.5px'
                           }),
                    html.H5("Comprehensive Analysis of Total & Age-Specific Fertility Rates (1993-2023)",
                           className="text-center mb-0",
                           style={
                               'fontWeight': '300', 
                               'color': 'rgba(255,255,255,0.95)',
                               'letterSpacing': '0.5px'
                           })
                ], width=8, className="d-flex flex-column justify-content-center"),
                
                dbc.Col(width=2)
            ], className="align-items-center")
        ], style={
            'background': f'linear-gradient(135deg, {colors["primary"]} 0%, {colors["secondary"]} 100%)',
            'padding': '30px 20px',
            'marginBottom': '30px',
            'boxShadow': '0 6px 20px rgba(0,0,0,0.15)',
            'borderRadius': '0 0 15px 15px',
            'marginTop': '-25px',
            'marginLeft': '-25px',
            'marginRight': '-25px',
            'animation': 'fadeIn 1s ease-in'
        })
    ]),
    
    # Control Panel
    dbc.Card([
        dbc.CardBody([
            html.H4("Dashboard Controls", className="mb-4", 
                   style={'color': colors['primary'], 'fontWeight': '600'}),
            
            dbc.Row([
                # Year Dropdown with   styling
                dbc.Col([
                    html.Label("Select Year", className="fw-bold mb-2",
                              style={'color': colors['text'], 'fontSize': '14px'}),
                    dcc.Dropdown(
                        id='year-dropdown',
                        options=[{'label': year, 'value': year} for year in years],
                        value=years[-1],
                        clearable=False,
                        style={'marginBottom': '15px'}
                    )
                ], width=4),
                
                # Age Dropdown with   styling
                dbc.Col([
                    html.Label("Select Age (ASFR)", className="fw-bold mb-2",
                              style={'color': colors['text'], 'fontSize': '14px'}),
                    dcc.Dropdown(
                        id='age-dropdown',
                        options=[{'label': f"Age {age}", 'value': age} for age in ages],
                        value="30",
                        clearable=False,
                        style={'marginBottom': '15px'}
                    )
                ], width=4),
                
                # LAD Dropdown with search
                dbc.Col([
                    html.Label("Local Authority", className="fw-bold mb-2",
                              style={'color': colors['text'], 'fontSize': '14px'}),
                    dcc.Dropdown(
                        id='lad-dropdown',
                        options=[{'label': lad, 'value': lad} for lad in lads],
                        value="Manchester",
                        clearable=False,
                        placeholder="Search Local Authority...",
                        style={'marginBottom': '15px'}
                    )
                ], width=4)
            ])
        ])
    ], className="mb-4 control-panel"),
    
    # Summary Metrics
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.H4(id="tfr-title", children="Total Fertility Rate", style={'color': colors['primary'], 'fontWeight': '600'}),
                        html.H2(id="current-tfr", children="--", 
                               style={'color': colors['secondary'], 'fontWeight': '700', 'fontSize': '2.5rem'})
                    ], className="text-center")
                ])
            ], className="metric-card", style={'backgroundColor': colors['card_bg'], 
                                              'borderLeft': f'5px solid {colors["secondary"]}',
                                              'boxShadow': '0 4px 15px rgba(0,0,0,0.1)'})
        ], width=4),
        
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.H4(id="comparison-title", children="vs UK Average", style={'color': colors['primary'], 'fontWeight': '600'}),
                        html.H2(id="tfr-comparison", children="--", 
                               style={'color': colors['accent'], 'fontWeight': '700', 'fontSize': '2.5rem'})
                    ], className="text-center")
                ])
            ], className="metric-card", style={'backgroundColor': colors['card_bg'], 
                                              'borderLeft': f'5px solid {colors["accent"]}',
                                              'boxShadow': '0 4px 15px rgba(0,0,0,0.1)'})
        ], width=4),
        
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        html.H4("Replacement Level", style={'color': colors['primary'], 'fontWeight': '600'}),
                        html.H2("2.1", style={'color': colors['warning'], 'fontWeight': '700', 'fontSize': '2.5rem'}),
                        html.P(id="replacement-status", children="--", className="text-muted")
                    ], className="text-center")
                ])
            ], className="metric-card", style={'backgroundColor': colors['card_bg'], 
                                              'borderLeft': f'5px solid {colors["warning"]}',
                                              'boxShadow': '0 4px 15px rgba(0,0,0,0.1)'})
        ], width=4)
    ], className="mb-4"),
    
    #   Maps Section
    dbc.Row([
        # TFR Map
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("Total Fertility Rate Map", className="text-center mb-0",
                           style={'color': colors['primary'], 'fontWeight': '600'})
                ], style={'backgroundColor': colors['background']}),
                dbc.CardBody([
                    dcc.Graph(id='tfr-map', style={'height': '520px'})
                ], style={'padding': '0'})
            ], className="graph-container")
        ], width=6),
        
        # ASFR Map 
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("Age-Specific Fertility Rate Map", className="text-center mb-0",
                           style={'color': colors['primary'], 'fontWeight': '600'})
                ], style={'backgroundColor': colors['background']}),
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
                    html.H5("TFR Trend Analysis", className="text-center mb-0",
                           style={'color': colors['primary'], 'fontWeight': '600'})
                ], style={'backgroundColor': colors['background']}),
                dbc.CardBody([
                    dcc.Graph(id='tfr-trend', style={'height': '420px'})
                ], style={'padding': '0'})
            ], className="graph-container")
        ], width=6),
        
        # ASFR Trend 
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("ASFR Trend Analysis", className="text-center mb-0",
                           style={'color': colors['primary'], 'fontWeight': '600'})
                ], style={'backgroundColor': colors['background']}),
                dbc.CardBody([
                    dcc.Graph(id='asfr-trend', style={'height': '420px'})
                ], style={'padding': '0'})
            ], className="graph-container")
        ], width=6)
    ], className="mb-4"),
    
    # Footer
    dbc.Row([
        dbc.Col([
            html.Hr(style={'borderColor': colors['secondary'], 'marginTop': '40px'}),
            dbc.Alert([
                html.H5("About This Dashboard", className="alert-heading",
                       style={'color': colors['primary'], 'fontWeight': 'bold'}),
                html.P([
                         "This dashboard provides analysis of UK fertility rates using the GLA Fertility Estimates. ",
                            "The code used to produce these estimates is available on ",
                            html.A(
                            "GitHub",  # Text that will show as a link
                        href="https://github.com/Greater-London-Authority/fertility_rate_estimation/tree/main",
                        target="_blank"  # Opens link in a new tab
                                   ,style={'color': colors['primary']}),
                        html.Br(),
                    html.Strong("TFR (Total Fertility Rate)"), " Total fertility rate (TFR) is a commonly used measure of overall fertility calculated as the sum of all age-specific fertility rates across all reproductive age groups. It represents the average number of children that a woman would have if she were to experience current age-specific fertility rates over the course of her life. For 2023, we estimate the TFR in Inner London to have been 1.16 compared to 1.54 in Outer London, and 1.41 for England as whole.",
                        html.Br(),
                    html.Strong("ASFR (Age-Specific Fertility Rate, 15 to 49)"), " measures the number of births per woman within specific age groups. For example, in England, the peak childbearing age is currently 32, with an ASFR of 0.107, meaning 107 babies were born for each 1,000 women aged 32.",
                    "The UK replacement fertility rate is approximately ", html.Strong("2.1 children per woman"), "."
                ], className="mb-2", style={'color': colors['primary']}),
                html.P([
                    "Use the controls above to explore different years, ages, and local authorities. ",
                    "Interactive maps maintain their fertility-specific colour schemes. ",
                    "Compare trends across time and regions with visualisations. Visualisations can be easily downloaded using the camera icon in the top-right corner of each graph."
                ], className="mb-0", style={'color': colors['primary']})
            ], color="navy", style={'backgroundColor': 'rgba(46, 139, 87, 0.1)', 
                                   'borderColor': colors['primary']}, className="mb-3"),
            
            html.P([
                "GLA Fertility Dashboard | Data: ONS | ",
                html.A("Office for National Statistics", 
                      href="https://www.ons.gov.uk", 
                      style={'color': colors['primary'], 'textDecoration': 'none'})
            ], className="text-center text-muted", style={'fontSize': '14px'})
        ])
    ])
    
], fluid=True, style={'padding': '25px', 'backgroundColor': colors['background'], 
                     'minHeight': '100vh'})

# ==========   CALLBACKS (Same Logic,   Styling) ==========

# Update metrics with   formatting
@app.callback(
    [Output('current-tfr', 'children'),
     Output('tfr-comparison', 'children'),
     Output('replacement-status', 'children')],
    [Input('year-dropdown', 'value'),
     Input('lad-dropdown', 'value')]
)
def update_metrics(selected_year, selected_lad):
    try:
        if selected_lad and selected_year:
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

#   TFR map (keeping RdYlBu_r colour scheme)
@app.callback(
    Output('tfr-map', 'figure'),
    [Input('year-dropdown', 'value')]
)
def update_tfr_map(selected_year):
    try:
        if not selected_year:
            return go.Figure().add_annotation(text="Please select a year", showarrow=False, 
                                           font=dict(size=16, color=colors['text']))
        
        filtered_tfr = tfr_clean[tfr_clean['year'] == selected_year]
        
        if filtered_tfr.empty:
            return go.Figure().add_annotation(text="No data available for selected year", 
                                           showarrow=False, font=dict(size=16, color=colors['text']))
        
        #   TFR map (KEEPING original fertility colour scheme)
        fig = px.choropleth_mapbox(
            filtered_tfr,
            geojson=filtered_tfr.__geo_interface__,
            locations='LAD23CD',
            featureidkey='properties.LAD23CD',
            color='tfr',
            hover_name='LAD23NM',
            hover_data={'tfr': ':.3f', 'LAD23CD': False},
            color_continuous_scale='RdYlBu_r',  # KEPT: Red=high, Blue=low fertility
            mapbox_style='carto-positron',
            zoom=5.3,
            center={"lat": 54.5, "lon": -2.5},
            opacity=0.85
        )
        
        fig.update_layout(
            title=dict(
                text=f"Total Fertility Rate ({selected_year})",
                x=0.5,
                font=dict(size=18, color=colors['primary'], family="Arial Black")
            ),
            margin={"r":5,"t":60,"l":5,"b":5},
            coloraxis_colorbar=dict(
                title="TFR",
                title_font=dict(size=14, color=colors['primary']),
                len=0.8,
                thickness=20
            )
        )
        
        return fig
        
    except Exception as e:
        print(f"  TFR map error: {e}")
        return go.Figure().add_annotation(text=f"Map Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))

#   ASFR map (keeping Plasma colour scheme)
@app.callback(
    Output('asfr-map', 'figure'),
    [Input('year-dropdown', 'value'),
     Input('age-dropdown', 'value')]
)
def update_asfr_map(selected_year, selected_age):
    try:
        if not selected_year or not selected_age:
            return go.Figure().add_annotation(text="Please select year and age", 
                                           showarrow=False, font=dict(size=16, color=colors['text']))
        
        filtered_asfr = asfr_clean[
            (asfr_clean['year'] == selected_year) &
            (asfr_clean['age'] == selected_age)
        ]
        
        if filtered_asfr.empty:
            return go.Figure().add_annotation(text="No data available for selection", 
                                           showarrow=False, font=dict(size=16, color=colors['text']))
        
        #   ASFR map (KEEPING original fertility colour scheme)
        fig = px.choropleth_mapbox(
            filtered_asfr,
            geojson=filtered_asfr.__geo_interface__,
            locations='LAD23CD',
            featureidkey='properties.LAD23CD',
            color='fertility_rate',
            hover_name='LAD23NM',
            hover_data={'fertility_rate': ':.4f', 'LAD23CD': False},
            color_continuous_scale='Plasma',  # KEPT: Original ASFR colour scheme
            mapbox_style='carto-positron',
            zoom=5.3,
            center={"lat": 54.5, "lon": -2.5},
            opacity=0.85
        )
        
        fig.update_layout(
            title=dict(
                text=f"ASFR Age {selected_age} ({selected_year})",
                x=0.5,
                font=dict(size=18, color=colors['primary'], family="Arial Black")
            ),
            margin={"r":5,"t":60,"l":5,"b":5},
            coloraxis_colorbar=dict(
                title=f"ASFR (Age {selected_age})",
                title_font=dict(size=14, color=colors['primary']),
                len=0.8,
                thickness=20
            )
        )
        
        return fig
        
    except Exception as e:
        print(f"  ASFR map error: {e}")
        return go.Figure().add_annotation(text=f"Map Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))

#   TFR trend with   styling
@app.callback(
    Output('tfr-trend', 'figure'),
    [Input('lad-dropdown', 'value')]
)
def update_tfr_trend(selected_lad):
    try:
        if not selected_lad:
            return go.Figure().add_annotation(text="Please select a Local Authority", 
                                           showarrow=False, font=dict(size=16, color=colors['text']))
        
        lad_data = tfr_clean[tfr_clean['LAD23NM'] == selected_lad].copy()
        
        if lad_data.empty:
            return go.Figure().add_annotation(text=f"No TFR data available for {selected_lad}", 
                                           showarrow=False, font=dict(size=14, color=colors['text']))
        
        # Convert for plotting
        lad_data['year_int'] = lad_data['year'].astype(int)
        lad_data = lad_data.sort_values('year_int')
        
        fig = go.Figure()
        
        #   LAD trend line
        fig.add_trace(
            go.Scatter(
                x=lad_data['year_int'],
                y=lad_data['tfr'],
                mode='lines+markers',
                name=selected_lad,
                line=dict(color=colors['primary'], width=4),
                marker=dict(size=8, color=colors['secondary'], 
                          line=dict(color='white', width=2))
            )
        )
        
        #   UK average
        uk_avg_by_year = tfr_clean.groupby('year')['tfr'].mean().reset_index()
        uk_avg_by_year['year_int'] = uk_avg_by_year['year'].astype(int)
        uk_avg_by_year = uk_avg_by_year.sort_values('year_int')
        
        fig.add_trace(
            go.Scatter(
                x=uk_avg_by_year['year_int'],
                y=uk_avg_by_year['tfr'],
                mode='lines',
                name='UK Average',
                line=dict(color='gray', width=3, dash='dash'),
                opacity=0.8
            )
        )
        
        #   replacement level line
        fig.add_hline(y=2.1, line_dash="dot", line_color=colors['warning'], line_width=3,
                     annotation_text="UK Replacement Level (2.1)", 
                     annotation_font=dict(color=colors['warning'], size=12))
        
        fig.update_layout(
            title=dict(
                text=f"TFR Trend Analysis: {selected_lad}",
                x=0.5,
                font=dict(size=16, color=colors['primary'], family="Arial Black")
            ),
            xaxis_title="Year",
            yaxis_title="Total Fertility Rate",
            height=400,
            hovermode='x unified',
            plot_bgcolor='rgba(248,249,250,0.8)',
            paper_bgcolor='white'
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
     Input('age-dropdown', 'value')]
)
def update_asfr_trend(selected_lad, selected_age):
    try:
        if not selected_lad or not selected_age:
            return go.Figure().add_annotation(text="Please select LAD and age", 
                                           showarrow=False, font=dict(size=16, color=colors['text']))
        
        lad_age_data = asfr_clean[
            (asfr_clean['LAD23NM'] == selected_lad) &
            (asfr_clean['age'] == selected_age)
        ].copy()
        
        if lad_age_data.empty:
            return go.Figure().add_annotation(
                text=f"No ASFR data for {selected_lad}, Age {selected_age}", 
                showarrow=False, font=dict(size=14, color=colors['text'])
            )
        
        # Convert for plotting
        lad_age_data['year_int'] = lad_age_data['year'].astype(int)
        lad_age_data = lad_age_data.sort_values('year_int')
        
        fig = go.Figure()
        
        #   LAD ASFR trend
        fig.add_trace(
            go.Scatter(
                x=lad_age_data['year_int'],
                y=lad_age_data['fertility_rate'],
                mode='lines+markers',
                name=f"{selected_lad} (Age {selected_age})",
                line=dict(color=colors['secondary'], width=4),
                marker=dict(size=8, color=colors['accent'], 
                          line=dict(color='white', width=2))
            )
        )
        
        #   UK average for age
        uk_avg_age = asfr_clean[asfr_clean['age'] == selected_age].groupby('year')['fertility_rate'].mean().reset_index()
        uk_avg_age['year_int'] = uk_avg_age['year'].astype(int)
        uk_avg_age = uk_avg_age.sort_values('year_int')
        
        fig.add_trace(
            go.Scatter(
                x=uk_avg_age['year_int'],
                y=uk_avg_age['fertility_rate'],
                mode='lines',
                name='UK Average',
                line=dict(color='gray', width=3, dash='dash'),
                opacity=0.8
            )
        )
        
        fig.update_layout(
            title=dict(
                text=f"ASFR Trend Analysis (Age {selected_age}): {selected_lad}",
                x=0.5,
                font=dict(size=16, color=colors['primary'], family="Arial Black")
            ),
            xaxis_title="Year",
            yaxis_title="Age-Specific Fertility Rate",
            height=400,
            hovermode='x unified',
            plot_bgcolor='rgba(248,249,250,0.8)',
            paper_bgcolor='white'
        )
        
        return fig
        
    except Exception as e:
        print(f"  ASFR trend error: {e}")
        return go.Figure().add_annotation(text=f"Trend Error: {str(e)[:50]}...", 
                                       showarrow=False, font=dict(size=14, color='red'))



if __name__ == '__main__':
    print(f"Starting UK Fertility Dashboard on port {PORT}...")
    app.run(debug=True, port=PORT)
