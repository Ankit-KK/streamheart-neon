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

st.title("🔍 Creator Profile & Data")
st.caption("Select a creator to view their live ledger, payment history, and manage their payout details.")

# ==============================================================================
# 2. CREATOR SELECTION
# ==============================================================================
creators_df = run_query("""
    SELECT id, creator_handle, creator_code 
    FROM creators 
    ORDER BY creator_handle ASC
""")

if creators_df.empty:
    st.warning("No creators found. Please add a creator in the '1_Creators' page first.")
    st.stop()

# Create a clean dropdown
creator_options = {f"{row['creator_handle']} ({row['creator_code']})": row['id'] for _, row in creators_df.iterrows()}
selected_name = st.selectbox("Select Creator to View", options=list(creator_options.keys()))
selected_id = creator_options[selected_name]

st.divider()

# ==============================================================================
# 3. SECTION A: LIVE LEDGER METRICS
# ==============================================================================
st.subheader("💰 Financial Ledger")

ledger_df = run_query("""
    SELECT total_gross_inr, total_fees_inr, total_tax_inr, total_refunds_inr, total_payments_count
    FROM creator_ledger 
    WHERE creator_id = %s
""", (selected_id,))

if not ledger_df.empty:
    row = ledger_df.iloc[0]
    gross = (row['total_gross_inr'] or 0) / 100.0
    fees = (row['total_fees_inr'] or 0) / 100.0
    tax = (row['total_tax_inr'] or 0) / 100.0
    refunds = (row['total_refunds_inr'] or 0) / 100.0
    count = row['total_payments_count'] or 0
    
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Payments", count)
    m2.metric("Gross Revenue", f"₹{gross:,.2f}")
    m3.metric("Platform Fees", f"₹{fees:,.2f}")
    m4.metric("Taxes", f"₹{tax:,.2f}")
    m5.metric("Refunds", f"₹{refunds:,.2f}")
else:
    st.info("No ledger data found for this creator yet.")

st.divider()

# ==============================================================================
# 4. SECTION B: RECENT PAYMENTS
# ==============================================================================
st.subheader("💳 Recent Payments")

payments_df = run_query("""
    SELECT 
        payment_id,
        created_at,
        original_currency,
        original_amount,
        amount_inr,
        fee_inr,
        status,
        receipt
    FROM payments 
    WHERE creator_id = %s
    ORDER BY created_at DESC
    LIMIT 20
""", (selected_id,))

if payments_df.empty:
    st.info("No payments mapped to this creator yet. Run the Sync Engine to pull Razorpay data.")
else:
    display_df = payments_df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['amount_inr'] = display_df['amount_inr'] / 100.0
    display_df['original_amount'] = display_df['original_amount'] / 100.0
    display_df['fee_inr'] = display_df['fee_inr'] / 100.0
    
    st.dataframe(
        display_df,
        column_config={
            "payment_id": st.column_config.TextColumn("Payment ID", width="small"),
            "created_at": st.column_config.TextColumn("Date", width="small"),
            "original_currency": st.column_config.TextColumn("Currency", width="small"),
            "original_amount": st.column_config.NumberColumn("Original Amt", format="%.2f"),
            "amount_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
            "fee_inr": st.column_config.NumberColumn("Fee (₹)", format="%.2f"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "receipt": st.column_config.TextColumn("Razorpay Receipt", width="medium")
        },
        hide_index=True,
        width='stretch'
    )

st.divider()

# ==============================================================================
# 5. SECTION C: FINANCIAL DOCUMENTS (VIEW & EDIT)
# ==============================================================================
st.subheader("🏦 UPI & Bank Details for Payouts")
st.info("Enter the creator's financial details here. This data is required to generate payout CSVs.")

# Fetch existing financials to pre-fill the form
fin_df = run_query("SELECT * FROM creator_financials WHERE creator_id = %s", (selected_id,))
fin_data = fin_df.iloc[0].to_dict() if not fin_df.empty else {}

with st.form("financials_form"):
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**👤 Personal & Tax Details**")
        legal_name = st.text_input("Legal Name (as per PAN)", value=fin_data.get('legal_name', ''))
        pan_number = st.text_input("PAN Number", value=fin_data.get('pan_number', ''))
        upi_id = st.text_input("UPI ID (for payouts)", value=fin_data.get('upi_id', ''))
        
    with col2:
        st.markdown("**🏦 Bank Account Details**")
        bank_name = st.text_input("Bank Name", value=fin_data.get('bank_name', ''))
        account_holder = st.text_input("Account Holder Name", value=fin_data.get('account_holder_name', ''))
        acc_last4 = st.text_input("Account Number (Last 4 Digits)", value=fin_data.get('account_number_last4', ''))
        ifsc = st.text_input("IFSC Code", value=fin_data.get('ifsc', ''))
        
    submitted = st.form_submit_button("💾 Save / Update Financial Details", type="primary", width='stretch')
    
    if submitted:
        # 🔥 UPSERT: Insert if new, Update if exists
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
        
        st.success(f"✅ UPI and Bank details for {selected_name} saved securely!")
        st.rerun()
