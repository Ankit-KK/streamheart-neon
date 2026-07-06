import streamlit as st
import pandas as pd
import requests
import time
import datetime
from utils.db import run_query
from utils.auth import verify_session

# ==============================================================================
# 1. SECURITY CHECK
# ==============================================================================
session_token = st.session_state.get("session_token")
current_user = verify_session(session_token) if session_token else None
if not current_user:
    st.error("❌ Access Denied.")
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
# 3. SYNC ENGINE (TWO MODES)
# ==============================================================================
st.subheader("🚀 Sync Engine")

col1, col2 = st.columns(2)
with col1:
    sync_new_clicked = st.button("🚀 Sync New Payments Only (Recommended)", type="primary", width='stretch')
with col2:
    sync_all_clicked = st.button("⚠️ Full Historical Sync (Fetch All)", type="secondary", width='stretch')

# --- MODE A: SYNC NEW ---
if sync_new_clicked:
    vercel_url = st.secrets.get("VERCEL_API_URL").rstrip("/")
    
    # 1. Get MAX created_at from DB
    max_time_df = run_query("SELECT MAX(created_at) as max_time FROM payments")
    
    if max_time_df.empty or pd.isna(max_time_df.iloc[0]['max_time']):
        st.error("❌ Database is empty. Please run 'Full Historical Sync' first to establish a baseline.")
        st.stop()
        
    max_time_utc = pd.to_datetime(max_time_df.iloc[0]['max_time'])
    
    # Convert to IST for display
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    max_time_ist = max_time_utc.replace(tzinfo=datetime.timezone.utc).astimezone(ist_tz)
    
    st.info(f"🕒 Resuming sync from: **{max_time_ist.strftime('%Y-%m-%d %H:%M:%S')}** (IST)")
    
    # API needs Unix timestamp (UTC)
    from_timestamp = int(max_time_utc.timestamp())
    to_timestamp = None
    
    total_fetched = 0
    total_inserted = 0
    status_text = st.empty()
    
    while True:
        payload = {"from_timestamp": from_timestamp}
        if to_timestamp:
            payload["to_timestamp"] = to_timestamp
            
        status_text.text(f"🔄 Fetching batch...")
        
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

    st.success(f"✅ Sync Complete! Fetched {total_fetched} new payments.")
    st.balloons()
    st.rerun()

# --- MODE B: FULL SYNC ---
if sync_all_clicked:
    vercel_url = st.secrets.get("VERCEL_API_URL").rstrip("/")
    st.warning("⚠️ Starting Full Historical Sync. This will fetch ALL payments from the beginning.")
    
    from_timestamp = None
    to_timestamp = None
    
    total_fetched = 0
    total_inserted = 0
    status_text = st.empty()
    
    while True:
        payload = {}
        if to_timestamp:
            payload["to_timestamp"] = to_timestamp
            
        status_text.text(f"🔄 Fetching batch...")
        
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

    st.success(f"✅ Full Sync Complete! Fetched {total_fetched} payments.")
    st.balloons()
    st.rerun()

st.divider()

# ==============================================================================
# 4. RECENT PAYMENTS TABLE (WITH IST FIX)
# ==============================================================================
st.subheader("💳 Latest Synced Payments (IST)")

payments_df = run_query("""
    SELECT p.payment_id, (p.created_at AT TIME ZONE 'Asia/Kolkata') as created_at, 
           p.original_currency, p.amount_inr, p.status, p.receipt, c.creator_handle
    FROM payments p LEFT JOIN creators c ON p.creator_id = c.id
    ORDER BY p.created_at DESC LIMIT 20
""")

if not payments_df.empty:
    display_df = payments_df.copy()
    display_df['created_at'] = pd.to_datetime(display_df['created_at']).dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['amount_inr'] = display_df['amount_inr'] / 100.0
    
    st.dataframe(
        display_df,
        column_config={
            "payment_id": st.column_config.TextColumn("Payment ID", width="small"),
            "created_at": st.column_config.TextColumn("Date (IST)", width="small"),
            "original_currency": st.column_config.TextColumn("Currency", width="small"),
            "amount_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "receipt": st.column_config.TextColumn("Razorpay Receipt", width="medium"),
            "creator_handle": st.column_config.TextColumn("Mapped Handle", width="medium")
        },
        hide_index=True,
        width='stretch'
    )
else:
    st.warning("No payments found yet.")

st.divider()

# ==============================================================================
# 🔥 MOVED TO BOTTOM: MISSING CREATOR CODES
# ==============================================================================
st.subheader("🚨 Missing Creator Codes")
st.info("These are the Unique Codes found in Razorpay receipts that do not match any creator in your database. Add these creators in the '1_Creators' page to map their past payments.")

missing_codes_df = run_query("""
    SELECT DISTINCT creator_code_attempted 
    FROM payments 
    WHERE creator_id IS NULL AND creator_code_attempted IS NOT NULL
    ORDER BY creator_code_attempted
""")

if missing_codes_df.empty:
    st.success("✅ No missing creator codes! All payments are perfectly mapped.")
else:
    st.warning(f"⚠️ Found **{len(missing_codes_df)}** missing creator codes. Please add them to your database.")
    
    display_codes = missing_codes_df.copy()
    st.dataframe(
        display_codes,
        column_config={
            "creator_code_attempted": st.column_config.TextColumn("Missing Unique Code", width="medium")
        },
        hide_index=True,
        width='stretch'
    )
