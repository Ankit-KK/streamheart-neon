import streamlit as st
import pandas as pd
from utils.db import run_query
from utils.auth import verify_session

session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None
if not current_user:
    st.error("❌ Access Denied.")
    st.stop()

st.title("👥 Creators Management")
st.caption("View your registered streamers and onboard new ones.")

tab_list, tab_add = st.tabs(["📋 View All Creators", "➕ Add New Creator"])

# ==============================================================================
# TAB 1: VIEW ALL CREATORS
# ==============================================================================
with tab_list:
    # 🔥 FIX: Added contact_email to the query
    creators_df = run_query("""
        SELECT creator_handle, creator_code, contact_email, payout_rate, status, created_at 
        FROM creators 
        ORDER BY created_at DESC
    """)
    
    if creators_df.empty:
        st.info("No creators found yet. Go to the '➕ Add New Creator' tab to onboard your first streamer!")
    else:
        display_df = creators_df.copy()
        display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d')
        display_df['contact_email'] = display_df['contact_email'].fillna("Not Provided")
        
        st.dataframe(
            display_df, 
            column_config={
                "creator_handle": st.column_config.TextColumn("Stream Handle", width="medium"),
                "creator_code": st.column_config.TextColumn("Unique Code", width="small"),
                "contact_email": st.column_config.TextColumn("Contact Email", width="medium"),
                "payout_rate": st.column_config.NumberColumn("Payout %", format="%.2f"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "created_at": st.column_config.TextColumn("Onboarded On", width="small")
            },
            hide_index=True,
            width='stretch'
        )

# ==============================================================================
# TAB 2: ADD NEW CREATOR
# ==============================================================================
with tab_add:
    st.subheader("Onboard a New Creator")
    st.warning("⚠️ The 'Unique Code' must exactly match the prefix used in Razorpay order receipts.")
    
    with st.form("add_creator_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_handle = st.text_input("Stream Handle (e.g., Raven Sharp)")
            new_code = st.text_input("Unique Code (e.g., rvs)").lower().strip()
            # 🔥 FIX: Added Email capture during onboarding
            new_email = st.text_input("Contact Email (for future receipts)")
            
        with col2:
            new_rate = st.number_input("Default Payout Rate (%)", min_value=0.0, max_value=100.0, value=89.00, step=0.01)
            new_status = st.selectbox("Initial Status", ["ACTIVE", "INACTIVE"])
            
        new_notes = st.text_area("Notes (Optional)")
        
        submitted = st.form_submit_button("🚀 Create Creator", type="primary", width='stretch')
        
        if submitted:
            if not new_handle or not new_code:
                st.error("❌ Handle and Unique Code are required.")
            else:
                try:
                    # 🔥 FIX: Added contact_email to the INSERT query
                    run_query("""
                        INSERT INTO creators (creator_handle, creator_code, contact_email, payout_rate, status, notes) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (new_handle, new_code, new_email, new_rate, new_status, new_notes))
                    
                    st.success(f"✅ Creator '{new_handle}' added successfully!")
                    st.balloons()
                    
                except Exception as e:
                    if "duplicate key value violates unique constraint" in str(e):
                        st.error(f"❌ The code '{new_code}' is already in use.")
                    else:
                        st.error(f"❌ Database Error: {e}")
