import streamlit as st
import pandas as pd
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

st.set_page_config(page_title="Financials", layout="wide")
st.title("📊 StreamHeart Financials & Balance Sheet")
st.caption("Comprehensive P&L, Balance Sheet, and Expense tracking for StreamHeart Private Limited.")

# ==============================================================================
# 2. FINANCIAL PERIOD SELECTOR
# ==============================================================================
st.subheader("📅 Select Financial Period")

# Force IST timezone
ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = datetime.datetime.now(ist_tz).date()
current_fy_start = datetime.date(today.year, 4, 1) if today.month >= 4 else datetime.date(today.year - 1, 4, 1)

col1, col2 = st.columns(2)
with col1:
    start_date = st.date_input("Start Date", value=datetime.date(2026, 4, 1))
with col2:
    end_date = st.date_input("End Date", value=today)

# Quick select buttons
col_a, col_b, col_c, col_d = st.columns(4)
with col_a:
    if st.button("Current Month", use_container_width=True):
        start_date = today.replace(day=1)
        end_date = today
with col_b:
    if st.button("Last Month", use_container_width=True):
        first_day = today.replace(day=1)
        last_month = first_day - datetime.timedelta(days=1)
        start_date = last_month.replace(day=1)
        end_date = last_month
with col_c:
    if st.button("Current FY (Apr-Mar)", use_container_width=True):
        start_date = current_fy_start
        end_date = today
with col_d:
    if st.button("All Time (Lifetime)", use_container_width=True):
        start_date = datetime.date(2024, 1, 1)
        end_date = today

st.info(f"🕒 Analyzing period: {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')} (IST)")

st.divider()

# ==============================================================================
# 3. 🔥 CORE MATH ENGINE
# ==============================================================================
# A. Total Money Collected
gross_df = run_query("""
    SELECT 
        COUNT(*) as total_transactions,
        COALESCE(SUM(CASE WHEN status = 'captured' THEN amount_inr ELSE 0 END), 0) as total_gross_paise,
        COALESCE(SUM(CASE WHEN status = 'captured' THEN fee_inr ELSE 0 END), 0) as total_fees_paise,
        COALESCE(SUM(CASE WHEN status = 'captured' THEN tax_inr ELSE 0 END), 0) as total_tax_paise
    FROM payments
    WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date BETWEEN %s AND %s
""", (start_date, end_date))

total_gross_paise = int(pd.to_numeric(gross_df.iloc[0]['total_gross_paise'], errors='coerce') or 0)
total_fees_paise = int(pd.to_numeric(gross_df.iloc[0]['total_fees_paise'], errors='coerce') or 0)

# B. Total Committed to Creators
creator_payouts_df = run_query("""
    SELECT COALESCE(SUM(net_payout_inr), 0) as total_committed_paise
    FROM payout_history
    WHERE status IN ('PAID', 'GENERATED')
      AND (
          (status = 'PAID' AND processed_at >= %s AND processed_at <= %s)
          OR
          (status = 'GENERATED' AND period_start >= %s AND period_end <= %s)
      )
""", (start_date, end_date, start_date, end_date))

total_creator_payout_paise = int(pd.to_numeric(creator_payouts_df.iloc[0]['total_committed_paise'], errors='coerce') or 0)

# C. Total Company Expenses
expenses_df = run_query("""
    SELECT COALESCE(SUM(amount_inr), 0) as total_expenses_paise
    FROM company_expenses
    WHERE expense_date BETWEEN %s AND %s
""", (start_date, end_date))

total_expenses_paise = int(pd.to_numeric(expenses_df.iloc[0]['total_expenses_paise'], errors='coerce') or 0)

# D. Calculate All Metrics
total_gross_inr = total_gross_paise / 100.0
total_creator_payout_inr = total_creator_payout_paise / 100.0
total_razorpay_fees_inr = total_fees_paise / 100.0
total_expenses_inr = total_expenses_paise / 100.0

