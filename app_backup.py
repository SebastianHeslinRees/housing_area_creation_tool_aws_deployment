"""UK Fertility Rate Dashboard - Dash app entrypoint

This is the application entrypoint used for local development and production
(gunicorn will import `server` from this module).

Notes:
- Runs on port 8022 by default when executed directly.
- Use `gunicorn --bind 0.0.0.0:8022 --workers 1 app:server` for production.
"""
import os
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely import wkt
import dash
from dash import dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go

# ----------------- Configuration -----------------
PORT = int(os.environ.get('PORT', 8022))

# ----------------- Helpers -----------------
def _safe_load_wkt(val):
    if pd.isna(val):
        return None
    try:
        return wkt.loads(val)
    except Exception:
        return None

# ----------------- Load Data -----------------
print("Loading fertility and geometry data...")

# Read asfr_merged and tfr_merged geojson
asfr_merged = 'asfr_merged.geojson'
tfr_merged = 'tfr_merged.geojson'

# Read geojson files
asfr_clean = gpd.read_file(asfr_merged)
tfr_clean = gpd.read_file(tfr_merged)

# Ensure geometry is set correctly
if 'geometry' in asfr_clean.columns:
    asfr_clean = asfr_clean.set_geometry('geometry')
if 'geometry' in tfr_clean.columns:
    tfr_clean = tfr_clean.set_geometry('geometry')

# Extract selectors
years = sorted(tfr_clean['year'].unique().astype(str)) if 'year' in tfr_clean.columns else []
ages = sorted(asfr_clean['age'].unique().astype(int)) if 'age' in asfr_clean.columns else []
ages = [str(a) for a in ages]  # Convert back to strings for dropdown
lads = sorted(tfr_clean['LAD23NM'].unique()) if 'LAD23NM' in tfr_clean.columns else []

print(f"Loaded {len(tfr_clean)} TFR records and {len(asfr_clean)} ASFR records")
print(f"Years: {len(years)}, Ages: {len(ages)}, LADs: {len(lads)}")

# ----------------- Styling -----------------
colors = {
    'primary': '#1e3a8a',
    'secondary': '#ea580c',
    'accent': '#3b82f6',
    'warning': '#f59e0b',
    'card_bg': 'white',
    'text': '#374151'
}

# ----------------- Dash App -----------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE], suppress_callback_exceptions=True,
                title='UK Fertility Rate Dashboard - GLA')
server = app.server

# Minimal layout: controls + metric cards + two maps + trend
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H1("UK Fertility Rate Dashboard", style={'color': colors['primary']}))
    ]),
    dbc.Row([
        dbc.Col([
            html.Label("Select Year"),
            dcc.Dropdown(id='year-dropdown', options=[{'label': y, 'value': y} for y in years], value=years[-1] if years else None, clearable=False)
        ], width=3),
        dbc.Col([
            html.Label("Local Authority"),
            dcc.Dropdown(id='lad-dropdown', options=[{'label': l, 'value': l} for l in lads], value=lads[0] if lads else None, clearable=False)
        ], width=4),
        dbc.Col([
            html.Label("Select Age (ASFR)"),
            dcc.Dropdown(id='age-dropdown', options=[{'label': f"Age {a}", 'value': a} for a in ages], value=ages[0] if ages else None, clearable=False)
        ], width=3)
    ], className='mb-3'),

    # Metric cards
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(id='tfr-title', children='Total Fertility Rate'), html.H2(id='current-tfr', children='--')]))),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4(id='comparison-title', children='vs UK Average'), html.H2(id='tfr-comparison', children='--')]))),
        dbc.Col(dbc.Card(dbc.CardBody([html.H4('Replacement Level'), html.H2('2.1'), html.P(id='replacement-status', children='--')]))),
    ], className='mb-4'),

    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id='tfr-map'))), width=6),
        dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id='asfr-map'))), width=6)
    ]),

    dbc.Row(dbc.Col(dbc.Card(dbc.CardBody(dcc.Graph(id='asfr-trend')))), className='mt-3')
], fluid=True)

