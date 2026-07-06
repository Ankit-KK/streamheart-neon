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
# Calculate all financial metrics for the selected period

# A. Total Money Collected (Successful Razorpay Payments)
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
total_tax_paise = int(pd.to_numeric(gross_df.iloc[0]['total_tax_paise'], errors='coerce') or 0)

# B. Total Paid to Creators (from payout_history - only PAID status)
payouts_df = run_query("""
    SELECT COALESCE(SUM(net_payout_inr), 0) as total_paid_paise
    FROM payout_history
    WHERE status = 'PAID'
      AND period_start >= %s 
      AND period_end <= %s
""", (start_date, end_date))

total_creator_payout_paise = int(pd.to_numeric(payouts_df.iloc[0]['total_paid_paise'], errors='coerce') or 0)

# C. Total Company Expenses (manual expenses)
expenses_df = run_query("""
    SELECT COALESCE(SUM(amount_inr), 0) as total_expenses_paise
    FROM company_expenses
    WHERE expense_date BETWEEN %s AND %s
""", (start_date, end_date))

total_expenses_paise = int(pd.to_numeric(expenses_df.iloc[0]['total_expenses_paise'], errors='coerce') or 0)

# D. Calculate Final Profit
total_gross_inr = total_gross_paise / 100.0
total_creator_payout_inr = total_creator_payout_paise / 100.0
total_razorpay_fees_inr = total_fees_paise / 100.0
total_expenses_inr = total_expenses_paise / 100.0

# Operating Profit (EBITDA) = Gross - Creator Payouts - Razorpay Fees
operating_profit_inr = total_gross_inr - total_creator_payout_inr - total_razorpay_fees_inr

# Final Net Profit = Operating Profit - Company Expenses
final_net_profit_inr = operating_profit_inr - total_expenses_inr

# ==============================================================================
# 4. TABS NAVIGATION
# ==============================================================================
tab1, tab2, tab3, tab_expenses, tab5 = st.tabs([
    "💰 Simple Breakdown",
    "📊 Dashboard", 
    "📑 Formal Statements",
    "💸 Expenses",
    "⬇️ CA Export"
])

# ==============================================================================
# 5. TAB 1: SIMPLE BREAKDOWN (Take-Home Profit Calculator)
# ==============================================================================
with tab1:
    st.subheader("💰 StreamHeart's Take-Home Profit Calculator")
    
    # Create the breakdown table
    breakdown_data = {
        "Step": [
            "1️⃣ Total Money Collected (Successful Donations)",
            "2️⃣ Less: Paid to Creators (Their 89%/90% Share)",
            "3️⃣ Less: Paid to Razorpay (Gateway Fees + GST)",
            "4️⃣ Less: Company Bills (Logged Expenses)",
            "🏆 StreamHeart's Final Take-Home Profit"
        ],
        "Amount (₹)": [
            f"₹{total_gross_inr:,.2f}",
            f"- ₹{total_creator_payout_inr:,.2f}",
            f"- ₹{total_razorpay_fees_inr:,.2f}",
            f"- ₹{total_expenses_inr:,.2f}",
            f"₹{final_net_profit_inr:,.2f}"
        ]
    }
    
    breakdown_df = pd.DataFrame(breakdown_data)
    st.table(breakdown_df)
    
    # Explanation box
    st.divider()
    st.info(f"""
    💡 **How to read this:** Out of the **₹{total_gross_inr:,.2f}** that successfully hit your bank account from viewers, 
    you paid your creators and Razorpay their dues. After subtracting your company's manual bills (**₹{total_expenses_inr:,.2f}**), 
    StreamHeart Private Limited is left with exactly **₹{final_net_profit_inr:,.2f}** in pure profit.
    """)

