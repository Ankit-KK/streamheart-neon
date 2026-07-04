import streamlit as st
import pandas as pd
import requests
import time
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

st.title("🔄 Razorpay Sync & Data Management")
st.caption("Pull raw payment data from Razorpay and manage local database mappings.")

# ==============================================================================
# 2. CURRENT DATABASE STATS
# ==============================================================================
st.subheader("📊 Current Database Status")

stats_df = run_query("""
    SELECT 
        COUNT(*) as total, 
        COUNT(creator_id) as mapped, 
        COUNT(*) - COUNT(creator_id) as unmapped 
    FROM payments
""")

if not stats_df.empty:
    row = stats_df.iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Payments in DB", int(row['total']))
    m2.metric("Successfully Mapped", int(row['mapped']))
    m3.metric("Unmapped (Needs Review)", int(row['unmapped']))

st.divider()

# ==============================================================================
# 3. RAZORPAY SYNC ENGINE (Downloads new data)
# ==============================================================================
st.subheader("🚀 Razorpay Sync Engine (Download New Data)")
st.info("Fetches the latest payments from Razorpay. Processes 100 at a time using timestamps to bypass API limits.")

sync_clicked = st.button("🚀 Start Razorpay Sync", type="primary", width='stretch')

if sync_clicked:
    vercel_url = st.secrets.get("VERCEL_API_URL").rstrip("/")
    
    to_timestamp = None
    total_fetched = 0
    total_inserted = 0
    
    status_text = st.empty()
    
    while True:
        payload = {"to_timestamp": to_timestamp} if to_timestamp else {}
        status_text.text(f"🔄 Fetching batch... (Cursor: {to_timestamp or 'Start'})")
        
        try:
            resp = requests.post(f"{vercel_url}/api", json=payload, timeout=30)
            data = resp.json()
        except Exception as e:
            st.error(f"Network Error: {e}")
            break
            
        if not data.get("success"):
            st.error(f"Sync Error: {data.get('error')}")
            break
            
        metrics = data.get("metrics", {})
        fetched = metrics.get("fetched", 0)
        
        total_fetched += fetched
        total_inserted += metrics.get("inserted", 0)
        
        status_text.text(f"🔄 Syncing... (Fetched: {total_fetched} | Inserted: {total_inserted})")
        
        next_to = data.get("next_to")
        if not next_to or fetched == 0:
            break
            
        to_timestamp = next_to
        time.sleep(0.5)

    st.success(f"✅ Razorpay Sync Complete! Fetched {total_fetched} payments.")
    st.balloons()
    st.rerun()

st.divider()

# ==============================================================================
# 4. LOCAL RE-MAP ENGINE (Links existing unmapped data)
# ==============================================================================
st.subheader("🔄 Local Re-map Engine (Link Existing Data)")
st.info("If you added a new creator *after* running the Razorpay sync, their past payments are sitting in the database as 'Unmapped'. Click below to scan your database and link them automatically.")

remap_clicked = st.button("🔗 Re-map Unmapped Payments to Creators", type="secondary", width='stretch')

if remap_clicked:
    status_text = st.empty()
    status_text.text("🔍 Scanning database for unmapped payments...")
    
    # 1. Get all unmapped payments that have a receipt
    unmapped_df = run_query("""
        SELECT id, receipt 
        FROM payments 
        WHERE creator_id IS NULL AND receipt IS NOT NULL AND receipt != ''
    """)
    
    # 2. Get all active creators
    creators_df = run_query("SELECT id, creator_code FROM creators WHERE status = 'ACTIVE'")
    
    if unmapped_df.empty or creators_df.empty:
        status_text.text("✅ Nothing to re-map! All payments are mapped, or no creators exist.")
    else:
        # Create a mapping dictionary for fast lookup
        creators_map = {row['creator_code']: str(row['id']) for _, row in creators_df.iterrows()}
        
        mapped_count = 0
        
        # 3. Loop through unmapped and find matches
        for _, row in unmapped_df.iterrows():
            receipt = row['receipt']
            matched_creator_id = None
            
            # Check for exact match or prefix match (e.g., receipt "rvs_123" matches code "rvs")
            for code, cid in creators_map.items():
                if receipt == code or receipt.startswith(f"{code}_"):
                    matched_creator_id = cid
                    break
                    
            # 4. If matched, update the database!
            if matched_creator_id:
                run_query("""
                    UPDATE payments 
                    SET creator_id = %s 
                    WHERE id = %s
                """, (matched_creator_id, row['id']))
                mapped_count += 1
                
        status_text.text(f"✅ Re-map Complete! Successfully linked {mapped_count} previously unmapped payments.")
        st.info("🪄 The database triggers have automatically updated the `creator_ledger` with their new totals!")
        st.balloons()
        st.rerun()

st.divider()

# ==============================================================================
# 5. RECENT PAYMENTS TABLE
# ==============================================================================
st.subheader("💳 Latest Synced Payments")

payments_df = run_query("""
    SELECT p.payment_id, p.created_at, p.original_currency, p.amount_inr, p.receipt, c.creator_handle
    FROM payments p LEFT JOIN creators c ON p.creator_id = c.id
    ORDER BY p.created_at DESC LIMIT 20
""")

if not payments_df.empty:
    display_df = payments_df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M')
    display_df['amount_inr'] = display_df['amount_inr'] / 100.0
    
    st.dataframe(display_df, hide_index=True, width='stretch')
else:
    st.warning("No payments found yet.")