# ----------------- Callbacks -----------------
@app.callback(
    [Output('tfr-title', 'children'), Output('comparison-title', 'children'), Output('current-tfr', 'children'), Output('tfr-comparison', 'children'), Output('replacement-status', 'children')],
    [Input('year-dropdown', 'value'), Input('lad-dropdown', 'value')]
)
def update_metrics(selected_year, selected_lad):
    try:
        if selected_year is None or selected_lad is None:
            return 'Total Fertility Rate', 'vs UK Average', '--', '--', '--'
        # Ensure year is int where dataset uses int
        year_int = int(selected_year)
        lad_data = tfr_clean[(tfr_clean['LAD23NM'] == selected_lad) & (tfr_clean['year'] == year_int)] if 'LAD23NM' in tfr_clean.columns else pd.DataFrame()
        uk_avg = tfr_clean[tfr_clean['year'] == year_int]['tfr'].mean() if 'year' in tfr_clean.columns and 'tfr' in tfr_clean.columns else None
        if lad_data.empty or 'tfr' not in lad_data.columns:
            return f"Total Fertility Rate for {selected_lad} in {selected_year}", f"{selected_lad} vs UK Average", 'No data', 'No data', 'No data available'
        lad_tfr = lad_data['tfr'].iloc[0]
        difference = lad_tfr - uk_avg if uk_avg is not None else None
        diff_text = f"+{difference:.2f}" if difference is not None and difference >= 0 else (f"{difference:.2f}" if difference is not None else 'N/A')
        status = f"Above replacement (+{lad_tfr-2.1:.2f})" if lad_tfr >= 2.1 else f"Below replacement ({lad_tfr-2.1:.2f})"
        return f"Total Fertility Rate for {selected_lad} in {selected_year}", f"{selected_lad} vs UK Average", f"{lad_tfr:.2f}", diff_text, status
    except Exception as e:
        print('Metric update error:', e)
        return 'Total Fertility Rate', 'vs UK Average', 'Error', 'Error', 'Error'


@app.callback(Output('tfr-map', 'figure'), [Input('year-dropdown', 'value')])
def update_tfr_map(selected_year):
    try:
        if selected_year is None:
            return go.Figure()
        year_int = int(selected_year)
        year_data = tfr_clean[tfr_clean['year'] == year_int].copy() if 'year' in tfr_clean.columns else gpd.GeoDataFrame()
        if year_data.empty:
            fig = go.Figure()
            fig.add_annotation(text=f"No TFR data for {selected_year}", showarrow=False)
            return fig
        
        # Use the geojson directly from the geodataframe
        fig = px.choropleth_mapbox(
            year_data, 
            geojson=year_data.__geo_interface__, 
            locations=year_data.index, 
            color='tfr',
            hover_name='LAD23NM',
            hover_data={'tfr': ':.3f'},
            color_continuous_scale='RdYlBu_r',
            mapbox_style='carto-positron',
            center={'lat': 54.5, 'lon': -2.5},
            zoom=5
        )
        fig.update_layout(
            title=f"Total Fertility Rate ({selected_year})", 
            margin=dict(l=5, r=5, t=40, b=5),
            height=500
        )
        return fig
    except Exception as e:
        print('TFR map error:', e)
        import traceback
        traceback.print_exc()
        fig = go.Figure()
        fig.add_annotation(text=f'TFR map error: {str(e)}', showarrow=False)
        return fig


@app.callback(Output('asfr-map', 'figure'), [Input('year-dropdown', 'value'), Input('age-dropdown', 'value')])
def update_asfr_map(selected_year, selected_age):
    try:
        if selected_year is None or selected_age is None:
            return go.Figure()
        year_int = int(selected_year)
        age_int = int(selected_age)
        df = asfr_clean[(asfr_clean['year'] == year_int) & (asfr_clean['age'] == age_int)].copy() if 'year' in asfr_clean.columns else gpd.GeoDataFrame()
        if df.empty:
            fig = go.Figure()
            fig.add_annotation(text=f"No ASFR data for {selected_year}, Age {selected_age}", showarrow=False)
            return fig
        
        # Use the geojson directly from the geodataframe
        fig = px.choropleth_mapbox(
            df, 
            geojson=df.__geo_interface__, 
            locations=df.index, 
            color='fertility_rate',
            hover_name='LAD23NM',
            hover_data={'fertility_rate': ':.4f'},
            color_continuous_scale='Plasma',
            mapbox_style='carto-positron',
            center={'lat': 54.5, 'lon': -2.5},
            zoom=5
        )
        fig.update_layout(
            title=f"ASFR Age {selected_age} ({selected_year})", 
            margin=dict(l=5, r=5, t=40, b=5),
            height=500
        )
        return fig
    except Exception as e:
        print('ASFR map error:', e)
        import traceback
        traceback.print_exc()
        fig = go.Figure()
        fig.add_annotation(text=f'ASFR map error: {str(e)}', showarrow=False)
        return fig


