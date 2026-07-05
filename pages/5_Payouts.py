import streamlit as st
import pandas as pd
import datetime
from utils.db import run_query
from utils.auth import verify_session
from utils.payouts import generate_payout, mark_as_paid, rollback_payout

# ==============================================================================
# 1. SECURITY CHECK
# ==============================================================================
session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None
if not current_user:
    st.error("❌ Access Denied.")
    st.stop()

st.title("💰 Payout Generation & Reconciliation")
st.caption("Calculate creator earnings, lock payout records, and reconcile payments.")

tab_generate, tab_reconcile = st.tabs(["💰 Generate Payouts", "📜 Reconciliation & History"])

# ==============================================================================
# 2. TAB 1: GENERATE PAYOUTS
# ==============================================================================
with tab_generate:
    st.subheader("📅 Select Payout Period")
    
    # 🔥 FIX: Force "today" to be calculated in IST
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    default_end = datetime.datetime.now(ist_tz).date()
    default_start = default_end - datetime.timedelta(days=30)
    
    date_range = st.date_input("Payout Period (IST)", value=(default_start, default_end), key="payout_period")

    if len(date_range) != 2:
        st.warning("Please select a valid start and end date.")
        st.stop()

    start_date, end_date = date_range
    st.success(f"📅 Calculating for: **{start_date}** to **{end_date}**")
    st.divider()

    # --- SINGLE CREATOR ---
    st.subheader("👤 Single Creator Payout")
    creators_df = run_query("SELECT id, creator_handle, payout_rate FROM creators WHERE status = 'ACTIVE' ORDER BY creator_handle")
    
    if creators_df.empty:
        st.warning("No active creators found.")
    else:
        creator_options = {row['creator_handle']: row['id'] for _, row in creators_df.iterrows()}
        selected_name = st.selectbox("Select Creator", options=list(creator_options.keys()), key="single_creator_select")
        selected_id = creator_options[selected_name]
        payout_rate = float(creators_df[creators_df['id'] == selected_id].iloc[0]['payout_rate'])

        # Calculate math for this specific period
        period_df = run_query("""
            SELECT 
                SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END) as period_gross,
                SUM(CASE WHEN status = 'refunded' THEN amount_inr ELSE 0 END) as period_refunds
            FROM payments
            WHERE creator_id = %s AND (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
        """, (selected_id, start_date, end_date))

        p_gross = int(pd.to_numeric(period_df.iloc[0]['period_gross'], errors='coerce') or 0) if not period_df.empty else 0
        p_refunds = int(pd.to_numeric(period_df.iloc[0]['period_refunds'], errors='coerce') or 0) if not period_df.empty else 0
        net_paise = int((p_gross - p_refunds) * (payout_rate / 100.0))

        m1, m2, m3 = st.columns(3)
        m1.metric("Period Gross", f"₹{p_gross / 100.0:,.2f}")
        m2.metric("Period Refunds", f"₹{p_refunds / 100.0:,.2f}")
        m3.metric("Net to Pay", f"₹{net_paise / 100.0:,.2f}", delta=f"@ {payout_rate}%")

        if net_paise > 0:
            if st.button("🔒 Generate & Lock Payout for " + selected_name, type="primary"):
                payout_id = generate_payout(selected_id, p_gross, p_refunds, payout_rate, net_paise, start_date, end_date)
                if payout_id:
                    st.success(f"✅ Payout locked! Go to 'Reconciliation' tab to mark as paid.")
                else:
                    st.error("❌ A payout for this exact period already exists.")

    st.divider()

    # --- BULK ---
    st.subheader("⚡ Bulk Payouts (All Creators)")
    st.info("Calculate and lock payouts for ALL active creators in this date range at once.")
    
    if st.button("⚡ Generate All Payouts for Period", type="secondary"):
        bulk_creators = run_query("SELECT id, creator_handle, payout_rate FROM creators WHERE status = 'ACTIVE'")
        generated_count = 0
        skipped_count = 0
        
        for _, row in bulk_creators.iterrows():
            cid = row['id']
            rate = float(row['payout_rate'])
            
            b_df = run_query("""
                SELECT 
                    SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END) as g,
                    SUM(CASE WHEN status = 'refunded' THEN amount_inr ELSE 0 END) as r
                FROM payments WHERE creator_id = %s AND (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
            """, (cid, start_date, end_date))
            
            bg = int(pd.to_numeric(b_df.iloc[0]['g'], errors='coerce') or 0) if not b_df.empty else 0
            br = int(pd.to_numeric(b_df.iloc[0]['r'], errors='coerce') or 0) if not b_df.empty else 0
            bnet = int((bg - br) * (rate / 100.0))
            
            if bnet > 0:
                res = generate_payout(cid, bg, br, rate, bnet, start_date, end_date)
                if res: generated_count += 1
                else: skipped_count += 1
                
        st.success(f"✅ Bulk Generation Complete! {generated_count} payouts locked. {skipped_count} skipped (already existed or 0 balance).")
        st.balloons()

