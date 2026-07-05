import streamlit as st
import pandas as pd
import datetime
from utils.db import run_query
from utils.auth import verify_session

session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None
if not current_user:
    st.error("❌ Access Denied.")
    st.stop()

st.title("🔍 Creator Profile & Data")
st.caption("View live ledger, payment history (IST), and manage financial documents.")

# 🔥 FIX: Fetch contact_email from the main creators table
creators_df = run_query("SELECT id, creator_handle, creator_code, contact_email FROM creators ORDER BY creator_handle ASC")
if creators_df.empty:
    st.warning("No creators found.")
    st.stop()

creator_options = {f"{row['creator_handle']} ({row['creator_code']})": row['id'] for _, row in creators_df.iterrows()}
selected_name = st.selectbox("Select Creator to View", options=list(creator_options.keys()))
selected_id = creator_options[selected_name]

# 🔥 FIX: Display the email prominently at the top
selected_email = creators_df[creators_df['id'] == selected_id].iloc[0]['contact_email']
if selected_email:
    st.success(f"📧 **Contact Email:** {selected_email}")
else:
    st.warning("📧 **Contact Email:** Not provided. (Update in the '1_Creators' page or add a quick edit form here later).")

if "last_selected_id" not in st.session_state:
    st.session_state.last_selected_id = selected_id
if st.session_state.last_selected_id != selected_id:
    st.session_state.last_selected_id = selected_id
    st.session_state.edit_financials = False

st.divider()

# --- SECTION A: LIVE LEDGER ---
st.subheader("💰 Financial Ledger")
ledger_df = run_query("SELECT total_gross_inr, total_fees_inr, total_tax_inr, total_refunds_inr, total_payments_count, total_paid_out_inr FROM creator_ledger WHERE creator_id = %s", (selected_id,))

if not ledger_df.empty:
    row = ledger_df.iloc[0]
    gross = int(pd.to_numeric(row['total_gross_inr'], errors='coerce') or 0)
    refunds = int(pd.to_numeric(row['total_refunds_inr'], errors='coerce') or 0)
    paid_out = int(pd.to_numeric(row['total_paid_out_inr'], errors='coerce') or 0)
    
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Payments", row['total_payments_count'] or 0)
    m2.metric("Gross Revenue", f"₹{gross / 100.0:,.2f}")
    m3.metric("Platform Fees", f"₹{int(pd.to_numeric(row['total_fees_inr'], errors='coerce') or 0) / 100.0:,.2f}")
    m4.metric("Taxes", f"₹{int(pd.to_numeric(row['total_tax_inr'], errors='coerce') or 0) / 100.0:,.2f}")
    m5.metric("Refunds", f"₹{refunds / 100.0:,.2f}")
    m6.metric("Already Paid Out", f"₹{paid_out / 100.0:,.2f}")
else:
    st.info("No ledger data found.")

st.divider()

# --- SECTION B: PAYMENT HISTORY ---
st.subheader("💳 Payment History (IST)")
default_end = datetime.date.today()
default_start = default_end - datetime.timedelta(days=30)
date_range = st.date_input("Filter by Date Range (IST)", value=(default_start, default_end), key="payment_date_range")

base_query = """
    SELECT payment_id, (created_at AT TIME ZONE 'Asia/Kolkata') as created_at, 
           original_currency, original_amount, amount_inr, fee_inr, status, receipt 
    FROM payments WHERE creator_id = %s
"""
params = [selected_id]
if len(date_range) == 2:
    base_query += " AND (created_at AT TIME ZONE 'Asia/Kolkata')::date >= %s AND (created_at AT TIME ZONE 'Asia/Kolkata')::date <= %s"
    params.extend([date_range[0], date_range[1]])
base_query += " ORDER BY created_at DESC"

payments_df = run_query(base_query, tuple(params))
if payments_df.empty:
    st.warning("No payments found in this range.")