# 🔥 NEW: Platform Cut (what you earned from the 11% split)
platform_cut_inr = total_gross_inr - total_creator_payout_inr

# Calculate platform cut percentage
if total_gross_inr > 0:
    platform_cut_percentage = (platform_cut_inr / total_gross_inr) * 100
else:
    platform_cut_percentage = 0

# Operating Profit (after Razorpay fees)
operating_profit_inr = platform_cut_inr - total_razorpay_fees_inr

# Final Net Profit (after all expenses)
final_net_profit_inr = operating_profit_inr - total_expenses_inr

# ==============================================================================
# 4. TABS NAVIGATION
# ==============================================================================
tab_options = ["💰 Simple Breakdown", "📊 Dashboard", "📑 Formal Statements", "💸 Expenses", "⬇️ CA Export"]

if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

active_tab = st.radio(
    "Navigation",
    tab_options,
    horizontal=True,
    label_visibility="collapsed",
    index=st.session_state.active_tab
)
st.session_state.active_tab = tab_options.index(active_tab)

st.divider()

# ==============================================================================
# 5. TAB 1: SIMPLE BREAKDOWN (WITH PLATFORM CUT)
# ==============================================================================
if active_tab == "💰 Simple Breakdown":
    st.subheader("💰 StreamHeart's Take-Home Profit Calculator")
    
    breakdown_data = {
        "Step": [
            "1️⃣ Total Money Collected (Successful Donations)",
            "2️⃣ Less: Paid to Creators (Their 89% Share)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "💎 PLATFORM CUT (Your 11% Earned)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "3️⃣ Less: Paid to Razorpay (Gateway Fees + GST)",
            "4️⃣ Less: Company Bills (Logged Expenses)",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🏆 StreamHeart's Final Take-Home Profit"
        ],
        "Amount (₹)": [
            f"₹{total_gross_inr:,.2f}",
            f"- ₹{total_creator_payout_inr:,.2f}",
            "",
            f"₹{platform_cut_inr:,.2f} ({platform_cut_percentage:.1f}%)",
            "",
            f"- ₹{total_razorpay_fees_inr:,.2f}",
            f"- ₹{total_expenses_inr:,.2f}",
            "",
            f"₹{final_net_profit_inr:,.2f}"
        ]
    }
    
    st.table(pd.DataFrame(breakdown_data))
    
    st.divider()
    
    # Visual breakdown
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("💎 Platform Cut", f"₹{platform_cut_inr:,.2f}", f"{platform_cut_percentage:.1f}% of Gross")
    with col2:
        st.metric("💸 Total Expenses", f"₹{total_razorpay_fees_inr + total_expenses_inr:,.2f}", "Razorpay + Bills")
    with col3:
        if final_net_profit_inr >= 0:
            st.metric("🏆 Final Profit", f"₹{final_net_profit_inr:,.2f}", "After All Expenses")
        else:
            st.metric("📉 Net Loss", f"₹{abs(final_net_profit_inr):,.2f}", "Expenses > Cut")
    
    st.divider()
    st.info(f"""
    💡 **How to read this:** 
    
    Out of **₹{total_gross_inr:,.2f}** collected from viewers:
    - You paid creators **₹{total_creator_payout_inr:,.2f}** (their share)
    - **Your platform earned ₹{platform_cut_inr:,.2f}** ({platform_cut_percentage:.1f}% cut)
    
    From that ₹{platform_cut_inr:,.2f} cut:
    - Razorpay took **₹{total_razorpay_fees_inr:,.2f}** in fees
    - Your company spent **₹{total_expenses_inr:,.2f}** on bills
    
    **Final Result:** {'Profit of' if final_net_profit_inr >= 0 else 'Loss of'} **₹{abs(final_net_profit_inr):,.2f}**
    """)

