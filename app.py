import streamlit as st
from utils.auth import get_auth_client

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")

auth_client = get_auth_client()

# ==============================================================================
# 1. AUTHENTICATION LAYER (REST API)
# ==============================================================================
if "user" not in st.session_state:
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
                    user = None
                    
                    # 🔥 FIX: Extract the user object directly from the login response
                    if "user" in resp:
                        user = resp["user"]
                    elif "data" in resp and "user" in resp["data"]:
                        user = resp["data"]["user"]
                            
                    if user:
                        st.session_state["user"] = user
                        st.success("✅ Logged in successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Login succeeded, but could not find user data.")
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
# 2. DASHBOARD (Using Streamlit Session State)
# ==============================================================================
# 🔥 FIX: We don't need to call the API on every load. 
# Streamlit's session state is secure and isolated per user.
user_data = st.session_state.get("user")
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
