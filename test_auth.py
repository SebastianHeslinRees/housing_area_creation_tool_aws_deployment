import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# Simple test app
app = dash.Dash(__name__, suppress_callback_exceptions=True)

app.layout = html.Div([
    dcc.Store(id='session-store', storage_type='session'),
    html.Div(id='page-content')
])

@app.callback(
    Output('page-content', 'children'),
    [Input('session-store', 'data')]
)
def display_page(session_data):
    if session_data and session_data.get('authenticated'):
        return html.Div([
            html.H1("Dashboard"),
            html.Button("Logout", id="logout-button")
        ])
    else:
        return html.Div([
            html.H2("Login Test"),
            dcc.Input(id='email-input', type='email', placeholder='Enter email'),
            html.Button('Check Email', id='check-email-button'),
            html.Div(id='auth-output')
        ])

@app.callback(
    [Output('session-store', 'data'),
     Output('auth-output', 'children')],
    [Input('check-email-button', 'n_clicks')],
    [State('email-input', 'value')]
)
def check_email(n_clicks, email):
    print(f"Callback triggered: n_clicks={n_clicks}, email={email}")
    if n_clicks and email:
        if email == "Sebastian.Heslin-Rees@london.gov.uk":
            return {'authenticated': True}, "Login successful!"
        else:
            return {}, "Email not authorised"
    return {}, ""

if __name__ == '__main__':
    app.run_server(debug=True, port=8051)  # Use different port