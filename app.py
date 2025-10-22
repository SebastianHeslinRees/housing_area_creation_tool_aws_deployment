
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import geopandas as gpd
from shapely import wkt

def _safe_load_wkt(val):
    if pd.isna(val):
        return None
    try:
        return wkt.loads(val)
    except Exception:
        return None

# Load and process data
print("Loading data...")
core_largesites_df = pd.read_csv('merged_Core_Largesites_gdf.csv')
ward_savills_df = pd.read_csv('merged_ward_savills_gdf.csv')

# Convert geometry
core_largesites_df['geometry'] = core_largesites_df['geometry'].apply(_safe_load_wkt)
ward_savills_df['geometry'] = ward_savills_df['geometry'].apply(_safe_load_wkt)

# Create GeoDataFrames
merged_Core_Largesites_gdf = gpd.GeoDataFrame(core_largesites_df, geometry='geometry', crs="EPSG:4326")
merged_ward_savills_gdf = gpd.GeoDataFrame(ward_savills_df, geometry='geometry', crs="EPSG:4326")

print("Data loaded successfully")

# --------- Dual Animated Map Function ---------
def create_dual_animated_map():
    ward_numeric = merged_ward_savills_gdf.select_dtypes(include=[np.number]).columns.tolist()
    sites_numeric = merged_Core_Largesites_gdf.select_dtypes(include=[np.number]).columns.tolist()
    
    ward_years = [col for col in ward_numeric if str(col).isdigit() and len(str(col)) == 4]
    sites_years = [col for col in sites_numeric if str(col).isdigit() and len(str(col)) == 4]
    common_years = sorted(set(ward_years) & set(sites_years))
    
    if not common_years:
        return None, []
    
    # Convert to integers for proper sorting
    common_years = sorted([int(year) for year in common_years])
    
    ward_gdf_web = merged_ward_savills_gdf.to_crs('EPSG:4326') if merged_ward_savills_gdf.crs != 'EPSG:4326' else merged_ward_savills_gdf
    sites_gdf_web = merged_Core_Largesites_gdf.to_crs('EPSG:4326') if merged_Core_Largesites_gdf.crs != 'EPSG:4326' else merged_Core_Largesites_gdf
    
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=('Savills Trajectory', 'Core Largesites Baseline'),
        specs=[[{'type': 'mapbox'}, {'type': 'mapbox'}]],
        horizontal_spacing=0.08
    )
    
    frames = []
    for year in common_years:
        frame_data = []
        ward_clean = ward_gdf_web.dropna(subset=[str(year), 'geometry'])
        sites_clean = sites_gdf_web.dropna(subset=[str(year), 'geometry'])
        
        # Calculate separate ranges for each dataset
        ward_values = ward_clean[str(year)].dropna().values if not ward_clean.empty else [0]
        sites_values = sites_clean[str(year)].dropna().values if not sites_clean.empty else [0]
        
        ward_min, ward_max = 0, max(ward_values) if len(ward_values) > 0 else 100
        sites_min, sites_max = 0, max(sites_values) if len(sites_values) > 0 else 100
        
        # Savills data with blue to orange colour scale and separate legend
        frame_data.append(
            go.Choroplethmapbox(
                geojson=ward_clean.__geo_interface__,
                locations=ward_clean.index,
                z=ward_clean[str(year)],
                colorscale=[[0, '#000080'], [1, '#FF4500']],  # Dark blue to dark orange
                zmin=ward_min,
                zmax=ward_max,
                text=ward_clean['wd22nm'],
                hovertemplate=f'<b>%{{text}}</b><br>Savills {year}: %{{z}}<extra></extra>',
                marker_opacity=0.7,
                marker_line_width=0.5,
                marker_line_color='white',
                name='Savills Data',
                showscale=True,
                colorbar=dict(
                    title=f"Savills Units ({year})", 
                    x=0.45, 
                    len=0.8, 
                    thickness=15,
                    title_side="right",
                )
            )
        )
        
        # Core Sites data with blue to orange colour scale and separate legend
        frame_data.append(
            go.Choroplethmapbox(
                geojson=sites_clean.__geo_interface__,
                locations=sites_clean.index,
                z=sites_clean[str(year)],
                colorscale=[[0, '#000080'], [1, '#FF4500']],  # Dark blue to dark orange
                zmin=sites_min,
                zmax=sites_max,
                text=sites_clean['wd22nm'],
                hovertemplate=f'<b>%{{text}}</b><br>Core Sites {year}: %{{z}}<extra></extra>',
                marker_opacity=0.7,
                marker_line_width=0.5,
                marker_line_color='white',
                name='Core Sites Data',
                showscale=True,
                colorbar=dict(
                    title=f"Core Sites Units ({year})", 
                    x=1.02, 
                    len=0.8, 
                    thickness=15,
                    title_side="right",
                )
            )
        )
        
        frames.append(go.Frame(data=frame_data, name=str(year)))
    
    # Initial traces
    if frames:
        fig.add_trace(frames[0].data[0], row=1, col=1)
        fig.add_trace(frames[0].data[1], row=1, col=2)
    
    fig.update_layout(
        title='Housing Units Added',
        mapbox1=dict(style='carto-positron', center={'lat': 51.5074, 'lon': -0.1278}, zoom=8),
        mapbox2=dict(style='carto-positron', center={'lat': 51.5074, 'lon': -0.1278}, zoom=8),
        height=600,
        width=1200,
        showlegend=False,
        updatemenus=[{
            'type': 'buttons',
            'showactive': False,
            'x': 0.1,
            'y': 1.02,
            'xanchor': 'right',
            'yanchor': 'top',
            'buttons': [
                {
                    'label': 'Play',
                    'method': 'animate',
                    'args': [None, {
                        'frame': {'duration': 1500, 'redraw': True},
                        'fromcurrent': True,
                        'transition': {'duration': 750}
                    }]
                },
                {
                    'label': 'Pause', 
                    'method': 'animate',
                    'args': [[None], {
                        'frame': {'duration': 0, 'redraw': False},
                        'mode': 'immediate',
                        'transition': {'duration': 0}
                    }]
                }
            ]
        }],
        sliders=[{
            'active': 0,
            'yanchor': 'top',
            'xanchor': 'left',
            'currentvalue': {
                'font': {'size': 16},
                'prefix': 'Year: ',
                'visible': True,
                'xanchor': 'right'
            },
            'transition': {'duration': 750, 'easing': 'cubic-in-out'},
            'pad': {'b': 10, 't': 50},
            'len': 0.9,
            'x': 0.1,
            'y': 0,
            'steps': [
                {
                    'args': [[year], {
                        'frame': {'duration': 750, 'redraw': True},
                        'mode': 'immediate',
                        'transition': {'duration': 750}
                    }],
                    'label': str(year),
                    'method': 'animate'
                } for year in common_years
            ]
        }]
    )
    
    fig.frames = frames
    return fig, common_years