@app.callback(Output('asfr-trend', 'figure'), [Input('lad-dropdown', 'value'), Input('age-dropdown', 'value')])
def update_asfr_trend(selected_lad, selected_age):
    try:
        if selected_lad is None or selected_age is None:
            return go.Figure()
        age_int = int(selected_age)
        df = asfr_clean[(asfr_clean['LAD23NM'] == selected_lad) & (asfr_clean['age'] == age_int)].copy() if 'LAD23NM' in asfr_clean.columns else pd.DataFrame()
        if df.empty:
            fig = go.Figure()
            fig.add_annotation(text=f"No ASFR data for {selected_lad}, Age {selected_age}", showarrow=False)
            return fig
        df['year_int'] = df['year'].astype(int)
        df = df.sort_values('year_int')
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df['year_int'], y=df['fertility_rate'], mode='lines+markers', name=selected_lad))
        fig.update_layout(title=f"ASFR Trend (Age {selected_age}): {selected_lad}", xaxis_title='Year', yaxis_title='ASFR', margin=dict(l=5, r=5, t=40, b=5))
        return fig
    except Exception as e:
        print('ASFR trend error:', e)
        fig = go.Figure()
        fig.add_annotation(text='ASFR trend error', showarrow=False)
        return fig


if __name__ == '__main__':
    print(f"Starting UK Fertility Dashboard on port {PORT}...")
    app.run_server(debug=True, port=PORT)
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
        title='<b>Housing Units Added</b>',
        title_x=0.5,
        mapbox1=dict(style='carto-positron', center={'lat': 51.5074, 'lon': -0.1278}, zoom=8),
        mapbox2=dict(style='carto-positron', center={'lat': 51.5074, 'lon': -0.1278}, zoom=8),
        height=580,  # Reduced to fit better in container
        width=1200,
        showlegend=False,
        margin=dict(l=5, r=5, t=40, b=5),  # Tighter margins to fit container
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
        title='<b>Housing Trajectories by Ward</b>',
        height=580,  # Reduced to fit better in container
        width=1200,
        showlegend=True,
        margin=dict(l=30, r=30, t=60, b=30)  # Tighter margins to fit container
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
        title=f'<b>Housing Trajectories - {selected_ward}</b>',
        title_x=0.5,
        height=580,  # Reduced to fit better in container
        width=1200,
        showlegend=True,
        margin=dict(l=30, r=30, t=60, b=30)  # Tighter margins to fit container
    )
    
    fig.update_xaxes(title_text="Year", row=1, col=1)
    fig.update_xaxes(title_text="Year", row=1, col=2)
    fig.update_yaxes(title_text="Housing Units", row=1, col=1)
    fig.update_yaxes(title_text="Housing Units", row=1, col=2)
    
    return fig

# ---------------- Initialise Figures ----------------
fig_dual_animated, common_years = create_dual_animated_map()
fig_line_graphs, ward_names = create_interactive_line_graphs()

