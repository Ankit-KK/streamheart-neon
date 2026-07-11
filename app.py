import streamlit as st
from utils.auth import (
    get_user_count, create_user, get_user_by_email, 
    verify_password, create_session, verify_session, revoke_session,
    create_reset_token, reset_password_with_token
)

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")

# ==============================================================================
# 1. CHECK FOR EXISTING SESSION
# ==============================================================================
current_user = None
session_token = st.session_state.get("session_token")

if session_token:
    current_user = verify_session(session_token)
    if not current_user:
        st.session_state.clear()

# ==============================================================================
# 2. AUTHENTICATION SCREENS
# ==============================================================================
if not current_user:
    user_count = get_user_count()
    
    if user_count == 0:
        st.title("🛠️ Initial System Setup")
        st.info("No admin accounts found. Create your master admin account to get started.")
        
        with st.form("setup_form"):
            email = st.text_input("Email")
            password = st.text_input("Create Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Create Admin Account", type="primary", width='stretch')
            
            if submitted:
                if not email or not password:
                    st.error("Email and Password cannot be empty.")
                elif len(password) < 8:
                    st.error("Password must be at least 8 characters.")
                elif password != confirm:
                    st.error("Passwords do not match.")
                elif create_user(email, password, "SUPER_ADMIN"):
                    user = get_user_by_email(email)
                    token = create_session(str(user['id']))
                    st.session_state["session_token"] = token
                    st.success("✅ Admin created! Redirecting...")
                    st.rerun()
                else:
                    st.error("❌ Failed to create account. Email may already exist.")
    else:
        st.title("🔐 StreamHeart CMS")
        
        tab_login, tab_forgot = st.tabs(["Login", "Forgot Password"])
        
        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", type="primary", width='stretch')
                
                if submitted:
                    user = get_user_by_email(email)
                    if user and user['status'] == 'ACTIVE' and verify_password(password, user['password_hash']):
                        token = create_session(str(user['id']))
                        st.session_state["session_token"] = token
                        st.success("✅ Logged in successfully!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid email, password, or account suspended.")
                        
        with tab_forgot:
            if "reset_token" not in st.session_state:
                st.info("Enter your email. A password reset token will be generated.")
                st.warning("⚠️ Email sending is not configured yet. The token will be displayed on screen for now.")
                
                with st.form("forgot_form"):
                    email = st.text_input("Email")
                    submitted = st.form_submit_button("Generate Reset Token", type="secondary", width='stretch')
                    
                    if submitted:
                        token = create_reset_token(email)
                        if token:
                            st.session_state["reset_token"] = token
                            st.success("🔑 Reset Token (valid for 1 hour):")
                            st.code(token)
                            st.rerun()
                        else:
                            st.error("❌ No account found with that email.")
            else:
                st.success("✅ Token generated successfully!")
                st.markdown("**Your Reset Token:**")
                st.code(st.session_state["reset_token"])
                st.info("Copy this token, paste it below, and set your new password.")
                
                with st.form("reset_form"):
                    reset_token_input = st.text_input("Paste Reset Token", value=st.session_state["reset_token"])
                    new_pass = st.text_input("New Password", type="password")
                    confirm_pass = st.text_input("Confirm New Password", type="password")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        reset_submitted = st.form_submit_button("Reset Password", type="primary", width='stretch')
                    with col2:
                        cancel_submitted = st.form_submit_button("Cancel", type="secondary", width='stretch')
                    
                    if reset_submitted:
                        if new_pass != confirm_pass:
                            st.error("Passwords do not match.")
                        elif len(new_pass) < 8:
                            st.error("Password must be at least 8 characters.")
                        else:
                            if reset_password_with_token(reset_token_input, new_pass):
                                st.success("✅ Password reset successfully! Please login with your new password.")
                                if "reset_token" in st.session_state:
                                    del st.session_state["reset_token"]
                            else:
                                st.error("❌ Invalid or expired reset token.")
                                
                    if cancel_submitted:
                        if "reset_token" in st.session_state:
                            del st.session_state["reset_token"]
                        st.rerun()
                    
    st.stop()

# ==============================================================================
# 3. DASHBOARD
# ==============================================================================
col_title, col_info, col_logout = st.columns([3, 2, 1])
with col_title:
    st.title("💖 StreamHeart Admin")
with col_info:
    st.caption(f"👤 {current_user['email']}")
    st.caption(f"🔑 Role: {current_user['role']}")
with col_logout:
    st.write("")
    if st.button("🚪 Logout", type="secondary", width='stretch'):
        revoke_session(session_token)
        st.session_state.clear()
        st.rerun()

st.divider()
st.info("👈 Use the **sidebar on the left** to navigate to Dashboard, Creators, Payouts, and User Management.")
