import streamlit as st
import pandas as pd
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
st.caption("Process creator payouts, record UTRs, and view the permanent audit trail.")

tab_pending, tab_history = st.tabs(["🔄 Pending Payouts", "📜 Payout History"])

# ==============================================================================
# 2. TAB 1: PENDING PAYOUTS
# ==============================================================================
with tab_pending:
    st.subheader("Creators Ready for Payout")
    st.info("This list shows all active creators with a positive net balance. Financial details are optional but displayed if available.")

    pending_df = run_query("""
        SELECT 
            c.id, c.creator_handle, c.payout_rate,
            l.total_gross_inr, l.total_refunds_inr,
            f.upi_id, f.pan_number
        FROM creators c
        JOIN creator_ledger l ON c.id = l.creator_id
        LEFT JOIN creator_financials f ON c.id = f.creator_id
        WHERE c.status = 'ACTIVE' 
          AND (l.total_gross_inr - COALESCE(l.total_refunds_inr, 0)) > 0
        ORDER BY (l.total_gross_inr - COALESCE(l.total_refunds_inr, 0)) DESC
    """)

    if pending_df.empty:
        st.success("✅ All creators are fully paid out, or no one has pending balances!")
    else:
        # 🔥 FIX: Force numeric types to prevent TypeError from Decimal/None/str
        pending_df['payout_rate'] = pd.to_numeric(pending_df['payout_rate'], errors='coerce').fillna(0.0)
        pending_df['total_gross_inr'] = pd.to_numeric(pending_df['total_gross_inr'], errors='coerce').fillna(0)
        pending_df['total_refunds_inr'] = pd.to_numeric(pending_df['total_refunds_inr'], errors='coerce').fillna(0)

        # Create a copy for display purposes
        display_df = pending_df.copy()
        
        # Calculate net payout in INR for display
        display_df['net_payout_inr'] = ((display_df['total_gross_inr'] - display_df['total_refunds_inr']) * (display_df['payout_rate'] / 100.0)) / 100.0
        
        # Convert paise to INR for display columns
        display_df['gross_inr_display'] = display_df['total_gross_inr'] / 100.0
        display_df['refunds_inr_display'] = display_df['total_refunds_inr'] / 100.0
        
        display_df['upi_id'] = display_df['upi_id'].fillna("Not Provided")
        display_df['pan_number'] = display_df['pan_number'].fillna("Not Provided")
        
        st.dataframe(
            display_df[['creator_handle', 'gross_inr_display', 'refunds_inr_display', 'payout_rate', 'net_payout_inr', 'upi_id']],
            column_config={
                "creator_handle": "Creator",
                "gross_inr_display": st.column_config.NumberColumn("Gross (₹)", format="%.2f"),
                "refunds_inr_display": st.column_config.NumberColumn("Refunds (₹)", format="%.2f"),
                "payout_rate": "Rate (%)",
                "net_payout_inr": st.column_config.NumberColumn("Net Payout (₹)", format="%.2f"),
                "upi_id": "Destination UPI"
            },
            hide_index=True,
            width='stretch'
        )

        st.divider()
        st.subheader("📝 Process a Payout")
        
        # Dropdown to select who to pay (using original pending_df which is still in paise)
        payout_options = {f"{row['creator_handle']} (Owe: ₹{((row['total_gross_inr'] - row['total_refunds_inr']) * (row['payout_rate'] / 100.0)) / 100.0:,.2f})": row['id'] for _, row in pending_df.iterrows()}
        selected_payout_name = st.selectbox("Select Creator to Pay", options=list(payout_options.keys()))
        selected_payout_id = payout_options[selected_payout_name]
        
        # Get the specific row data from the ORIGINAL pending_df (still in paise)
        payout_row = pending_df[pending_df['id'] == selected_payout_id].iloc[0]
        
        gross_paise = int(payout_row['total_gross_inr'])
        refunds_paise = int(payout_row['total_refunds_inr'])
        rate = float(payout_row['payout_rate'])
        
        net_paise = int((gross_paise - refunds_paise) * (rate / 100.0))
        net_inr = net_paise / 100.0

        st.metric("Amount to Disburse", f"₹{net_inr:,.2f}")
        
        upi_display = payout_row['upi_id'] if pd.notna(payout_row['upi_id']) and payout_row['upi_id'] != "Not Provided" else "Not Provided"
        pan_display = payout_row['pan_number'] if pd.notna(payout_row['pan_number']) and payout_row['pan_number'] != "Not Provided" else "Not Provided"
        
        st.caption(f"Destination UPI: **{upi_display}** | PAN: **{pan_display}**")

        with st.form("payout_form"):
            ref = st.text_input("Transaction Reference / UTR Number", placeholder="e.g., UTR123456789")
            method = st.selectbox("Payment Method", ["UPI", "NEFT", "IMPS", "Bank Transfer", "RazorpayX"])
            notes = st.text_area("Notes (Optional)")
            
            submit_btn = st.form_submit_button("🔒 Confirm & Archive Payout", type="primary", width='stretch')
            
            if submit_btn:
                if not ref:
                    st.error("❌ Transaction Reference is mandatory for the audit trail.")
                else:
                    success = process_payout(
                        creator_id=selected_payout_id,
                        gross_inr=gross_paise,
                        refunds_inr=refunds_paise,
                        payout_rate=rate,
                        net_payout_inr=net_paise,
                        reference=ref,
                        method=method,
                        notes=notes
                    )
                    if success:
                        st.success(f"✅ ₹{net_inr:,.2f} paid to {selected_payout_name}. Ledger reset to zero!")
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
            ph.processed_at,
            ph.gross_inr,
            ph.refunds_inr,
            ph.payout_rate,
            ph.net_payout_inr,
            ph.transaction_reference,
            ph.payment_method,
            ph.status,
            ph.notes
        FROM payout_history ph
        JOIN creators c ON ph.creator_id = c.id
        ORDER BY ph.processed_at DESC
    """)
    
    if history_df.empty:
        st.info("No payouts have been processed yet.")
    else:
        # 🔥 FIX: Force numeric types for history too
        history_df['gross_inr'] = pd.to_numeric(history_df['gross_inr'], errors='coerce').fillna(0)
        history_df['refunds_inr'] = pd.to_numeric(history_df['refunds_inr'], errors='coerce').fillna(0)
        history_df['net_payout_inr'] = pd.to_numeric(history_df['net_payout_inr'], errors='coerce').fillna(0)
        history_df['payout_rate'] = pd.to_numeric(history_df['payout_rate'], errors='coerce').fillna(0.0)

        display_hist = history_df.copy()
        display_hist['processed_at'] = pd.to_datetime(display_hist['processed_at']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Convert paise to INR for display
        display_hist['gross_inr'] = display_hist['gross_inr'] / 100.0
        display_hist['refunds_inr'] = display_hist['refunds_inr'] / 100.0
        display_hist['net_payout_inr'] = display_hist['net_payout_inr'] / 100.0
        
        st.dataframe(
            display_hist,
            column_config={
                "creator_handle": "Creator",
                "processed_at": "Date Processed",
                "gross_inr": st.column_config.NumberColumn("Gross (₹)", format="%.2f"),
                "refunds_inr": st.column_config.NumberColumn("Refunds (₹)", format="%.2f"),
                "payout_rate": "Rate (%)",
                "net_payout_inr": st.column_config.NumberColumn("Net Paid (₹)", format="%.2f"),
                "transaction_reference": "UTR / Reference",
                "payment_method": "Method",
                "status": "Status",
                "notes": "Notes"
            },
            hide_index=True,
            width='stretch'
        )
