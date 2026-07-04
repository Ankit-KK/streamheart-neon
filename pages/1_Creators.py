import streamlit as st
import pandas as pd
from utils.db import run_query
from utils.auth import verify_session

# ==============================================================================
# 1. SECURITY CHECK
# ==============================================================================
session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None

if not current_user:
    st.error("❌ Access Denied. Please log in.")
    st.stop()

st.set_page_config(page_title="Creators Management", page_icon="👥", layout="wide")
st.title("👥 Creators & Financials Management")
st.caption("Manage your streamers and their payout details. Adding a creator automatically provisions their accounting ledger.")

# ==============================================================================
# 2. TABS LAYOUT
# ==============================================================================
tab_list, tab_add = st.tabs(["📋 All Creators", "➕ Add New Creator"])

# ==============================================================================
# 3. TAB 1: ALL CREATORS & FINANCIALS
# ==============================================================================
with tab_list:
    st.subheader("Registered Creators")
    
    # Fetch all creators
    creators_df = run_query("""
        SELECT id, creator_handle, creator_code, payout_rate, status, created_at 
        FROM creators 
        ORDER BY created_at DESC
    """)
    
    if creators_df.empty:
        st.info("No creators found yet. Go to the 'Add New Creator' tab to onboard your first streamer!")
    else:
        # Display the main table
        display_df = creators_df.copy()
        display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d')
        
        st.dataframe(
            display_df, 
            column_config={
                "id": None, # Hide the UUID
                "creator_handle": st.column_config.TextColumn("Stream Handle", width="medium"),
                "creator_code": st.column_config.TextColumn("Unique Code", width="small"),
                "payout_rate": st.column_config.NumberColumn("Payout %", format="%.2f"),
                "status": st.column_config.TextColumn("Status", width="small"),
                "created_at": st.column_config.TextColumn("Onboarded On", width="small")
            },
            hide_index=True,
            width='stretch'
        )
        
        st.divider()
        st.subheader("🏦 Manage Financial Documents")
        st.info("Select a creator below to view or update their secure banking and tax details for payouts.")
        
        # Create a dropdown to select a creator
        creator_options = {f"{row['creator_handle']} ({row['creator_code']})": row['id'] for _, row in creators_df.iterrows()}
        selected_name = st.selectbox("Select Creator", options=list(creator_options.keys()))
        selected_id = creator_options[selected_name]
        
        # Fetch existing financials for the selected creator
        fin_df = run_query("SELECT * FROM creator_financials WHERE creator_id = %s", (selected_id,))
        
        # Pre-fill form if data exists
        fin_data = fin_df.iloc[0].to_dict() if not fin_df.empty else {}
        
        with st.form("financials_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                legal_name = st.text_input("Legal Name (as per PAN)", value=fin_data.get('legal_name', ''))
                pan_number = st.text_input("PAN Number", value=fin_data.get('pan_number', ''))
                upi_id = st.text_input("UPI ID (for payouts)", value=fin_data.get('upi_id', ''))
                
            with col2:
                bank_name = st.text_input("Bank Name", value=fin_data.get('bank_name', ''))
                account_holder = st.text_input("Account Holder Name", value=fin_data.get('account_holder_name', ''))
                acc_last4 = st.text_input("Account Number (Last 4 Digits)", value=fin_data.get('account_number_last4', ''))
                ifsc = st.text_input("IFSC Code", value=fin_data.get('ifsc', ''))
                
            submitted = st.form_submit_button("💾 Save Financial Details", type="primary", width='stretch')
            
            if submitted:
                # 🔥 UPSERT: Insert or Update the financial details securely
                run_query("""
                    INSERT INTO creator_financials (
                        creator_id, legal_name, pan_number, upi_id, bank_name, 
                        account_holder_name, account_number_last4, ifsc
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (creator_id) DO UPDATE SET
                        legal_name = EXCLUDED.legal_name,
                        pan_number = EXCLUDED.pan_number,
                        upi_id = EXCLUDED.upi_id,
                        bank_name = EXCLUDED.bank_name,
                        account_holder_name = EXCLUDED.account_holder_name,
                        account_number_last4 = EXCLUDED.account_number_last4,
                        ifsc = EXCLUDED.ifsc,
                        updated_at = NOW()
                """, (selected_id, legal_name, pan_number, upi_id, bank_name, account_holder, acc_last4, ifsc))
                
                st.success(f"✅ Financial details for {selected_name} saved securely!")
                st.rerun()

# ==============================================================================
# 4. TAB 2: ADD NEW CREATOR
# ==============================================================================
with tab_add:
    st.subheader("Onboard a New Creator")
    st.warning("⚠️ The 'Unique Code' must exactly match the prefix used in Razorpay order receipts (e.g., if receipt is 'rvs_123', code must be 'rvs').")
    
    with st.form("add_creator_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_handle = st.text_input("Stream Handle (e.g., Raven Sharp)")
            new_code = st.text_input("Unique Code (e.g., rvs)").lower().strip()
            
        with col2:
            new_rate = st.number_input("Default Payout Rate (%)", min_value=0.0, max_value=100.0, value=89.00, step=0.01)
            new_status = st.selectbox("Initial Status", ["ACTIVE", "INACTIVE"])
            
        new_notes = st.text_area("Notes (Optional)")
        
        submitted = st.form_submit_button("🚀 Create Creator & Provision Ledger", type="primary", width='stretch')
        
        if submitted:
            if not new_handle or not new_code:
                st.error("❌ Handle and Unique Code are required.")
            else:
                try:
                    # Insert into creators table
                    run_query("""
                        INSERT INTO creators (creator_handle, creator_code, payout_rate, status, notes) 
                        VALUES (%s, %s, %s, %s, %s)
                    """, (new_handle, new_code, new_rate, new_status, new_notes))
                    
                    st.success(f"✅ Creator '{new_handle}' added successfully!")
                    st.info("🪄 The database trigger has automatically created their empty accounting ledger. You can now start syncing their payments.")
                    st.balloons()
                    
                except Exception as e:
                    if "duplicate key value violates unique constraint" in str(e):
                        st.error(f"❌ The code '{new_code}' is already in use. Please choose a different unique code.")
                    else:
                        st.error(f"❌ Database Error: {e}")
