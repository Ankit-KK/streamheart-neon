import streamlit as st
import requests
import jwt
from jwt import PyJWKClient

class NeonAuthClient:
    def __init__(self, base_url: str, jwks_url: str):
        self.base_url = base_url.rstrip("/")
        self.jwks_url = jwks_url
        self._jwks_client = PyJWKClient(self.jwks_url)

    def sign_in(self, email: str, password: str):
        try:
            url = f"{self.base_url}/api/auth/sign-in/email"
            r = requests.post(url, json={"email": email, "password": password})
            if r.status_code == 200:
                return r.json()
            else:
                st.error(f"Sign In Failed: {r.status_code} - URL: {url} - Response: {r.text}")
            return None
        except Exception as e:
            st.error(f"Sign In API Error: {e}")
            return None

    def sign_up(self, email: str, password: str, name: str = "Admin"):
        try:
            url = f"{self.base_url}/api/auth/sign-up/email"
            r = requests.post(url, json={"email": email, "password": password, "name": name})
            if r.status_code in [200, 201]:
                return r.json()
            else:
                # 🔥 DEBUG: This will show us the exact URL that returned 404
                st.error(f"Sign Up Failed: {r.status_code} - URL: {url} - Response: {r.text}")
                return None
        except Exception as e:
            st.error(f"Sign Up API Error: {e}")
            return None

    def verify_token(self, access_token: str) -> dict:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(access_token)
            return jwt.decode(access_token, signing_key.key, algorithms=["RS256"])
        except Exception as e:
            return None

def get_auth_client():
    base_url = st.secrets.get("NEON_AUTH_URL")
    jwks_url = st.secrets.get("NEON_AUTH_JWKS_URL")
    
    if not base_url or not jwks_url:
        st.error("❌ Missing NEON_AUTH_URL or NEON_AUTH_JWKS_URL in Streamlit Secrets!")
        st.stop()
        
    return NeonAuthClient(base_url, jwks_url)
