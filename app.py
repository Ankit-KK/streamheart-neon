import streamlit as st
from utils.auth import get_auth_client

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")

auth_client = get_auth_client()

# ==============================================================================
# 1. AUTHENTICATION LAYER (REST API)
# ==============================================================================
if "auth_token" not in st.session_state:
    st.title("🔐 StreamHeart CMS Login")
    
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        
        if submitted:
            resp = auth_client.sign_in(email, password)
            if resp and "data" in resp and "session" in resp["data"]:
                # Store the token and user data in session state
                st.session_state["auth_token"] = resp["data"]["session"]["token"]
                st.session_state["user"] = resp["data"]["user"]
                st.success("✅ Logged in successfully!")
                st.rerun()
            else:
                st.error("❌ Invalid email or password.")
                
    st.stop() # Stops the rest of the app from loading if not authenticated

# ==============================================================================
# 2. VERIFY JWT & DASHBOARD (Local Verification)
# ==============================================================================
# Verify the token locally on every load using JWKS
claims = auth_client.verify_token(st.session_state["auth_token"])

if not claims:
    st.error("❌ Session expired or invalid. Please log in again.")
    if st.button("Clear Session"):
        st.session_state.clear()
        st.rerun()
    st.stop()

# Token is valid! Extract user info directly from the JWT payload.
user_email = claims.get("email", "Unknown User")
user_id = claims.get("sub") # This is the UUID from Neon Auth

col_title, col_logout = st.columns([4, 1])
with col_title:
    st.title("💖 StreamHeart Admin Dashboard")
    st.caption(f"Welcome back, **{user_email}**")
with col_logout:
    st.write("") 
    if st.button("🚪 Logout", type="secondary", use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.divider()
st.info("👈 Use the **sidebar on the left** to navigate to specific modules.")