# --------- Interactive Line Graph Function ---------
def create_interactive_line_graphs():
    merged_ward_savills_gdf_line = merged_ward_savills_gdf.drop(columns=['2021'], errors='ignore')
    merged_Core_Largesites_gdf_line = merged_Core_Largesites_gdf.drop(columns=['2021'], errors='ignore')
    
    ward_numeric = merged_ward_savills_gdf_line.select_dtypes(include=[np.number]).columns.tolist()
    sites_numeric = merged_Core_Largesites_gdf_line.select_dtypes(include=[np.number]).columns.tolist()
    
    ward_years = [col for col in ward_numeric if str(col).isdigit() and len(str(col)) == 4]
    sites_years = [col for col in sites_numeric if str(col).isdigit() and len(str(col)) == 4]
    common_years = sorted(set(ward_years) & set(sites_years))
    
    if not common_years:
        return None
    
    # Convert to integers for proper sorting
    common_years = sorted([int(year) for year in common_years])
    
    ward_names = merged_ward_savills_gdf['wd22nm'].dropna().unique()
    ward_names = sorted([name for name in ward_names if pd.notna(name)])
    if len(ward_names) == 0:
        return None
    
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Savills Trajectory', 'Core Largesites Baseline'), x_title='Year', y_title='Housing Units')
    
    all_traces = []
    for i, ward_name in enumerate(ward_names):
        ward_savills_data = merged_ward_savills_gdf[merged_ward_savills_gdf['wd22nm'] == ward_name]
        ward_sites_data = merged_Core_Largesites_gdf[merged_Core_Largesites_gdf['wd22nm'] == ward_name]
        
        savills_values = [ward_savills_data[str(year)].iloc[0] if str(year) in ward_savills_data.columns else 0 for year in common_years] if not ward_savills_data.empty else [0]*len(common_years)
        sites_values = [ward_sites_data[str(year)].iloc[0] if str(year) in ward_sites_data.columns else 0 for year in common_years] if not ward_sites_data.empty else [0]*len(common_years)
        
        trace_savills = go.Scatter(x=common_years, y=savills_values, mode='lines+markers', name=f'{ward_name} (Savills)', visible=(i==0), line=dict(color='#0074D9', width=2), marker=dict(size=6))
        trace_sites = go.Scatter(x=common_years, y=sites_values, mode='lines+markers', name=f'{ward_name} (Sites)', visible=(i==0), line=dict(color='#FF851B', width=2), marker=dict(size=6))
        
        fig.add_trace(trace_savills, row=1, col=1)
        fig.add_trace(trace_sites, row=1, col=2)
        all_traces.extend([trace_savills, trace_sites])
    
    dropdown_buttons = []
    for i, ward_name in enumerate(ward_names):
        visibility = [False]*len(all_traces)
        visibility[i*2] = True
        visibility[i*2+1] = True
        dropdown_buttons.append(dict(label=ward_name, method="update", args=[{"visible": visibility}]))
    
    fig.update_layout(
        title='Housing Trajectories by Ward',
        height=600,
        width=1200,
        showlegend=True,
        updatemenus=[dict(buttons=dropdown_buttons, direction="down", showactive=True, x=0.5, xanchor="center", y=1.15, yanchor="top")]
    )
    
    fig.update_xaxes(title_text="Year", row=1, col=1)
    fig.update_xaxes(title_text="Year", row=1, col=2)
    fig.update_yaxes(title_text="Housing Units", row=1, col=1)
    fig.update_yaxes(title_text="Housing Units", row=1, col=2)
    
    return fig