# ==============================================================================
# 6. TAB 2: DASHBOARD
# ==============================================================================
elif active_tab == "📊 Dashboard":
    st.subheader("📈 Executive Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Gross Revenue", f"₹{total_gross_inr:,.2f}")
    col2.metric("💎 Platform Cut", f"₹{platform_cut_inr:,.2f}", f"{platform_cut_percentage:.1f}%")
    col3.metric("Total Expenses", f"₹{total_razorpay_fees_inr + total_expenses_inr:,.2f}")
    col4.metric("🏆 Final Profit", f"₹{final_net_profit_inr:,.2f}")
    
    st.divider()
    st.subheader("💰 Revenue Distribution")
    
    chart_data = pd.DataFrame({
        'Category': ['Creator Payouts (89%)', 'Platform Cut (11%)', 'Razorpay Fees', 'Company Expenses', 'Net Profit/Loss'],
        'Amount': [total_creator_payout_inr, platform_cut_inr, total_razorpay_fees_inr, total_expenses_inr, abs(final_net_profit_inr)]
    })
    
    if total_gross_inr > 0:
        chart_data['Percentage'] = (chart_data['Amount'] / total_gross_inr * 100).round(2)
    else:
        chart_data['Percentage'] = 0.0
    
    import altair as alt
    chart = alt.Chart(chart_data).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="Amount", type="quantitative"),
        color=alt.Color(field="Category", type="nominal", 
                       scale=alt.Scale(domain=['Creator Payouts (89%)', 'Platform Cut (11%)', 'Razorpay Fees', 'Company Expenses', 'Net Profit/Loss'],
                                      range=['#94a3b8', '#10b981', '#f59e0b', '#ef4444', '#3b82f6'])),
        tooltip=['Category', alt.Tooltip('Amount:Q', format='₹,.2f'), 'Percentage']
    ).properties(width=500, height=500, title="Where Did the Money Go?")
    
    st.altair_chart(chart, use_container_width=True)
    
    st.divider()
    st.subheader("📊 Detailed Breakdown")
    
    detail_df = pd.DataFrame({
        'Metric': [
            'Total Gross Collected', 
            'Creator Payouts (89%)', 
            '💎 Platform Cut (11%)',
            'Razorpay Fees', 
            'Company Expenses', 
            '🏆 Final Profit/Loss'
        ],
        'Amount (₹)': [
            total_gross_inr, 
            total_creator_payout_inr, 
            platform_cut_inr,
            total_razorpay_fees_inr, 
            total_expenses_inr, 
            final_net_profit_inr
        ],
        '% of Gross': [
            '100%', 
            f"{(total_creator_payout_inr/total_gross_inr*100) if total_gross_inr > 0 else 0:.1f}%",
            f"{platform_cut_percentage:.1f}%",
            f"{(total_razorpay_fees_inr/total_gross_inr*100) if total_gross_inr > 0 else 0:.1f}%",
            f"{(total_expenses_inr/total_gross_inr*100) if total_gross_inr > 0 else 0:.1f}%",
            f"{(final_net_profit_inr/total_gross_inr*100) if total_gross_inr > 0 else 0:.1f}%"
        ]
    })
    
    st.dataframe(detail_df, use_container_width=True, hide_index=True)

# ==============================================================================
# 7. TAB 3: FORMAL STATEMENTS
# ==============================================================================
elif active_tab == "📑 Formal Statements":
    st.subheader("📑 Formal Statements")
    st.info("🚧 This tab is under construction. We'll build formal P&L and Balance Sheet statements!")

