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

st.title("🔄 Razorpay Sync Engine")
st.caption("Pull raw payment data from Razorpay and map it to your creators automatically.")

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
# 3. SYNC ENGINE
# ==============================================================================
st.subheader("🚀 Sync Engine")
sync_clicked = st.button("🚀 Start Full Sync", type="primary", width='stretch')

if sync_clicked:
    vercel_url = st.secrets.get("VERCEL_API_URL").rstrip("/")
    
    skip = 0
    total_fetched = 0
    total_inserted = 0
    total_unmapped = 0
    
    status_text = st.empty()
    # 🔥 NEW: Debug log to see exactly what the API is returning
    debug_log = st.expander("🔍 Debug Logs (Click to expand if sync stops unexpectedly)")
    
    while True:
        payload = {"skip": skip}
        status_text.text(f"🔄 Fetching batch starting at skip={skip}...")
        
        try:
            resp = requests.post(f"{vercel_url}/api", json=payload, timeout=30)
            data = resp.json()
        except Exception as e:
            with debug_log: st.error(f"Network Error on skip={skip}: {e}")
            break
            
        # 🔥 LOG THE RAW RESPONSE
        with debug_log:
            st.write(f"**Batch skip={skip} Raw Response:**", data)
            
        if not data.get("success"):
            with debug_log: st.error(f"Sync Error: {data.get('error')}")
            break
            
        metrics = data.get("metrics", {})
        fetched = metrics.get("fetched", 0)
        
        total_fetched += fetched
        total_inserted += metrics.get("inserted", 0)
        total_unmapped += metrics.get("unmapped", 0)
        
        status_text.text(f"🔄 Syncing... (Batch {skip//100 + 1} | Fetched: {total_fetched} | Inserted: {total_inserted})")
        
        next_skip = data.get("next_skip")
        
        # If no next_skip, or we fetched 0 items, we are at the end
        if not next_skip or fetched == 0:
            break
            
        skip = next_skip
        time.sleep(0.5) # Small delay to respect API rate limits

    st.success(f"✅ Sync Complete! Total Fetched: {total_fetched} | Inserted: {total_inserted}")
    st.balloons()
    st.rerun()

st.divider()

# ==============================================================================
# 4. RECENT PAYMENTS TABLE
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
