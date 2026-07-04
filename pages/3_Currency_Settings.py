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

st.title("💱 Currency Exchange Rates")
st.caption("Manage the exchange rates used by the Razorpay Sync Engine to convert foreign payments to INR.")
st.warning("⚠️ **Crucial:** The rate for INR must always be exactly 1.0000. Changing it will break all historical and future calculations.")

# ==============================================================================
# 2. VIEW CURRENT RATES
# ==============================================================================
st.subheader("📊 Current Exchange Rates")

rates_df = run_query("SELECT currency_code, rate_to_inr FROM currency_rates ORDER BY currency_code ASC")

if rates_df.empty:
    st.info("No currency rates found. Please add INR (1.0000) to start.")
else:
    # Format the display
    display_df = rates_df.copy()
    display_df['rate_to_inr'] = display_df['rate_to_inr'].apply(lambda x: f"{float(x):.4f}")
    
    st.dataframe(
        display_df,
        column_config={
            "currency_code": st.column_config.TextColumn("Currency Code", width="small"),
            "rate_to_inr": st.column_config.TextColumn("Rate to 1 INR", width="medium")
        },
        hide_index=True,
        width='stretch'
    )

st.divider()

# ==============================================================================
# 3. ADD OR UPDATE A RATE
# ==============================================================================
st.subheader("➕ Add or Update Rate")
st.info("Enter a currency code (e.g., USD, EUR, GBP) and its current exchange rate to 1 INR.")

with st.form("rate_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        # Force uppercase and strip spaces
        new_code = st.text_input("Currency Code (e.g., USD)").upper().strip()
        
    with col2:
        new_rate = st.number_input(
            "Exchange Rate to INR", 
            min_value=0.0001, 
            value=1.0000, 
            step=0.0100, 
            format="%.4f",
            help="How many INR equal 1 unit of this currency? (e.g., 1 USD = 83.50 INR)"
        )
        
    submitted = st.form_submit_button("💾 Save / Update Rate", type="primary", width='stretch')
    
    if submitted:
        if not new_code:
            st.error("❌ Currency Code cannot be empty.")
        elif new_code == "INR" and new_rate != 1.0000:
            st.error("❌ The INR rate must always be exactly 1.0000!")
        else:
            # UPSERT: Insert if new, update if exists
            run_query("""
                INSERT INTO currency_rates (currency_code, rate_to_inr) 
                VALUES (%s, %s)
                ON CONFLICT (currency_code) DO UPDATE SET rate_to_inr = EXCLUDED.rate_to_inr
            """, (new_code, new_rate))
            
            st.success(f"✅ Rate for {new_code} successfully updated to {new_rate:.4f}!")
            st.rerun()

st.divider()

# ==============================================================================
# 4. DELETE A CURRENCY
# ==============================================================================
st.subheader("🗑️ Remove a Currency")
st.warning("⚠️ If you delete a currency, any future payments in that currency will be skipped by the Sync Engine until you add it back.")

# Get list of deletable currencies (Exclude INR to prevent disaster)
deletable_codes = [row['currency_code'] for _, row in rates_df.iterrows() if row['currency_code'] != 'INR']

if not deletable_codes:
    st.info("No extra currencies to delete (INR cannot be deleted).")
else:
    with st.form("delete_form"):
        code_to_delete = st.selectbox("Select Currency to Remove", options=deletable_codes)
        delete_btn = st.form_submit_button("🗑️ Delete Currency", type="secondary", width='stretch')
        
        if delete_btn:
            run_query("DELETE FROM currency_rates WHERE currency_code = %s", (code_to_delete,))
            st.success(f"✅ {code_to_delete} has been removed.")
            st.rerun()
