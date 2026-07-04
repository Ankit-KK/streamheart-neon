import streamlit as st
import requests
import jwt
from jwt import PyJWKClient

class NeonAuthClient:
    def __init__(self, base_url: str, jwks_url: str):
        self.base_url = base_url.rstrip("/")
        self.jwks_url = jwks_url
        # Cache the JWKS client to avoid fetching keys on every Streamlit rerun
        self._jwks_client = PyJWKClient(self.jwks_url)

    def sign_in(self, email: str, password: str):
        """Hits the Neon Auth REST API to sign in."""
        try:
            # Hitting the Better Auth REST endpoint
            r = requests.post(
                f"{self.base_url}/api/auth/sign-in/email", 
                json={"email": email, "password": password}
            )
            
            if r.status_code == 200:
                return r.json()
            else:
                return None # Invalid credentials or API error
        except Exception as e:
            st.error(f"Auth API Error: {e}")
            return None

    def verify_token(self, access_token: str) -> dict:
        """Verifies the JWT locally using JWKS (No database query needed!)."""
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(access_token)
            return jwt.decode(
                access_token, 
                signing_key.key, 
                algorithms=["RS256"]
            )
        except Exception as e:
            return None

def get_auth_client():
    """Initializes the Neon Auth client using Streamlit secrets."""
    base_url = st.secrets.get("NEON_AUTH_URL")
    jwks_url = st.secrets.get("NEON_AUTH_JWKS_URL")
    
    if not base_url or not jwks_url:
        st.error("❌ Missing NEON_AUTH_URL or NEON_AUTH_JWKS_URL in Streamlit Secrets!")
        st.stop()
        
    return NeonAuthClient(base_url, jwks_url)
