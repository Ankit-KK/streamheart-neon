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
st.caption("View your registered streamers and onboard new ones with all their details.")

tab_list, tab_add = st.tabs(["📋 View All Creators", "➕ Add New Creator"])

# ==============================================================================
# TAB 1: VIEW ALL CREATORS
# ==============================================================================
with tab_list:
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
# TAB 2: ADD NEW CREATOR (FULL ONBOARDING)
# ==============================================================================
with tab_add:
    st.subheader("Onboard a New Creator")
    st.warning("⚠️ The 'Unique Code' must exactly match the prefix used in Razorpay order receipts.")
    
    with st.form("add_creator_form"):
        # --- SECTION 1: CORE IDENTITY ---
        st.markdown("### 1. Core Identity")
        col1, col2 = st.columns(2)
        with col1:
            new_handle = st.text_input("Stream Handle (e.g., Raven Sharp)")
            new_code = st.text_input("Unique Code (e.g., rvs)").lower().strip()
            new_email = st.text_input("Contact Email (for receipts)")
        with col2:
            new_rate = st.number_input("Default Payout Rate (%)", min_value=0.0, max_value=100.0, value=89.00, step=0.01)
            new_status = st.selectbox("Initial Status", ["ACTIVE", "INACTIVE"])
            new_notes = st.text_area("Notes (Optional)")
            
        st.divider()
        
        # --- SECTION 2: PERSONAL & TAX ---
        st.markdown("### 2. Personal & Tax Details")
        col3, col4 = st.columns(2)
        with col3:
            new_legal_name = st.text_input("Legal Name (as per PAN)")
            new_pan = st.text_input("PAN Number")
        with col4:
            new_upi = st.text_input("UPI ID (for payouts)")
            
        st.divider()
        
        # --- SECTION 3: BANK DETAILS ---
        st.markdown("### 3. Bank Account Details")
        col5, col6 = st.columns(2)
        with col5:
            new_bank_name = st.text_input("Bank Name")
            new_acc_holder = st.text_input("Account Holder Name")
        with col6:
            new_acc_last4 = st.text_input("Account Number (Last 4 Digits)")
            new_ifsc = st.text_input("IFSC Code")
            
        submitted = st.form_submit_button("🚀 Create Creator & Save Financials", type="primary", width='stretch')
        
        if submitted:
            if not new_handle or not new_code:
                st.error("❌ Handle and Unique Code are required.")
            else:
                try:
                    # 1. Insert Core Details into 'creators' table
                    run_query("""
                        INSERT INTO creators (creator_handle, creator_code, contact_email, payout_rate, status, notes) 
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (new_handle, new_code, new_email, new_rate, new_status, new_notes))
                    
                    # 2. Fetch the newly created ID using the unique code
                    id_df = run_query("SELECT id FROM creators WHERE creator_code = %s", (new_code,))
                    if id_df.empty:
                        st.error("❌ Failed to retrieve new creator ID.")
                    else:
                        new_id = str(id_df.iloc[0]['id'])
                        
                        # 3. Insert Financial Details into 'creator_financials' table
                        run_query("""
                            INSERT INTO creator_financials (
                                creator_id, legal_name, pan_number, upi_id, bank_name, 
                                account_holder_name, account_number_last4, ifsc
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (new_id, new_legal_name, new_pan, new_upi, new_bank_name, new_acc_holder, new_acc_last4, new_ifsc))
                        
                        st.success(f"✅ Creator '{new_handle}' and all financial details added successfully!")
                        st.balloons()
                        
                except Exception as e:
                    if "duplicate key value violates unique constraint" in str(e):
                        st.error(f"❌ The code '{new_code}' is already in use.")
                    else:
                        st.error(f"❌ Database Error: {e}")