else:
    display_df = payments_df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['amount_inr'] = display_df['amount_inr'] / 100.0
    display_df['original_amount'] = display_df['original_amount'] / 100.0
    display_df['fee_inr'] = display_df['fee_inr'] / 100.0
    
    st.dataframe(
        display_df,
        column_config={
            "payment_id": st.column_config.TextColumn("Payment ID", width="small"),
            "created_at": st.column_config.TextColumn("Date (IST)", width="small"),
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

# --- SECTION C: FINANCIAL DOCUMENTS (EMAIL REMOVED) ---
st.subheader("🏦 UPI & Bank Details")
fin_df = run_query("SELECT * FROM creator_financials WHERE creator_id = %s", (selected_id,))
fin_data = fin_df.iloc[0].to_dict() if not fin_df.empty else {}

if "edit_financials" not in st.session_state:
    st.session_state.edit_financials = False

if not st.session_state.edit_financials:
    if not fin_data:
        st.info("No financial details saved yet.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**👤 Personal & Tax**")
            st.text(f"Legal Name: {fin_data.get('legal_name') or '-'}")
            st.text(f"PAN Number: {fin_data.get('pan_number') or '-'}")
            st.text(f"UPI ID: {fin_data.get('upi_id') or '-'}")
        with col2:
            st.markdown("**🏦 Bank Details**")
            st.text(f"Bank Name: {fin_data.get('bank_name') or '-'}")
            st.text(f"Account Holder: {fin_data.get('account_holder_name') or '-'}")
            st.text(f"Acc (Last 4): {fin_data.get('account_number_last4') or '-'}")
            st.text(f"IFSC Code: {fin_data.get('ifsc') or '-'}")
    if st.button("✏️ Edit Details", type="primary"):
        st.session_state.edit_financials = True
        st.rerun()
else:
    st.warning("⚠️ Edit Mode Active")
    with st.form("financials_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**👤 Personal & Tax Details**")
            # 🔥 FIX: Email is completely removed from this form
            legal_name = st.text_input("Legal Name", value=fin_data.get('legal_name', ''))
            pan_number = st.text_input("PAN", value=fin_data.get('pan_number', ''))
            upi_id = st.text_input("UPI ID", value=fin_data.get('upi_id', ''))
        with col2:
            st.markdown("**🏦 Bank Account Details**")
            bank_name = st.text_input("Bank Name", value=fin_data.get('bank_name', ''))
            account_holder = st.text_input("Acc Holder", value=fin_data.get('account_holder_name', ''))
            acc_last4 = st.text_input("Acc Last 4", value=fin_data.get('account_number_last4', ''))
            ifsc = st.text_input("IFSC", value=fin_data.get('ifsc', ''))
            
        c1, c2 = st.columns(2)
        with c1: save_btn = st.form_submit_button("💾 Save", type="primary", width='stretch')
        with c2: cancel_btn = st.form_submit_button("❌ Cancel", width='stretch')
            
        if save_btn:
            # 🔥 FIX: Email is completely removed from this UPSERT query
            run_query("""
                INSERT INTO creator_financials (creator_id, legal_name, pan_number, upi_id, bank_name, account_holder_name, account_number_last4, ifsc) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (creator_id) DO UPDATE SET 
                    legal_name=EXCLUDED.legal_name, 
                    pan_number=EXCLUDED.pan_number, 
                    upi_id=EXCLUDED.upi_id, 
                    bank_name=EXCLUDED.bank_name, 
                    account_holder_name=EXCLUDED.account_holder_name, 
                    account_number_last4=EXCLUDED.account_number_last4, 
                    ifsc=EXCLUDED.ifsc, 
                    updated_at=NOW()
            """, (selected_id, legal_name, pan_number, upi_id, bank_name, account_holder, acc_last4, ifsc))
            st.session_state.edit_financials = False
            st.success("✅ Saved!")
            st.rerun()
        if cancel_btn:
            st.session_state.edit_financials = False
            st.rerun()