# ---------------- Initialize Figures ----------------
fig_dual_animated, common_years = create_dual_animated_map()
fig_line_graphs = create_interactive_line_graphs()

# ---------------- Dash App Layout ----------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE])

# Add GLA favicon and custom loading spinner
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        <link rel="icon" href="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png" type="image/png">
        {%favicon%}
        {%css%}
        <style>
            /* Loading spinner overlay */
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, #0074D9 0%, #FF851B 100%);
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                z-index: 9999;
                transition: opacity 0.5s ease-out;
            }
            
            /* Spinner animation */
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
            
            /* Loading text */
            .loading-text {
                color: white;
                font-family: Arial, sans-serif;
                font-size: 24px;
                font-weight: bold;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                margin-bottom: 10px;
            }
            
            .loading-subtext {
                color: rgba(255, 255, 255, 0.9);
                font-family: Arial, sans-serif;
                font-size: 16px;
                text-align: center;
                max-width: 300px;
            }
            
            /* GLA logo in loading screen */
            .loading-logo {
                width: 60px;
                height: 60px;
                margin-bottom: 30px;
                border-radius: 50%;
                background: white;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            }
            
            .loading-logo img {
                width: 40px;
                height: 40px;
                object-fit: contain;
            }
        </style>
    </head>
    <body>
        <!-- Loading overlay -->
        <div id="loading-overlay" class="loading-overlay">
            <div class="loading-logo">
                <img src="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png" alt="GLA Logo">
            </div>
            <div class="spinner"></div>
            <div class="loading-text">Loading Dashboard</div>
            <div class="loading-subtext">Preparing housing trajectory visualisations...</div>
        </div>
        
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        
        <script>
            // Hide loading overlay when page is fully loaded
            window.addEventListener('load', function() {
                setTimeout(function() {
                    const overlay = document.getElementById('loading-overlay');
                    if (overlay) {
                        overlay.style.opacity = '0';
                        setTimeout(function() {
                            overlay.style.display = 'none';
                        }, 500);
                    }
                }, 1000); // Show spinner for at least 1 second
            });
            
            // Also hide when Dash is ready
            document.addEventListener('DOMContentLoaded', function() {
                // Wait for Dash to render main content
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
                        }, 500);
                    }
                }, 100);
            });
        </script>
    </body>
