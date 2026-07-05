import streamlit as st
import pandas as pd
import datetime
from utils.db import run_query
from utils.auth import verify_session
from utils.payouts import process_payout

# ==============================================================================
# 1. SECURITY CHECK
# ==============================================================================
session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None
if not current_user:
    st.error("❌ Access Denied.")
    st.stop()

st.title("💸 Payout Management")
st.caption("Process date-specific creator payouts and view the permanent audit trail.")

tab_pending, tab_history = st.tabs(["🔄 Process Payout", "📜 Payout History"])

# ==============================================================================
# 2. TAB 1: PROCESS PAYOUT (DATE-SPECIFIC)
# ==============================================================================
with tab_pending:
    st.subheader("📅 Process a Date-Specific Payout")
    st.info("Select a date range to calculate earnings for a specific period. This allows you to pay for 'June' without touching 'May' rollover balances.")

    col1, col2 = st.columns(2)
    with col1:
        # 🔥 FIX: Force "today" to be calculated in IST
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        default_end = datetime.datetime.now(ist_tz).date()
        default_start = default_end - datetime.timedelta(days=30)
        
date_range = st.date_input("Payout Period (IST)", value=(default_start, default_end), key="payout_period")
    
    with col2:
        st.write("") 
        st.write("") 
        if len(date_range) == 2:
            st.success(f"📅 Calculating for: **{date_range[0]}** to **{date_range[1]}**")

    if len(date_range) != 2:
        st.warning("Please select a valid start and end date.")
        st.stop()

    start_date, end_date = date_range

    creators_df = run_query("SELECT id, creator_handle, payout_rate FROM creators WHERE status = 'ACTIVE' ORDER BY creator_handle")
    if creators_df.empty:
        st.warning("No active creators found.")
        st.stop()

    creator_options = {row['creator_handle']: row['id'] for _, row in creators_df.iterrows()}
    selected_name = st.selectbox("Select Creator to Pay", options=list(creator_options.keys()))
    selected_id = creator_options[selected_name]
    
    selected_row = creators_df[creators_df['id'] == selected_id].iloc[0]
    payout_rate = float(selected_row['payout_rate'])

    # --- CALCULATION ENGINE ---
    # Get Period Specific Earnings (Filtered by IST Date)
    period_df = run_query("""
        SELECT 
            SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END) as period_gross,
            SUM(CASE WHEN status = 'refunded' THEN amount_inr ELSE 0 END) as period_refunds
        FROM payments
        WHERE creator_id = %s 
          AND (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
    """, (selected_id, start_date, end_date))

    if not period_df.empty:
        p_gross = int(pd.to_numeric(period_df.iloc[0]['period_gross'], errors='coerce') or 0)
        p_refunds = int(pd.to_numeric(period_df.iloc[0]['period_refunds'], errors='coerce') or 0)
    else:
        p_gross, p_refunds = 0, 0

    period_net_paise = int((p_gross - p_refunds) * (payout_rate / 100.0))
    period_net_inr = period_net_paise / 100.0

    # --- DISPLAY SUMMARY ---
    st.divider()
    st.markdown(f"### 💰 Payout Summary for **{selected_name}**")
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Period Gross (IST)", f"₹{p_gross / 100.0:,.2f}")
    m2.metric("Period Refunds (IST)", f"₹{p_refunds / 100.0:,.2f}")
    m3.metric("Net to Pay", f"₹{period_net_inr:,.2f}", delta=f"@ {payout_rate}%")

    if period_net_paise <= 0:
        st.warning("⚠️ No earnings found for this creator in the selected date range (IST).")
    else:
        st.divider()
        st.subheader("📝 Confirm Payout")
        
        with st.form("payout_form"):
            ref = st.text_input("Transaction Reference / UTR Number", placeholder="e.g., UTR123456789")
            method = st.selectbox("Payment Method", ["UPI", "NEFT", "IMPS", "Bank Transfer", "RazorpayX"])
            notes = st.text_area("Notes (Optional)")
            
            submit_btn = st.form_submit_button("🔒 Confirm & Archive Payout", type="primary", width='stretch')
            
            if submit_btn:
                if not ref:
                    st.error("❌ Transaction Reference is mandatory.")
                else:
                    success = process_payout(
                        creator_id=selected_id, gross_inr=p_gross, refunds_inr=p_refunds,
                        payout_rate=payout_rate, net_payout_inr=period_net_paise,
                        reference=ref, method=method, notes=notes,
                        period_start=start_date, period_end=end_date
                    )
                    if success:
                        st.success(f"✅ ₹{period_net_inr:,.2f} paid to {selected_name} for period {start_date} to {end_date}.")
                        st.balloons()
                        st.rerun()

# ==============================================================================
# 3. TAB 2: PAYOUT HISTORY
# ==============================================================================
with tab_history:
    st.subheader("📜 Permanent Payout Audit Trail")
    
    history_df = run_query("""
        SELECT 
            c.creator_handle,
            ph.period_start,
            ph.period_end,
            (ph.processed_at AT TIME ZONE 'Asia/Kolkata') as processed_at,
            ph.net_payout_inr,
            ph.transaction_reference,
            ph.payment_method,
            ph.notes
        FROM payout_history ph
        JOIN creators c ON ph.creator_id = c.id
        ORDER BY ph.processed_at DESC
    """)
    
    if history_df.empty:
        st.info("No payouts have been processed yet.")
    else:
        display_hist = history_df.copy()
        display_hist['processed_at'] = pd.to_datetime(display_hist['processed_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
        display_hist['net_payout_inr'] = pd.to_numeric(display_hist['net_payout_inr'], errors='coerce').fillna(0) / 100.0
        
        st.dataframe(
            display_hist,
            column_config={
                "creator_handle": "Creator",
                "period_start": "Period Start",
                "period_end": "Period End",
                "processed_at": "Paid On (IST)",
                "net_payout_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
                "transaction_reference": "UTR / Reference",
                "payment_method": "Method",
                "notes": "Notes"
            },
            hide_index=True,
            width='stretch'
        )
