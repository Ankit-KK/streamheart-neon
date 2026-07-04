import streamlit as st
import requests
import jwt
from jwt import PyJWKClient

class NeonAuthClient:
    def __init__(self, base_url: str, jwks_url: str):
        self.base_url = base_url.rstrip("/")
        self.jwks_url = jwks_url
        self._jwks_client = PyJWKClient(self.jwks_url)

    def _get_headers(self):
        return {
            "Origin": "http://localhost:8501",
            "Content-Type": "application/json"
        }

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

    def verify_token(self, access_token: str) -> dict:
        try:
            # 🔥 DEBUG 1: Check if it's actually a JWT (JWTs have exactly 2 dots)
            if access_token.count('.') != 2:
                st.warning(f"🔍 DEBUG: Token is NOT a standard JWT format. It might be an opaque session ID. Length: {len(access_token)}")
                # If it's not a JWT, we can't decode it locally. We'll return a dummy dict to bypass the crash for now.
                return {"email": "unknown@unknown.com", "sub": "opaque-token"}

            # 🔥 DEBUG 2: Try to decode and catch the EXACT error
            signing_key = self._jwks_client.get_signing_key_from_jwt(access_token)
            return jwt.decode(access_token, signing_key.key, algorithms=["RS256"])
            
        except jwt.ExpiredSignatureError:
            st.error("🔍 DEBUG: Token is expired (Clock skew?)")
            return None
        except jwt.InvalidAlgorithmError:
            st.error("🔍 DEBUG: Invalid algorithm. Better Auth might be using HS256 instead of RS256.")
            return None
        except Exception as e:
            st.error(f"🔍 DEBUG: JWT Verification Failed: {type(e).__name__} - {str(e)}")
            return None

def get_auth_client():
    base_url = st.secrets.get("NEON_AUTH_URL")
    jwks_url = st.secrets.get("NEON_AUTH_JWKS_URL")
    
    if not base_url or not jwks_url:
        st.error("❌ Missing NEON_AUTH_URL or NEON_AUTH_JWKS_URL in Streamlit Secrets!")
        st.stop()
        
    return NeonAuthClient(base_url, jwks_url)