</html>
'''

# Colours
primary_color = "#0074D9"  # Blue
secondary_color = "#FF851B"  # Orange
bg_color = "#F5F7FA"

# Ensure we have valid numeric years for the slider
if not common_years:
    common_years = [2022, 2023, 2024, 2025]  # Default years

min_year = min(common_years) if common_years else 2022
max_year = max(common_years) if common_years else 2050
default_year = min_year

app.layout = dbc.Container([
    
    html.Div([
        html.H1("Housing Units Dashboard", style={'textAlign': 'center', 'color': primary_color, 'fontWeight': 'bold', 'marginTop': 20, 'textShadow': '2px 2px 4px #888'}),
        html.Hr(style={'borderColor': secondary_color, 'height': '3px'})
    ]),
    
    # Metric Cards with dynamic year data and professional loading indicators
    dbc.Row([
        dbc.Col(
            dcc.Loading(
                id="loading-savills-card",
                type="dot",
                color=primary_color,
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Total Number of Houses Added", className="card-title", style={'color': primary_color}),
                            html.H5(id="year-display-savills", style={'color': '#666', 'fontSize': '14px'}),
                            html.H2(id="savills-total", className="card-text")
                        ])
                    ], style={'borderLeft': f'5px solid {secondary_color}', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'})
                ]
            )
        ),
        
        dbc.Col(
            dcc.Loading(
                id="loading-sites-card",
                type="dot",
                color=secondary_color,
                children=[
                    dbc.Card([
                        dbc.CardBody([
                            html.H4("Total Number of Houses Added", className="card-title", style={'color': secondary_color}),
                            html.H5(id="year-display-sites", style={'color': '#666', 'fontSize': '14px'}),
                            html.H2(id="sites-total", className="card-text")
                        ])
                    ], style={'borderLeft': f'5px solid {primary_color}', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'})
                ]
            )
        ),
    ], className="mb-4"),
    
    # Year Slider for controlling everything - moved above maps
    html.Div([
        html.H4("Select Year", style={'color': primary_color, 'marginBottom': 10}),
        dcc.Slider(
            id='year-slider',
            min=min_year,
            max=max_year,
            value=2027,
            marks={year: str(year) for year in common_years[::2]} if common_years else {},
            step=1,
            tooltip={"placement": "bottom", "always_visible": True},
            included=False
        )
    ], style={'marginBottom': 30, 'padding': '20px', 'backgroundColor': 'white', 'borderRadius': '10px', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'}),
    
    # Animated Map with Professional Loading Spinner
    html.H3("Animated Comparison Map", style={'color': primary_color, 'fontWeight': 'bold', 'textAlign': 'center', 'marginTop': 20}),
    dcc.Loading(
        id="loading-animated-map",
        type="cube",
        color=primary_color,
        style={'minHeight': '650px'},
        children=[
            dcc.Graph(
                id='animated-map', 
                figure=fig_dual_animated if fig_dual_animated else go.Figure(), 
                style={'height': '650px', 'border': f'3px solid {secondary_color}', 'borderRadius': '10px', 'boxShadow': '5px 5px 15px rgba(0,0,0,0.2)'}
            )
        ]
    ),
    
    # Line Graphs with Professional Loading Spinner
    html.H3("Interactive Line Graphs by Ward", style={'color': primary_color, 'fontWeight': 'bold', 'textAlign': 'center', 'marginTop': 30}),
    dcc.Loading(
        id="loading-line-graphs",
        type="circle",
        color=secondary_color,
        style={'minHeight': '650px'},
        children=[
            dcc.Graph(
                figure=fig_line_graphs if fig_line_graphs else go.Figure(), 
                style={'height': '650px', 'border': f'3px solid {secondary_color}', 'borderRadius': '10px', 'boxShadow': '5px 5px 15px rgba(0,0,0,0.2)'}
            )
        ]
    ),
    
    html.Div([
        html.P("This is an automated report produced by the Greater London Authority (GLA)", 
               style={'margin': '10px 0', 'fontSize': '14px', 'color': '#666'}),
        html.P([
            "If you require further information, please email ",
            html.A("Sebastian.Heslin-Rees@london.gov.uk", 
                   href="mailto:Sebastian.Heslin-Rees@london.gov.uk",
                   style={'color': primary_color, 'textDecoration': 'underline'})
        ], style={'margin': '10px 0', 'fontSize': '14px', 'color': '#666'})
    ], className="footer", style={'textAlign': 'center', 'marginTop': 50, 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderTop': f'2px solid {secondary_color}', 'borderRadius': '5px'})
    
], fluid=True, style={'backgroundColor': bg_color, 'padding': '20px'})

# Callback to update metric cards and year display based on selected year
@app.callback(
    [Output('savills-total', 'children'),
     Output('sites-total', 'children'),
     Output('year-display-savills', 'children'),
     Output('year-display-sites', 'children')],
    [Input('year-slider', 'value')]
)
def update_metrics(selected_year):
    year_str = str(selected_year)
    
    # Calculate totals for selected year
    savills_total = 0
    sites_total = 0
    
    if year_str in merged_ward_savills_gdf.columns:
        savills_total = merged_ward_savills_gdf[year_str].sum()
    
    if year_str in merged_Core_Largesites_gdf.columns:
        sites_total = merged_Core_Largesites_gdf[year_str].sum()
    
    year_display = f"Year {selected_year}"
    
    return f"{int(savills_total):,}", f"{int(sites_total):,}", year_display, year_display

# For gunicorn - FIXED: Only one if __name__ == "__main__": block
server = app.server

if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=8080, debug=False)