# ==============================================================================
# 3. TAB 2: RECONCILIATION & HISTORY
# ==============================================================================
with tab_reconcile:
    st.subheader("📜 Payout Ledger")
    st.info("Track the status of all generated payouts. 'GENERATED' means locked but unpaid. 'PAID' means money was sent.")
    
    ledger_df = run_query("""
        SELECT ph.id, c.creator_handle, ph.period_start, ph.period_end, ph.net_payout_inr, ph.status, ph.transaction_reference
        FROM payout_history ph
        JOIN creators c ON ph.creator_id = c.id
        WHERE ph.status != 'CANCELLED'
        ORDER BY ph.created_at DESC
    """)
    
    if ledger_df.empty:
        st.info("No payouts generated yet.")
    else:
        display_ledger = ledger_df.copy()
        display_ledger['net_payout_inr'] = pd.to_numeric(display_ledger['net_payout_inr']) / 100.0
        st.dataframe(
            display_ledger,
            column_config={
                "id": None,
                "creator_handle": "Creator",
                "period_start": "Start Date",
                "period_end": "End Date",
                "net_payout_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
                "status": "Status",
                "transaction_reference": "UTR / Ref"
            },
            hide_index=True,
            width='stretch'
        )

    st.divider()

    # --- MARK AS PAID ---
    st.subheader("✍️ Update Payout Status (Mark as Paid)")
    st.info("Select a GENERATED payout, enter the UTR from your bank, and confirm. This will update the creator's ledger.")
    
    generated_payouts = run_query("""
        SELECT ph.id, c.creator_handle, ph.net_payout_inr, ph.period_start
        FROM payout_history ph JOIN creators c ON ph.creator_id = c.id
        WHERE ph.status = 'GENERATED'
    """)
    
    if generated_payouts.empty:
        st.info("No payouts are currently waiting to be marked as paid.")
    else:
        gen_options = {f"{row['creator_handle']} - ₹{float(row['net_payout_inr'])/100.0:,.2f} ({row['period_start']})": str(row['id']) for _, row in generated_payouts.iterrows()}
        sel_gen_name = st.selectbox("Select Payout to Mark as Paid", options=list(gen_options.keys()), key="mark_paid_select")
        sel_gen_id = gen_options[sel_gen_name]
        
        with st.form("mark_paid_form"):
            utr = st.text_input("Enter UTR / Transaction Ref", placeholder="e.g., UPI-616330527727")
            method = st.selectbox("Payment Method", ["UPI", "NEFT", "IMPS", "Bank Transfer", "RazorpayX"])
            if st.form_submit_button("✅ Confirm & Update Ledger", type="primary"):
                if not utr:
                    st.error("UTR is mandatory.")
                else:
                    if mark_as_paid(sel_gen_id, utr, method):
                        st.success("✅ Payout marked as PAID and ledger updated!")
                        st.rerun()
                    else:
                        st.error("Failed to update.")

    st.divider()

    # --- ROLLBACK ---
    st.subheader("🗑️ Rollback / Delete Payout (Emergency Use)")
    st.warning("Use this ONLY if you generated a payout by mistake and haven't sent the money yet.")
    
    if generated_payouts.empty:
        st.info("No generated payouts available to rollback.")
    else:
        rb_options = {f"{row['creator_handle']} - ₹{float(row['net_payout_inr'])/100.0:,.2f} ({row['period_start']})": str(row['id']) for _, row in generated_payouts.iterrows()}
        sel_rb_name = st.selectbox("Select Payout to Rollback", options=list(rb_options.keys()), key="rollback_select")
        sel_rb_id = rb_options[sel_rb_name]
        
        if st.button("🗑️ Cancel & Delete Payout", type="secondary"):
            if rollback_payout(sel_rb_id):
                st.success("✅ Payout cancelled and removed from queue.")
                st.rerun()
