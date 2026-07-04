import streamlit as st

st.set_page_config(page_title="StreamHeart CMS", page_icon="💖", layout="wide")

# 🔒 AUTH PLACEHOLDER (Swap with your Neon Auth logic later)
if not st.session_state.get("authenticated"):
    with st.form("login_form"):
        st.text_input("Admin Password", type="password", key="password")
        if st.form_submit_button("🔓 Login", type="primary", use_container_width=True):
            if st.session_state.password == "streamheart123": # Change this!
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()

st.sidebar.title("💖 StreamHeart")
st.sidebar.success("✅ Logged In")
if st.sidebar.button("🚪 Logout"):
    st.session_state.authenticated = False
    st.rerun()

st.title("💖 StreamHeart CMS")
st.info("👈 Use the sidebar to navigate. All metrics load instantly from the `creator_ledger`.")
