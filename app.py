import streamlit as st
from utils.auth import get_auth_client

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")

auth_client = get_auth_client()

# ==============================================================================
# 1. AUTHENTICATION LAYER (REST API)
# ==============================================================================
if "auth_token" not in st.session_state:
    st.title("🔐 StreamHeart CMS")
    
    tab_login, tab_signup = st.tabs(["Login", "Create Account"])
    
    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
            
            if submitted:
                resp = auth_client.sign_in(email, password)
                if resp:
                    # Smart token finder (handles different JSON structures)
                    token = None
                    user = None
                    
                    if "token" in resp:
                        token = resp["token"]
                        user = resp.get("user")
                    elif "session" in resp and "token" in resp["session"]:
                        token = resp["session"]["token"]
                        user = resp.get("user")
                    elif "data" in resp:
                        data = resp["data"]
                        if "token" in data:
                            token = data["token"]
                            user = data.get("user")
                        elif "session" in data and "token" in data["session"]:
                            token = data["session"]["token"]
                            user = data.get("user")
                            
                    if token:
                        st.session_state["auth_token"] = token
                        st.session_state["user"] = user
                        st.success("✅ Logged in successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Login succeeded, but could not find the token.")
                else:
                    st.error("❌ Invalid email or password.")
                    
    with tab_signup:
        with st.form("signup_form"):
            st.info("🛠️ Create your master admin account for the first time.")
            name = st.text_input("Name", value="Admin")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)
            
            if submitted:
                resp = auth_client.sign_up(email, password, name)
                if resp:
                    st.success("✅ Account created! Please switch to the **Login** tab to sign in.")
                else:
                    st.error("❌ Failed to create account.")
                    
    st.stop()

# ==============================================================================
# 2. VERIFY SESSION & DASHBOARD (API Verification)
# ==============================================================================
# 🔥 FIX: We ask the API to verify the opaque token instead of decoding a JWT
user_data = auth_client.get_session(st.session_state["auth_token"])

if not user_data:
    st.error("❌ Session expired or invalid. Please log in again.")
    if st.button("Clear Session"):
        st.session_state.clear()
        st.rerun()
    st.stop()

# Extract email from the API response (Better Auth usually returns the user object directly)
user_email = user_data.get("email", "Unknown User")

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
