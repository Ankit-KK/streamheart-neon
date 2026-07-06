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
st.caption("Calculate creator earnings, preview bulk liabilities, lock records, and reconcile.")

tab_generate, tab_reconcile = st.tabs(["💰 Generate Payouts", "📜 Reconciliation & History"])

# ==============================================================================
# 2. TAB 1: GENERATE PAYOUTS
# ==============================================================================
with tab_generate:
    st.subheader("📅 Select Payout Period")
    
    # Force "today" to be calculated in IST
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

        period_df = run_query("""
            SELECT 
                SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END) as period_gross,
                SUM(CASE WHEN status = 'refunded' THEN amount_inr ELSE 0 END) as period_refunds
            FROM payments
            WHERE creator_id = %s AND (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
        """, (selected_id, start_date, end_date))

        # 🔥 BULLETPROOF EXTRACTION (Prevents NaN to int ValueError)
        raw_gross = period_df.iloc[0]['period_gross'] if not period_df.empty else 0
        p_gross = int(raw_gross) if pd.notna(raw_gross) else 0
        
        raw_refunds = period_df.iloc[0]['period_refunds'] if not period_df.empty else 0
        p_refunds = int(raw_refunds) if pd.notna(raw_refunds) else 0
        
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

    # --- BULK PAYOUT CALCULATION & PREVIEW ---
    st.subheader("⚡ Bulk Payouts (Calculate & Preview)")
    st.info("Calculate what is owed to ALL active creators for this period. Review the numbers before locking them.")
    
    if "show_bulk_preview" not in st.session_state:
        st.session_state.show_bulk_preview = False
        
    # Reset preview if date range changes
    if "last_bulk_dates" not in st.session_state:
        st.session_state.last_bulk_dates = (start_date, end_date)
    if st.session_state.last_bulk_dates != (start_date, end_date):
        st.session_state.last_bulk_dates = (start_date, end_date)
        st.session_state.show_bulk_preview = False

    if not st.session_state.show_bulk_preview:
        if st.button("🧮 Calculate All Payouts for Period", type="secondary"):
            st.session_state.show_bulk_preview = True
            st.rerun()
    else:
        # 1. Run the optimized bulk calculation query
        bulk_calc_df = run_query("""
            SELECT 
                c.id, c.creator_handle, c.payout_rate,
                COALESCE(SUM(CASE WHEN p.status = 'captured' THEN p.amount_inr ELSE 0 END), 0) as gross_paise,
                COALESCE(SUM(CASE WHEN p.status = 'refunded' THEN p.amount_inr ELSE 0 END), 0) as refunds_paise
            FROM creators c
            LEFT JOIN payments p ON c.id = p.creator_id 
                AND (p.created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
            WHERE c.status = 'ACTIVE'
            GROUP BY c.id, c.creator_handle, c.payout_rate
        """, (start_date, end_date))
        
        if bulk_calc_df.empty:
            st.warning("No active creators found.")
        else:
            # 2. Process data in Python
            display_bulk = bulk_calc_df.copy()
            display_bulk['gross_paise'] = pd.to_numeric(display_bulk['gross_paise'], errors='coerce').fillna(0).astype(int)
            display_bulk['refunds_paise'] = pd.to_numeric(display_bulk['refunds_paise'], errors='coerce').fillna(0).astype(int)
            display_bulk['payout_rate'] = pd.to_numeric(display_bulk['payout_rate'], errors='coerce').fillna(0.0)
            
            # Calculate Net Payout
            display_bulk['net_paise'] = ((display_bulk['gross_paise'] - display_bulk['refunds_paise']) * (display_bulk['payout_rate'] / 100.0)).astype(int)
            
            # Filter out creators with 0 or negative net payout
            display_bulk = display_bulk[display_bulk['net_paise'] > 0]
            
            if display_bulk.empty:
                st.info("✅ No creators have a positive net balance for this period.")
            else:
                # Convert to INR for display
                display_bulk['gross_inr'] = display_bulk['gross_paise'] / 100.0
                display_bulk['refunds_inr'] = display_bulk['refunds_paise'] / 100.0
                display_bulk['net_inr'] = display_bulk['net_paise'] / 100.0
                
                # 3. Show Grand Total
                grand_total = display_bulk['net_inr'].sum()
                st.metric("💰 Grand Total Liability (Cash needed to disburse)", f"₹{grand_total:,.2f}")
                
                # 4. Show Preview Table
                st.dataframe(
                    display_bulk[['creator_handle', 'gross_inr', 'refunds_inr', 'payout_rate', 'net_inr']],
                    column_config={
                        "creator_handle": "Creator",
                        "gross_inr": st.column_config.NumberColumn("Gross (₹)", format="%.2f"),
                        "refunds_inr": st.column_config.NumberColumn("Refunds (₹)", format="%.2f"),
                        "payout_rate": "Rate (%)",
                        "net_inr": st.column_config.NumberColumn("Net Payout (₹)", format="%.2f")
                    },
                    hide_index=True,
                    width='stretch'
                )
                
                # 5. Lock Button (This is the "make data for all creators at one go" feature)
                st.divider()
                st.warning(f"⚠️ You are about to lock **{len(display_bulk)}** payouts totaling **₹{grand_total:,.2f}**.")
                
                if st.button("🔒 Generate & Lock All Previewed Payouts", type="primary"):
                    locked_count = 0
                    skipped_count = 0
                    
                    for _, row in display_bulk.iterrows():
                        res = generate_payout(
                            creator_id=str(row['id']), 
                            gross_inr=int(row['gross_paise']), 
                            refunds_inr=int(row['refunds_paise']), 
                            payout_rate=float(row['payout_rate']), 
                            net_payout_inr=int(row['net_paise']), 
                            period_start=start_date, 
                            period_end=end_date
                        )
                        if res:
                            locked_count += 1
                        else:
                            skipped_count += 1
                            
                    st.session_state.show_bulk_preview = False
                    st.success(f"✅ Bulk Lock Complete! {locked_count} payouts locked. {skipped_count} skipped (already existed).")
                    st.balloons()
                    st.rerun()

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
