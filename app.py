import streamlit as st
from utils.auth import get_admin_count, create_admin, verify_login

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")

# ==============================================================================
# 1. AUTHENTICATION LAYER
# ==============================================================================
if not st.session_state.get('authenticated'):
    
    admin_count = get_admin_count()
    
    if admin_count == 0:
        # 🟢 FIRST RUN: SETUP WIZARD
        st.title("🛠️ Initial System Setup")
        st.info("No admin account found. Please create the master admin account to secure the dashboard.")
        
        with st.form("setup_form"):
            email = st.text_input("Admin Email")
            password = st.text_input("Create Password", type="password")
            submitted = st.form_submit_button("Create Admin & Login", type="primary", use_container_width=True)
            
            if submitted:
                if not email or not password:
                    st.error("Email and Password cannot be empty.")
                else:
                    create_admin(email, password)
                    st.session_state['authenticated'] = True
                    st.session_state['user_email'] = email
                    st.success("✅ Admin created! Loading dashboard...")
                    st.rerun()
    else:
        # 🔵 STANDARD SECURE LOGIN
        st.title("🔐 StreamHeart CMS Login")
        
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
            
            if submitted:
                if verify_login(email, password):
                    st.session_state['authenticated'] = True
                    st.session_state['user_email'] = email
                    st.success("✅ Logged in successfully!")
                    st.rerun()
                else:
                    st.error("❌ Invalid email or password.")
                    
    st.stop() # Stops the rest of the app from loading if not authenticated

# ==============================================================================
# 2. DASHBOARD (Only visible if authenticated)
# ==============================================================================
col_title, col_logout = st.columns([4, 1])
with col_title:
    st.title("💖 StreamHeart Admin Dashboard")
    st.caption(f"Welcome back, **{st.session_state.get('user_email')}**")
with col_logout:
    st.write("") 
    if st.button("🚪 Logout", type="secondary", use_container_width=True):
        st.session_state['authenticated'] = False
        st.session_state['user_email'] = None
        st.rerun()

st.divider()
st.info("👈 Use the **sidebar on the left** to navigate to specific modules.")
