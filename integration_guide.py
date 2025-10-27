"""
Integration guide for adding authentication to your existing app.py

STEP 1: Add these imports to the top of your app.py file:
"""

# Add to your existing imports in app.py:
from auth import create_login_layout, check_auth, get_user_info

"""
STEP 2: Modify your app initialization section in app.py

Find where you initialize your Dash app and modify the layout:
"""

# Replace your existing app.layout = ... with:
app.layout = html.Div([
    dcc.Store(id='session-store', storage_type='session'),
    html.Div(id='page-content')
])

"""
STEP 3: Add these callback functions to your app.py file

Add these BEFORE your existing callbacks:
"""

@app.callback(
    Output('page-content', 'children'),
    [Input('session-store', 'data')]
)
def display_page(session_data):
    """Display login page or main dashboard based on authentication"""
    if session_data and session_data.get('authenticated'):
        # Return your existing dashboard layout
        return get_main_dashboard_layout(session_data.get('email', 'Unknown User'))
    else:
        # Return login page
        return create_login_layout()

@app.callback(
    [Output('session-store', 'data'),
     Output('login-output', 'children')],
    [Input('login-button', 'n_clicks')],
    [State('email-input', 'value'),
     State('password-input', 'value')]
)
def login_user(n_clicks, email, password):
    """Handle login authentication"""
    if n_clicks > 0 and email and password:
        if check_auth(email, password):
            user_info = get_user_info(email)
            # Successful login
            return {
                'authenticated': True, 
                'email': email,
                'name': user_info.get('name', email),
                'role': user_info.get('role', 'user')
            }, ""
        else:
            # Failed login
            return {}, html.Div("Invalid credentials. Please contact Sebastian.Heslin-Rees@london.gov.uk for access.", 
                              style={'color': 'red', 'fontWeight': 'bold'})
    return {}, ""

"""
STEP 4: Wrap your existing layout in a function

Take all your current dashboard HTML layout and put it inside this function:
"""

def get_main_dashboard_layout(user_email=""):
    """Return your existing dashboard layout with logout button"""
    
    # Get user info for display
    user_info = get_user_info(user_email)
    user_name = user_info.get('name', user_email)
    
    return html.Div([
        # Add header with user info and logout
        html.Div([
            html.Div([
                html.Span(f"Welcome, {user_name}", 
                         style={'color': primary_color, 'fontSize': '16px', 'fontWeight': 'bold'}),
                html.Button("Logout", id="logout-button", 
                           style={'float': 'right', 'margin': '0 20px',
                                 'backgroundColor': '#dc3545', 'color': 'white',
                                 'border': 'none', 'padding': '8px 15px',
                                 'borderRadius': '5px', 'cursor': 'pointer'})
            ], style={'padding': '10px 20px', 'backgroundColor': light_blue, 
                     'borderBottom': f'2px solid {secondary_color}', 'marginBottom': '20px'})
        ]),
        
        # PUT ALL YOUR EXISTING DASHBOARD CONTENT HERE
        # Just copy everything from your current app.layout and paste it below:
        
        # Your existing loading overlay, title, controls, graphs, etc.
        # Example:
        html.Div(id="loading-overlay", style={...}),  # Your existing content
        html.H1("Housing Units Dashboard", style={...}),  # Your existing content
        # ... rest of your dashboard layout
        
    ])

# Add logout callback
@app.callback(
    Output('session-store', 'data', allow_duplicate=True),
    [Input('logout-button', 'n_clicks')],
    prevent_initial_call=True
)
def logout_user(n_clicks):
    """Handle logout"""
    if n_clicks:
        return {}
    return dash.no_update

"""
STEP 5: Add new authorized users

To add new users, edit the AUTHORIZED_USERS dictionary in auth.py:

1. Add their email address
2. Generate a password hash by uncommenting the lines at the bottom of auth.py
3. Run: python auth.py to see the hash
4. Add the hash to the user entry

Example:
    "new.user@london.gov.uk": {
        "password": "generated_hash_here",
        "role": "user",
        "name": "New User Name"
    }
"""