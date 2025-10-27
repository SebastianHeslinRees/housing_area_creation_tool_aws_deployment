"""
Microsoft OAuth Configuration for GLA Housing Dashboard
"""
import os
import msal

# OAuth Configuration
CLIENT_ID = os.getenv('MICROSOFT_CLIENT_ID', 'your-client-id-here')
CLIENT_SECRET = os.getenv('MICROSOFT_CLIENT_SECRET', 'your-client-secret-here')
TENANT_ID = os.getenv('MICROSOFT_TENANT_ID', 'common')  # 'common' allows any Microsoft account
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# App Runner URL
BASE_URL = "https://fyt9mwp3yz.eu-west-2.awsapprunner.com"
REDIRECT_URI = f"{BASE_URL}/oauth/callback"

# OAuth Scopes - what we want to access
SCOPES = [
    "User.Read",  # Basic profile info
    "email",      # Email address
    "openid",     # OpenID Connect
    "profile"     # Basic profile
]

# Restrict to GLA domain
ALLOWED_DOMAINS = ["london.gov.uk"]

def create_msal_app():
    """Create MSAL application instance"""
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

def get_auth_url():
    """Get the authorisation URL to redirect users to Microsoft login"""
    app = create_msal_app()
    auth_url = app.get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
        state="random_state_string"  # You should generate a random state
    )
    return auth_url

def exchange_code_for_token(code, state):
    """Exchange authorization code for access token"""
    app = create_msal_app()
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    return result

def is_gla_email(email):
    """Check if email is from GLA domain"""
    if not email:
        return False
    domain = email.split('@')[-1].lower()
    return domain in ALLOWED_DOMAINS