# ==============================================================================
# 6. TAB 2: DASHBOARD (Executive Summary + Donut Chart)
# ==============================================================================
with tab2:
    st.subheader("📈 Executive Summary")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Successful Revenue (GMV)", f"₹{total_gross_inr:,.2f}")
    col2.metric("Operating Profit (EBITDA)", f"₹{operating_profit_inr:,.2f}")
    col3.metric("🔥 Final Net Profit", f"₹{final_net_profit_inr:,.2f}")
    
    st.divider()
    
    st.subheader("Cash Outflow & Revenue Distribution")
    
    # Prepare data for donut chart
    chart_data = pd.DataFrame({
        'Category': ['Creator Payouts (COGS)', 'Gateway Fees', 'Business Expenses', 'Net Profit'],
        'Amount': [total_creator_payout_inr, total_razorpay_fees_inr, total_expenses_inr, final_net_profit_inr]
    })
    
    # Calculate percentages
    chart_data['Percentage'] = (chart_data['Amount'] / total_gross_inr * 100).round(2)
    
    # Display donut chart using Altair
    import altair as alt
    
    chart = alt.Chart(chart_data).mark_arc(innerRadius=50).encode(
        theta=alt.Theta(field="Amount", type="quantitative"),
        color=alt.Color(field="Category", type="nominal", 
                       scale=alt.Scale(domain=['Creator Payouts (COGS)', 'Gateway Fees', 'Business Expenses', 'Net Profit'],
                                      range=['#1e3a8a', '#3b82f6', '#60a5fa', '#10b981'])),
        tooltip=['Category', alt.Tooltip('Amount:Q', format='₹,.2f'), 'Percentage']
    ).properties(
        width=400,
        height=400,
        title="Revenue Distribution"
    )
    
    st.altair_chart(chart, use_container_width=True)
    
    # Show data table
    st.divider()
    st.subheader("📊 Detailed Breakdown")
    
    detail_df = pd.DataFrame({
        'Metric': ['Total Gross Collected', 'Creator Payouts', 'Razorpay Fees', 'Company Expenses', 'Net Profit'],
        'Amount (₹)': [total_gross_inr, total_creator_payout_inr, total_razorpay_fees_inr, total_expenses_inr, final_net_profit_inr],
        '% of Revenue': ['100%', f"{(total_creator_payout_inr/total_gross_inr*100):.2f}%", 
                        f"{(total_razorpay_fees_inr/total_gross_inr*100):.2f}%",
                        f"{(total_expenses_inr/total_gross_inr*100):.2f}%",
                        f"{(final_net_profit_inr/total_gross_inr*100):.2f}%"]
    })
    
    st.dataframe(detail_df, use_container_width=True, hide_index=True)

# ==============================================================================
# 7. TAB 3: EXPENSES (Same as before)
# ==============================================================================
with tab_expenses:
    st.subheader("💸 Manage Business Expenses")
    st.info("Log your company expenses (Server costs, Domain renewals, Software subscriptions, etc.)")
    
    # --- ADD NEW EXPENSE FORM ---
    with st.form("add_expense_form"):
        col_e1, col_e2, col_e3 = st.columns(3)
        
        with col_e1:
            expense_date = st.date_input("Date", value=today)
            category = st.selectbox("Category", [
                "Server/Hosting",
                "Domain/SSL",
                "Software/SaaS",
                "Payment Gateway Fees",
                "Legal/Compliance",
                "Marketing/Ads",
                "Office/Equipment",
                "Professional Services",
                "Bank Charges",
                "Other"
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
                    
                    st.success(f"✅ Expense of ₹{amount_inr:,.2f} added successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to add expense: {e}")
    
    st.divider()
    
    # --- VIEW EXPENSES TABLE ---
    st.subheader("📋 Expense Ledger")
    
    expenses_df = run_query("""
        SELECT id, expense_date, category, amount_inr, description, receipt_url, created_at
        FROM company_expenses
        WHERE expense_date BETWEEN %s AND %s
        ORDER BY expense_date DESC
    """, (start_date, end_date))
    
    if expenses_df.empty:
        st.info("No expenses logged for this period.")
    else:
        display_expenses = expenses_df.copy()
        display_expenses['amount_inr'] = pd.to_numeric(display_expenses['amount_inr'], errors='coerce') / 100.0
        display_expenses['expense_date'] = pd.to_datetime(display_expenses['expense_date']).dt.strftime('%Y-%m-%d')
        
        total_expenses = display_expenses['amount_inr'].sum()
        st.metric("💸 Total Expenses for Period", f"₹{total_expenses:,.2f}")
        
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
        
        # --- DELETE EXPENSE ---
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
                st.rerun()

# ==============================================================================
# 8. TAB 4 & 5: PLACEHOLDERS
# ==============================================================================
with tab3:
    st.subheader("📑 Formal Statements")
    st.info("🚧 This tab is under construction. We'll build formal P&L and Balance Sheet statements!")
    
with tab5:
    st.subheader("⬇️ CA Export")
    st.info("🚧 This tab is under construction. We'll build export functionality for your Chartered Accountant!")
