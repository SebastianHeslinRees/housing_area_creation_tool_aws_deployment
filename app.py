
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import geopandas as gpd
from shapely import wkt

# Colours Palette 
primary_color = "#1E3A5F"      # Deep Professional Blue
secondary_color = "#E67E22"    # Sophisticated Orange  
accent_color = "#2980B9"       # Bright Professional Blue
light_blue = "#EBF3FD"         # Very Light Blue
orange_light = "#FDF2E9"       # Very Light Orange
bg_color = "#F8FAFE"           # Ultra Light Blue Background
text_dark = "#2C3E50"          # Professional Dark Text
text_light = "#7F8C8D"         # Professional Light Text

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
        
        # Savills data with bright blue to orange colour scale and separate legend
        frame_data.append(
            go.Choroplethmapbox(
                geojson=ward_clean.__geo_interface__,
                locations=ward_clean.index,
                z=ward_clean[str(year)],
                colorscale=[[0, accent_color], [1, secondary_color]],  # Bright blue to orange
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
        
        # Core Sites data with bright blue to orange colour scale and separate legend
        frame_data.append(
            go.Choroplethmapbox(
                geojson=sites_clean.__geo_interface__,
                locations=sites_clean.index,
                z=sites_clean[str(year)],
                colorscale=[[0, accent_color], [1, secondary_color]],  # Bright blue to orange
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
    
    # Initial traces - start at 2027 if available, otherwise first year
    if frames:
        # Find the index for year 2027
        start_index = 0
        for i, year in enumerate(common_years):
            if year == 2027:
                start_index = i
                break
        
        # Make sure we don't go out of bounds
        if start_index < len(frames):
            fig.add_trace(frames[start_index].data[0], row=1, col=1)
            fig.add_trace(frames[start_index].data[1], row=1, col=2)
        else:
            fig.add_trace(frames[0].data[0], row=1, col=1)
            fig.add_trace(frames[0].data[1], row=1, col=2)
    
    fig.update_layout(
        title='Housing Units Added',
        mapbox1=dict(style='carto-positron', center={'lat': 51.5074, 'lon': -0.1278}, zoom=8),
        mapbox2=dict(style='carto-positron', center={'lat': 51.5074, 'lon': -0.1278}, zoom=8),
        height=600,
        width=1200,
        showlegend=False,
        margin=dict(l=10, r=10, t=50, b=10),
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
            'active': common_years.index(2027) if 2027 in common_years else 0,
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
        
        trace_savills = go.Scatter(x=common_years, y=savills_values, mode='lines+markers', name=f'{ward_name} (Savills)', visible=(i==0), line=dict(color=accent_color, width=2), marker=dict(size=6))
        trace_sites = go.Scatter(x=common_years, y=sites_values, mode='lines+markers', name=f'{ward_name} (Sites)', visible=(i==0), line=dict(color=secondary_color, width=2), marker=dict(size=6))
        
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
        margin=dict(l=40, r=40, t=80, b=40)
    )
    
    fig.update_xaxes(title_text="Year", row=1, col=1)
    fig.update_xaxes(title_text="Year", row=1, col=2)
    fig.update_yaxes(title_text="Housing Units", row=1, col=1)
    fig.update_yaxes(title_text="Housing Units", row=1, col=2)
    
    return fig, ward_names

# --------- Function to create line graph for specific ward ---------
def create_line_graph_for_ward(selected_ward):
    merged_ward_savills_gdf_line = merged_ward_savills_gdf.drop(columns=['2021'], errors='ignore')
    merged_Core_Largesites_gdf_line = merged_Core_Largesites_gdf.drop(columns=['2021'], errors='ignore')
    
    ward_numeric = merged_ward_savills_gdf_line.select_dtypes(include=[np.number]).columns.tolist()
    sites_numeric = merged_Core_Largesites_gdf_line.select_dtypes(include=[np.number]).columns.tolist()
    
    ward_years = [col for col in ward_numeric if str(col).isdigit() and len(str(col)) == 4]
    sites_years = [col for col in sites_numeric if str(col).isdigit() and len(str(col)) == 4]
    common_years = sorted(set(ward_years) & set(sites_years))
    
    if not common_years:
        return go.Figure()
    
    # Convert to integers for proper sorting
    common_years = sorted([int(year) for year in common_years])
    
    fig = make_subplots(rows=1, cols=2, subplot_titles=('Savills Trajectory', 'Core Largesites Baseline'))
    
    # Get data for selected ward
    ward_savills_data = merged_ward_savills_gdf[merged_ward_savills_gdf['wd22nm'] == selected_ward]
    ward_sites_data = merged_Core_Largesites_gdf[merged_Core_Largesites_gdf['wd22nm'] == selected_ward]
    
    if not ward_savills_data.empty and not ward_sites_data.empty:
        savills_values = [ward_savills_data[str(year)].iloc[0] if str(year) in ward_savills_data.columns else 0 for year in common_years]
        sites_values = [ward_sites_data[str(year)].iloc[0] if str(year) in ward_sites_data.columns else 0 for year in common_years]
        
        # Add traces for the selected ward
        trace_savills = go.Scatter(x=common_years, y=savills_values, mode='lines+markers', name=f'{selected_ward} (Savills)', line=dict(color=accent_color, width=3), marker=dict(size=8))
        trace_sites = go.Scatter(x=common_years, y=sites_values, mode='lines+markers', name=f'{selected_ward} (Sites)', line=dict(color=secondary_color, width=3), marker=dict(size=8))
        
        fig.add_trace(trace_savills, row=1, col=1)
        fig.add_trace(trace_sites, row=1, col=2)
    
    fig.update_layout(
        title=f'Housing Trajectories - {selected_ward}',
        height=600,
        width=1200,
        showlegend=True,
        margin=dict(l=40, r=40, t=80, b=40)
    )
    
    fig.update_xaxes(title_text="Year", row=1, col=1)
    fig.update_xaxes(title_text="Year", row=1, col=2)
    fig.update_yaxes(title_text="Housing Units", row=1, col=1)
    fig.update_yaxes(title_text="Housing Units", row=1, col=2)
    
    return fig

# ---------------- Initialize Figures ----------------
fig_dual_animated, common_years = create_dual_animated_map()
fig_line_graphs, ward_names = create_interactive_line_graphs()

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
        {%css%}
        <style>
            /* Hide ALL default Dash loading indicators */
            ._dash-loading, .dash-spinner, .dash-loading, .loading {
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
            }
            
            /* Hide any loading with data attributes */
            [data-dash-is-loading="true"] {
                display: none !important;
                visibility: hidden !important;
            }
            
            /* Loading spinner overlay */
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, #1E3A5F 0%, #E67E22 100%);
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
            // Hide all default Dash loading indicators immediately
            function hideDefaultDashLoading() {
                // Hide all Dash loading spinners
                const loadingSpinners = document.querySelectorAll('._dash-loading, .dash-spinner, [data-dash-is-loading="true"]');
                loadingSpinners.forEach(spinner => {
                    spinner.style.display = 'none !important';
                    spinner.style.visibility = 'hidden !important';
                });
                
                // Hide any loading overlays that might appear
                const loadingOverlays = document.querySelectorAll('.loading, .spinner, .dash-loading');
                loadingOverlays.forEach(overlay => {
                    if (overlay.id !== 'loading-overlay') { // Don't hide our custom overlay
                        overlay.style.display = 'none !important';
                    }
                });
            }
            
            // Run immediately and repeatedly to catch any loading indicators
            hideDefaultDashLoading();
            setInterval(hideDefaultDashLoading, 100);
            
            // Function to check if all Dash components are ready
            function isDashFullyReady() {
                // Check if main container is loaded
                const dashContainer = document.querySelector('[data-dash-is-loading="false"]');
                if (!dashContainer) return false;
                
                // Check if graphs are loaded (they should have plot containers)
                const graphs = document.querySelectorAll('.js-plotly-plot');
                if (graphs.length === 0) return false;
                
                // Check if all graphs have actual content
                let allGraphsReady = true;
                graphs.forEach(graph => {
                    const plotDiv = graph.querySelector('.plotly');
                    if (!plotDiv || !graph._fullLayout) {
                        allGraphsReady = false;
                    }
                });
                
                // Check if dropdown has options
                const dropdown = document.querySelector('#ward-dropdown .Select-control');
                const hasDropdownOptions = dropdown && dropdown.textContent.trim() !== '';
                
                return allGraphsReady && hasDropdownOptions;
            }
            
            // Main function to hide loading overlay when everything is ready
            function hideLoadingWhenReady() {
                const checkInterval = setInterval(function() {
                    hideDefaultDashLoading(); // Keep hiding default loaders
                    
                    if (isDashFullyReady()) {
                        clearInterval(checkInterval);
                        // Wait a bit longer to ensure everything is stable
                        setTimeout(function() {
                            const overlay = document.getElementById('loading-overlay');
                            if (overlay) {
                                overlay.style.opacity = '0';
                                setTimeout(function() {
                                    overlay.style.display = 'none';
                                }, 500);
                            }
                        }, 1000); // Extra buffer to ensure stability
                    }
                }, 100);
                
                // Safety fallback - hide after maximum time
                setTimeout(function() {
                    clearInterval(checkInterval);
                    const overlay = document.getElementById('loading-overlay');
                    if (overlay && overlay.style.display !== 'none') {
                        overlay.style.opacity = '0';
                        setTimeout(function() {
                            overlay.style.display = 'none';
                        }, 500);
                    }
                }, 10000); // Max 10 seconds fallback
            }
            
            // Start checking when DOM is ready
            document.addEventListener('DOMContentLoaded', function() {
                hideDefaultDashLoading();
                hideLoadingWhenReady();
            });
            
            // Also start checking on window load as backup
            window.addEventListener('load', function() {
                hideLoadingWhenReady();
            });
        </script>
    </body>
</html>
'''

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
    
    # Info Box with expandable information
    html.Div([
        dbc.Button(
            [
                html.I(className="fas fa-info-circle", style={'marginRight': '8px', 'fontSize': '16px'}),
                "Dashboard Information"
            ],
            id="info-toggle",
            color="info",
            outline=True,
            size="sm",
            style={'marginBottom': '10px', 'borderRadius': '20px'}
        ),
        dbc.Collapse(
            dbc.Card([
                dbc.CardBody([
                    html.H5(" About This Dashboard", style={'color': primary_color, 'marginBottom': '15px'}),
                    html.P([
                        "This interactive dashboard compares housing trajectory data from:"
                    ], style={'marginBottom': '10px'}),
                    html.Ul([
                        html.Li([
                            html.Strong("Savills Trajectory "), 
                        ], style={'marginBottom': '8px'}),
                        html.Li([
                            html.Strong("Core Largesites Baseline "), 
                        ], style={'marginBottom': '8px'}),
                    ]),
                    html.Hr(style={'margin': '15px 0'}),
                    html.H6("Interactive Features:", style={'color': secondary_color, 'marginBottom': '10px'}),
                    html.Ul([
                        html.Li("• Use the year slider to see data for different years", style={'marginBottom': '5px'}),
                        html.Li("• Click play on the map to see animated changes over time", style={'marginBottom': '5px'}),
                        html.Li("• Search for specific boroughs in the line graph dropdown", style={'marginBottom': '5px'}),
                        html.Li("• Compare trends between the two data sources", style={'marginBottom': '5px'}),
                    ]),
                    html.Hr(style={'margin': '15px 0'}),
                    html.P([
                        html.I(className="fas fa-building", style={'marginRight': '5px', 'color': primary_color}),
                        html.Small("Data visualisation by the Greater London Authority Housing Team", 
                                 style={'color': text_light, 'fontStyle': 'italic'})
                    ], style={'marginBottom': '0', 'textAlign': 'center'})
                ])
            ], style={'border': f'1px solid {primary_color}', 'borderRadius': '10px'}),
            id="info-collapse",
            is_open=False
        )
    ], style={'marginBottom': '20px', 'textAlign': 'center'}),
    
    # Metric Cards with dynamic year data
    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardBody([
                    html.H4("Number of Houses Added", className="card-title", style={'color': primary_color}),
                    html.H5(id="year-display-savills", style={'color': '#666', 'fontSize': '14px'}),
                    html.H2(id="savills-total", className="card-text")
                ])
            ], style={'borderLeft': f'5px solid {secondary_color}', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'})
        ),
        
        dbc.Col(
            dbc.Card([
                dbc.CardBody([
                    html.H4("Number of Houses Added", className="card-title", style={'color': secondary_color}),
                    html.H5(id="year-display-sites", style={'color': '#666', 'fontSize': '14px'}),
                    html.H2(id="sites-total", className="card-text")
                ])
            ], style={'borderLeft': f'5px solid {primary_color}', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'})
        ),
    ], className="mb-4"),
    
    # Year Slider for controlling everything - moved above maps
    html.Div([
        html.H4("Select Year", style={'color': primary_color, 'marginBottom': 10}),
        dcc.Slider(
            id='year-slider',
            min=2021,
            max=max_year,
            value=2027,
            marks={year: str(year) for year in common_years[::2]} if common_years else {},
            step=1,
            tooltip={"placement": "bottom", "always_visible": True},
            included=False
        )
    ], style={'marginBottom': 30, 'padding': '20px', 'backgroundColor': 'white', 'borderRadius': '10px', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'}),
    
    # Animated Comparison Map
    html.H3("Comparison Maps", style={'color': primary_color, 'fontWeight': 'bold', 'textAlign': 'center', 'marginTop': 20}),
    dcc.Graph(
        id='animated-map', 
        figure=fig_dual_animated if fig_dual_animated else go.Figure(), 
        style={'height': '650px', 'border': f'3px solid {secondary_color}', 'borderRadius': '10px', 'boxShadow': '5px 5px 15px rgba(0,0,0,0.2)', 'overflow': 'hidden'},
        config={'displayModeBar': False}
    ),
    
    # Interactive Line Graphs by Ward
    html.H3("Interactive Line Graphs by Ward", style={'color': primary_color, 'fontWeight': 'bold', 'textAlign': 'center', 'marginTop': 30}),
    
    # Searchable Borough Dropdown
    html.Div([
        html.H4("Select Borough/Ward", style={'color': primary_color, 'marginBottom': 10}),
        dcc.Dropdown(
            id='ward-dropdown',
            options=[{'label': ward, 'value': ward} for ward in sorted(ward_names)] if ward_names else [],
            value=sorted(ward_names)[0] if ward_names else None,
            placeholder="Search and select a borough/ward...",
            searchable=True,
            clearable=False,
            style={'fontSize': '16px'}
        )
    ], style={'marginBottom': 20, 'padding': '20px', 'backgroundColor': 'white', 'borderRadius': '10px', 'boxShadow': '3px 3px 15px rgba(0,0,0,0.1)'}),
    
    dcc.Graph(
        id='line-graphs',
        figure=fig_line_graphs if fig_line_graphs else go.Figure(), 
        style={'height': '650px', 'border': f'3px solid {secondary_color}', 'borderRadius': '10px', 'boxShadow': '5px 5px 15px rgba(0,0,0,0.2)', 'overflow': 'hidden'},
        config={'displayModeBar': False}
    ),
    
    html.Div([
        html.P("This is an automated report produced by the Greater London Authority (GLA)", 
               style={'margin': '10px 0', 'fontSize': '14px', 'color': text_light}),
        html.P([
            "If you require further information, please email ",
            html.A("Sebastian.Heslin-Rees@london.gov.uk", 
                   href="mailto:Sebastian.Heslin-Rees@london.gov.uk",
                   style={'color': primary_color, 'textDecoration': 'underline'})
        ], style={'margin': '10px 0', 'fontSize': '14px', 'color': text_light})
    ], className="footer", style={'textAlign': 'center', 'marginTop': 50, 'padding': '20px', 'backgroundColor': light_blue, 'borderTop': f'2px solid {secondary_color}', 'borderRadius': '5px'})
    
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

# Callback to update line graph based on selected ward
@app.callback(
    Output('line-graphs', 'figure'),
    [Input('ward-dropdown', 'value')]
)
def update_line_graph(selected_ward):
    if selected_ward:
        return create_line_graph_for_ward(selected_ward)
    else:
        return go.Figure()

# Callback to toggle info box
@app.callback(
    Output("info-collapse", "is_open"),
    [Input("info-toggle", "n_clicks")],
    [State("info-collapse", "is_open")],
)
def toggle_info_box(n_clicks, is_open):
    if n_clicks:
        return not is_open
    return is_open

# For gunicorn - FIXED: Only one if __name__ == "__main__": block
server = app.server

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=True)

