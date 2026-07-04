import streamlit as st
import requests

class NeonAuthClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _get_headers(self, token=None):
        """Standard headers. If a token is provided, we send it as a Bearer token AND a cookie to cover all bases."""
        headers = {
            "Origin": "http://localhost:8501",
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
            # Better Auth often relies on this specific cookie name for sessions
            headers["Cookie"] = f"better-auth.session_token={token}" 
        return headers

    def sign_in(self, email: str, password: str):
        try:
            url = f"{self.base_url}/sign-in/email"
            payload = {"email": email, "password": password, "callbackURL": "http://localhost:8501"}
            r = requests.post(url, json=payload, headers=self._get_headers())
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            st.error(f"Sign In API Error: {e}")
            return None

    def sign_up(self, email: str, password: str, name: str = "Admin"):
        try:
            url = f"{self.base_url}/sign-up/email"
            payload = {"email": email, "password": password, "name": name, "callbackURL": "http://localhost:8501"}
            r = requests.post(url, json=payload, headers=self._get_headers())
            if r.status_code in [200, 201]:
                return r.json()
            return None
        except Exception as e:
            st.error(f"Sign Up API Error: {e}")
            return None

    def get_session(self, token: str) -> dict:
        """🔥 FIX: Verifies the opaque session token by asking the Auth API directly."""
        try:
            url = f"{self.base_url}/get-session"
            headers = self._get_headers(token)
            r = requests.get(url, headers=headers)
            
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            st.error(f"Get Session API Error: {e}")
            return None

def get_auth_client():
    base_url = st.secrets.get("NEON_AUTH_URL")
    if not base_url:
        st.error("❌ Missing NEON_AUTH_URL in Streamlit Secrets!")
        st.stop()
    return NeonAuthClient(base_url)