# ==============================================================================
# 8. TAB 4: EXPENSES
# ==============================================================================
elif active_tab == "💸 Expenses":
    st.subheader("💸 Manage Business Expenses")
    st.info("Log your company expenses (Server costs, Domain renewals, Software subscriptions, etc.)")
    
    if 'expense_form_key' not in st.session_state:
        st.session_state.expense_form_key = 0
    if 'expense_success_msg' not in st.session_state:
        st.session_state.expense_success_msg = ""

    if st.session_state.expense_success_msg:
        st.success(st.session_state.expense_success_msg)
        st.session_state.expense_success_msg = ""

    with st.form(f"add_expense_form_{st.session_state.expense_form_key}"):
        col_e1, col_e2, col_e3 = st.columns(3)
        
        with col_e1:
            expense_date = st.date_input("Date", value=today)
            category = st.selectbox("Category", [
                "Server/Hosting", "Domain/SSL", "Software/SaaS", "Payment Gateway Fees",
                "Legal/Compliance", "Marketing/Ads", "Office/Equipment", 
                "Professional Services", "Bank Charges", "Other"
            ])
        
        with col_e2:
            amount_inr = st.number_input("Amount (INR ₹)", min_value=0.01, step=0.01, format="%.2f")
        
        with col_e3:
            description = st.text_input("Description (e.g., Vercel Pro Plan)")
        
        receipt_url = st.text_input("Receipt URL (Optional)", placeholder="https://...")
        
        submitted = st.form_submit_button("💾 Add Expense", type="primary", use_container_width=True)
        
        if submitted:
            if not description:
                st.error("❌ Description is required.")
            else:
                amount_paise = int(amount_inr * 100)
                try:
                    run_query("""
                        INSERT INTO company_expenses (expense_date, category, amount_inr, description, receipt_url)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (expense_date, category, amount_paise, description, receipt_url if receipt_url else None))
                    
                    st.session_state.expense_success_msg = f"✅ Expense of ₹{amount_inr:,.2f} added successfully!"
                    st.session_state.expense_form_key += 1
                except Exception as e:
                    st.error(f"❌ Failed to add expense: {e}")
    
    st.divider()
    
    st.subheader("📋 Expense Ledger")
    
    expenses_ledger_df = run_query("""
        SELECT id, expense_date, category, amount_inr, description, receipt_url, created_at
        FROM company_expenses
        WHERE expense_date BETWEEN %s AND %s
        ORDER BY expense_date DESC
    """, (start_date, end_date))
    
    if expenses_ledger_df.empty:
        st.info("No expenses logged for this period.")
    else:
        display_expenses = expenses_ledger_df.copy()
        display_expenses['amount_inr'] = pd.to_numeric(display_expenses['amount_inr'], errors='coerce') / 100.0
        display_expenses['expense_date'] = pd.to_datetime(display_expenses['expense_date']).dt.strftime('%Y-%m-%d')
        
        total_expenses_display = display_expenses['amount_inr'].sum()
        st.metric("💸 Total Expenses for Period", f"₹{total_expenses_display:,.2f}")
        
        st.dataframe(
            display_expenses[['expense_date', 'category', 'description', 'amount_inr']],
            column_config={
                "expense_date": "Date",
                "category": "Category",
                "description": "Description",
                "amount_inr": st.column_config.NumberColumn("Amount (₹)", format="%.2f")
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.divider()
        st.subheader("🗑️ Delete Expense")
        
        expense_options = {f"{row['expense_date']} - {row['description']} (₹{row['amount_inr']:,.2f})": str(row['id']) 
                          for _, row in display_expenses.iterrows()}
        
        if expense_options:
            selected_expense = st.selectbox("Select expense to delete", options=list(expense_options.keys()))
            
            if st.button("🗑️ Delete Selected Expense", type="secondary"):
                expense_id = expense_options[selected_expense]
                run_query("DELETE FROM company_expenses WHERE id = %s", (expense_id,))
                st.success("✅ Expense deleted successfully!")

# ==============================================================================
# 9. TAB 5: CA EXPORT
# ==============================================================================
elif active_tab == "⬇️ CA Export":
    st.subheader("⬇️ CA Export")
    st.info("🚧 This tab is under construction. We'll build export functionality for your Chartered Accountant!")