# ---------------- Dash App Layout ----------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SANDSTONE], suppress_callback_exceptions=True)

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
                try {
                    // Check if main container is loaded
                    const dashContainer = document.querySelector('[data-dash-is-loading="false"]');
                    if (!dashContainer) return false;
                    
                    // More lenient check - look for any visible content
                    const hasVisibleContent = document.querySelector('#main-content') && 
                                            document.querySelector('#main-content').children.length > 0;
                    if (!hasVisibleContent) return false;
                    
                    // Check if graphs exist (don't require full layout in cloud env)
                    const graphs = document.querySelectorAll('.js-plotly-plot, [id*="map"], [id*="graph"]');
                    if (graphs.length < 2) return false; // Should have at least 2 maps
                    
                    // Check if dropdown exists and has some structure
                    const dropdown = document.querySelector('#ward-dropdown');
                    if (!dropdown) return false;
                    
                    // More flexible content check - any of these indicate readiness
                    const hasAnyPlots = document.querySelectorAll('.plotly, .js-plotly-plot').length > 0;
                    const hasMapContent = document.querySelector('[id*="map-container"]');
                    const hasDropdownStructure = document.querySelector('.Select-control, .dash-dropdown');
                    
                    return hasAnyPlots || hasMapContent || hasDropdownStructure;
                } catch (e) {
                    console.log('Error checking dash readiness:', e);
                    return false;
                }
            }
            
            // Main function to hide loading overlay when everything is ready
            function hideLoadingWhenReady() {
                let checkCount = 0;
                const maxChecks = 200; // 20 seconds max (100ms * 200)
                
                const checkInterval = setInterval(function() {
                    checkCount++;
                    hideDefaultDashLoading(); // Keep hiding default loaders
                    
                    // For cloud deployment, be more patient and use multiple strategies
                    const isReady = isDashFullyReady();
                    const hasMinimumTime = checkCount > 30; // At least 3 seconds
                    const hasContent = document.querySelectorAll('.js-plotly-plot, [id*="map"], .plotly').length > 0;
                    
                    // On cloud, wait longer and be more flexible about "ready" state
                    if ((isReady && hasMinimumTime) || (hasContent && checkCount > 80)) {
                        clearInterval(checkInterval);
                        // Longer buffer for cloud environment
                        setTimeout(function() {
                            const overlay = document.getElementById('loading-overlay');
                            if (overlay) {
                                overlay.style.opacity = '0';
                                setTimeout(function() {
                                    overlay.style.display = 'none';
                                }, 800); // Slower fade for cloud
                            }
                        }, 2000); // Longer wait for cloud stability
                    }
                    
                    // Safety fallback
                    if (checkCount >= maxChecks) {
                        clearInterval(checkInterval);
                        const overlay = document.getElementById('loading-overlay');
                        if (overlay && overlay.style.display !== 'none') {
                            overlay.style.opacity = '0';
                            setTimeout(function() {
                                overlay.style.display = 'none';
                            }, 800);
                        }
                    }
                }, 100);
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

# Authentication-enabled layout
app.layout = html.Div([
    dcc.Store(id='session-store', storage_type='session'),
    html.Div(id='page-content')
])

def get_main_dashboard():
    """Return the main dashboard layout"""
    return dbc.Container([
    
    html.Div([
        html.Div([
            html.Button("Logout", id="logout-button", 
                       style={'float': 'right', 'margin': '10px 0',
                             'backgroundColor': '#dc3545', 'color': 'white',
                             'border': 'none', 'padding': '8px 15px',
                             'borderRadius': '5px', 'cursor': 'pointer', 'fontSize': '14px'})
        ], style={'textAlign': 'right', 'marginBottom': '10px'}),
        html.H1("Housing Units Dashboard", style={'textAlign': 'center', 'color': primary_color, 'fontWeight': 'bold', 'marginTop': 0, 'textShadow': '2px 2px 4px #888'}),
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
                        html.P([
                            html.Strong("Savills Trajectory "), 
                        ], style={'marginBottom': '8px'}),
                        html.P([
                            html.Strong("Core Largesites Baseline "), 
                        ], style={'marginBottom': '8px'}),
                    ]),
                    html.Hr(style={'margin': '15px 0'}),
                    html.H6("Interactive Features:", style={'color': secondary_color, 'marginBottom': '10px'}),
                    html.P("• Use the year slider to see data for different years", style={'marginBottom': '5px'}),
                    html.P("• Click play on the map to see animated changes over time", style={'marginBottom': '5px'}),
                    html.P("• Search for specific boroughs in the line graph dropdown", style={'marginBottom': '5px'}),
                    html.P("• Compare trends between the two data sources", style={'marginBottom': '5px'}),
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
            min=2022,
            max=max_year,
            value=2027,
            marks={year: str(year) for year in common_years[::2] if year >= 2022} if common_years else {},
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
        config={'displayModeBar': True}
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
        config={'displayModeBar': True}
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

# Authentication callbacks
@app.callback(
    Output('page-content', 'children'),
    [Input('session-store', 'data')]
)
def display_page(session_data):
    """Display login page or main dashboard based on authentication"""
    if session_data and session_data.get('authenticated'):
        return get_main_dashboard()
    else:
        return create_login_layout()

@app.callback(
    [Output('session-store', 'data'),
     Output('auth-output', 'children')],
    [Input('login-button', 'n_clicks')],
    [State('email-input', 'value'),
     State('password-input', 'value')]
)
def handle_login(n_clicks, email, password):
    """Handle login authentication"""
    if n_clicks > 0:
        if email and password:
            if check_auth(email, password):
                # Successful login
                user_info = get_user_info(email)
                return {
                    'authenticated': True,
                    'email': email,
                    'name': user_info.get('name', email),
                    'role': user_info.get('role', 'user')
                }, ""
            else:
                # Failed login
                return dash.no_update, html.Div([
                    html.P("Invalid email or password", style={'color': 'red', 'fontWeight': 'bold'}),
                    html.P("Please check your credentials and try again.", style={'color': '#666', 'fontSize': '14px'})
                ])
        else:
            # Missing fields
            return dash.no_update, html.Div([
                html.P("Please enter both email and password", style={'color': 'red', 'fontWeight': 'bold'})
            ])
    return dash.no_update, ""





# @app.callback(
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

