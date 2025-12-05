"""
Simple Authentication module for the GLA Housing Dashboard
"""
import dash
from dash import html, dcc
import os

# authorised email addresses with fixed password (stored in lowercase for case-insensitive matching)
authoriseD_EMAILS = {
    'sebastian.heslin-rees@london.gov.uk': {
        'name': 'Sebastian Heslin-Rees',
        'role': 'admin'
    },
    'ben.corr@london.gov.uk': {
        'name': 'Ben Corr',
        'role': 'user'
    }

}

# Fixed password for all authorised users - get from environment variable
FIXED_PASSWORD = os.getenv('DASHBOARD_PASSWORD', 'dashboardgla')  # Default for local development

def is_authorised_email(email):
    """Check if email is in authorised list (case-insensitive)"""
    if not email:
        return False
    return email.lower() in authoriseD_EMAILS

def get_user_info(email):
    """Get user information from authorised emails (case-insensitive)"""
    if not email:
        return {}
    return authoriseD_EMAILS.get(email.lower(), {})

def verify_password(password):
    """Verify password against fixed password"""
    return password == FIXED_PASSWORD

def check_auth(email, password):
    """Check if email and password are valid"""
    return is_authorised_email(email) and verify_password(password)

def create_login_layout():
    """Create the login page layout"""
    return html.Div([
        html.Div([
            html.Img(
                src="https://resource.esriuk.com/wp-content/uploads/2017/06/GLA-Logo-Resized.png",
                style={'height': '80px', 'marginBottom': '20px'}
            ),
            html.H2("GLA Housing Dashboard",
                   style={'textAlign': 'center', 'color': '#1E3A5F', 'marginBottom': '10px'}),
            html.P("authorised Access Required",
                   style={'textAlign': 'center', 'color': '#666', 'marginBottom': '30px'}),
            
            html.Div([
                dcc.Input(
                    id='email-input',
                    type='email',
                    placeholder='Email Address (e.g., your.name@london.gov.uk)',
                    style={'width': '100%', 'padding': '12px', 'marginBottom': '15px', 
                          'border': '2px solid #ddd', 'borderRadius': '5px', 'fontSize': '16px'}
                ),
                dcc.Input(
                    id='password-input',
                    type='password',
                    placeholder='Password',
                    style={'width': '100%', 'padding': '12px', 'marginBottom': '15px', 
                          'border': '2px solid #ddd', 'borderRadius': '5px', 'fontSize': '16px'}
                ),
                html.Button(
                    'Sign In',
                    id='login-button',
                    n_clicks=0,
                    style={'width': '100%', 'padding': '12px', 'backgroundColor': '#E67E22', 
                          'color': 'white', 'border': 'none', 'borderRadius': '5px', 
                          'fontSize': '18px', 'cursor': 'pointer', 'marginBottom': '20px'}
                ),
                html.Div(id='auth-output', style={'marginTop': '15px', 'textAlign': 'center'})
            ], id='auth-form')
        ], style={
            'maxWidth': '450px', 'margin': '100px auto', 'padding': '40px',
            'backgroundColor': 'white', 'borderRadius': '10px',
            'boxShadow': '0 4px 20px rgba(0,0,0,0.1)', 'border': '1px solid #ddd'
        })
    ], style={
        'backgroundColor': '#f8f9fa', 'minHeight': '100vh',
        'fontFamily': 'Arial, sans-serif'
    })

print("DEBUG: Authentication functions imported successfully")
