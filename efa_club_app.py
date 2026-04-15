import streamlit as st
import pandas as pd
import yfinance as yf
import json
from datetime import datetime
import os
from collections import defaultdict

st.set_page_config(page_title="EFA Investment Club", layout="wide", page_icon="🔥")

st.markdown("""
    <style>
    body { font-size: 1.1em; }
    .stDataFrame { font-size: 1.05em; }
    .total-row { font-weight: bold; font-size: 1.15em; background-color: #1e1e1e; }
    /* Right-align numeric column headers */
    .stDataFrame th[data-field="total_contributed"],
    .stDataFrame th[data-field="total_invested"],
    .stDataFrame th[data-field="fees"],
    .stDataFrame th[data-field="current_balance"] {
        text-align: right !important;
    }
    .bible-box {
        background-color: #4B0082;
        color: white;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 25px;
        border-left: 6px solid #9370DB;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    </style>
""", unsafe_allow_html=True)

st.title("🔥 EFA Investment Club")
st.caption("Equity For All • Accurate Deposit History + Live Portfolio Tracking • April 2026")

# ====================== INSPIRATIONAL BIBLE BOX ======================
st.markdown("""
<div class="bible-box">
    <h3>🙌 Building Together</h3>
    <p><strong>2 Corinthians 9:6-8 (NIV)</strong></p>
    <p>“Remember this: Whoever sows sparingly will also reap sparingly, and whoever sows generously will also reap generously. 
    Each of you should give what you have decided in your heart to give, not reluctantly or under compulsion, 
    for God loves a cheerful giver. And God is able to bless you abundantly, so that in all things at all times, 
    having all that you need, you will abound in every good work.”</p>
    <p style="font-size: 0.95em; opacity: 0.9;">Planting seeds as a family • Growing abundance to share with the world</p>
</div>
""", unsafe_allow_html=True)

# ====================== DATA FILES ======================
DATA_FILE = "efa_club_data.json"
CHANGE_LOG_FILE = "efa_change_log.json"
COMMENTS_FILE = "efa_comments.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "members": [
            {"name": "Matt Newbill",     "total_contributed": 5225.0, "current_balance": 5000.0},
            {"name": "Nick Vigil",       "total_contributed": 5225.0, "current_balance": 5000.0},
            {"name": "Mike Brooks",      "total_contributed": 2725.0, "current_balance": 2500.0},
            {"name": "Jose Calderon",    "total_contributed": 2725.0, "current_balance": 2500.0},
            {"name": "Jeff Gragert",     "total_contributed": 2725.0, "current_balance": 2500.0},
            {"name": "Ray Gilkes",       "total_contributed": 2500.0, "current_balance": 2500.0},
            {"name": "Antonio Calderon", "total_contributed": 225.0,  "current_balance": 0.0},
            {"name": "Josh Tafoya",      "total_contributed": 2725.0, "current_balance": 2500.0},
            {"name": "Jaydn Tafoya",     "total_contributed": 2725.0, "current_balance": 2500.0},
            {"name": "Chad Speegle",     "total_contributed": 2725.0, "current_balance": 2500.0},
            {"name": "Chris Koo",        "total_contributed": 225.0,  "current_balance": 0.0}
        ],
        "transactions": []
    }

data = load_data()

def load_change_log():
    if os.path.exists(CHANGE_LOG_FILE):
        with open(CHANGE_LOG_FILE, "r") as f:
            return json.load(f)
    return []

change_log = load_change_log()

def load_comments():
    if os.path.exists(COMMENTS_FILE):
        with open(COMMENTS_FILE, "r") as f:
            return json.load(f)
    return []

comments = load_comments()

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_change_log():
    with open(CHANGE_LOG_FILE, "w") as f:
        json.dump(change_log, f, indent=2)

def save_comments():
    with open(COMMENTS_FILE, "w") as f:
        json.dump(comments, f, indent=2)

df_members = pd.DataFrame(data["members"])

# ====================== AUTO-ALLOCATION & DYNAMIC TOTALS ======================
def auto_allocate_transactions():
    members_list = [m["name"] for m in data["members"]]
    num_members = 11
    for txn in data["transactions"]:
        if not txn.get("allocations"):
            amount = float(txn.get("amount", 0))
            if amount != 0:
                positive_amount = abs(amount)
                default = positive_amount / num_members
                txn["allocations"] = {name: default for name in members_list}

auto_allocate_transactions()

def calculate_dynamic_totals():
    df_txn = pd.DataFrame(data["transactions"])
    member_totals = {m["name"]: {"invested": 0.0, "fees": 0.0} for m in data["members"]}
    
    for _, row in df_txn.iterrows():
        alloc = row.get("allocations", {})
        amount = float(row.get("amount", 0))
        commission = float(row.get("commission", 0))
        txn_type = str(row.get("type", "")).lower().strip()
        
        is_buy = ("buy" in txn_type) and (str(row.get("ticker", "")).upper() not in ["CASH", ""])
        is_sell = "sell" in txn_type
        
        for member_name, alloc_amount in alloc.items():
            if member_name in member_totals:
                alloc_abs = abs(alloc_amount)
                if is_buy:
                    member_totals[member_name]["invested"] += alloc_abs
                elif is_sell:
                    member_totals[member_name]["invested"] -= alloc_abs
                
                if commission != 0 and amount != 0:
                    fee_share = commission * (alloc_abs / abs(amount))
                    member_totals[member_name]["fees"] += abs(fee_share)
    
    return member_totals

dynamic_totals = calculate_dynamic_totals()

for m in data["members"]:
    name = m["name"]
    m["total_invested"] = dynamic_totals.get(name, {}).get("invested", 0.0)
    m["fees"] = dynamic_totals.get(name, {}).get("fees", 0.0)

# ====================== SHARED HOLDINGS & PRICES ======================
df_txn = pd.DataFrame(data["transactions"])
buys = df_txn[df_txn.get("type", pd.Series([])).str.contains("Buy", na=False)]

holdings = defaultdict(lambda: {"qty": 0.0, "cost_basis": 0.0})
for _, row in buys.iterrows():
    ticker = str(row.get("ticker", "CASH"))
    if ticker == "CASH": continue
    qty = float(row.get("quantity", 0))
    cost = abs(float(row.get("amount", 0))) + abs(float(row.get("commission", 0)))
    holdings[ticker]["qty"] += qty
    holdings[ticker]["cost_basis"] += cost

prices = {}
for ticker in holdings:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        prices[ticker] = info.get("currentPrice") or info.get("regularMarketPreviousClose") or (stock.history(period="5d")['Close'].iloc[-1] if not stock.history(period="5d").empty else 0)
    except:
        prices[ticker] = 0

# ====================== NEGATIVE BALANCE ALERT ======================
negative_members = [m["name"] for m in data["members"] if (m.get("total_contributed", 0) - m.get("total_invested", 0)) < 0]
if negative_members:
    st.error(f"⚠️ **NEGATIVE BALANCE ALERT**: {', '.join(negative_members)} ha{'s' if len(negative_members)==1 else 've'} gone negative.")

# ====================== SIDEBAR - CSV UPLOAD ======================
st.sidebar.header("📤 CSV Upload (IBKR)")
uploaded_file = st.sidebar.file_uploader("Upload new IBKR Transactions CSV", type=["csv"])
if uploaded_file is not None:
    try:
        text = uploaded_file.getvalue().decode('utf-8')
        lines = text.splitlines()
        header_index = None
        for i, line in enumerate(lines):
            if "Transaction Type" in line and "Symbol" in line:
                header_index = i
                break
        if header_index is None:
            st.sidebar.error("Could not find transaction header in CSV.")
        else:
            df_transactions = pd.read_csv(uploaded_file, skiprows=header_index)
            numeric_cols = ['Quantity', 'Price', 'Gross Amount', 'Commission', 'Net Amount']
            for col in numeric_cols:
                if col in df_transactions.columns:
                    df_transactions[col] = pd.to_numeric(df_transactions[col], errors='coerce').fillna(0)
            
            st.sidebar.success(f"Loaded {len(df_transactions)} transactions")
            
            col1, col2 = st.sidebar.columns(2)
            if col1.button("Append to Existing Data"):
                for _, row in df_transactions.iterrows():
                    data["transactions"].append({
                        "date": str(row.get("Date", datetime.today().date())),
                        "type": str(row.get("Transaction Type", "Club Buy")),
                        "ticker": str(row.get("Symbol", "CASH")),
                        "quantity": float(row.get("Quantity", 0)),
                        "price": float(row.get("Price", 0)),
                        "amount": float(row.get("Net Amount", 0)),
                        "commission": float(row.get("Commission", 0)),
                        "notes": str(row.get("Description", "")),
                        "allocations": {}
                    })
                auto_allocate_transactions()
                save_data()
                st.sidebar.success("✅ Transactions appended!")
                st.rerun()
            
            if col2.button("Replace All Data", type="primary"):
                data["transactions"] = []
                for _, row in df_transactions.iterrows():
                    data["transactions"].append({
                        "date": str(row.get("Date", datetime.today().date())),
                        "type": str(row.get("Transaction Type", "Club Buy")),
                        "ticker": str(row.get("Symbol", "CASH")),
                        "quantity": float(row.get("Quantity", 0)),
                        "price": float(row.get("Price", 0)),
                        "amount": float(row.get("Net Amount", 0)),
                        "commission": float(row.get("Commission", 0)),
                        "notes": str(row.get("Description", "")),
                        "allocations": {}
                    })
                auto_allocate_transactions()
                save_data()
                st.sidebar.success("✅ All data replaced with new CSV!")
                st.rerun()
    except Exception as e:
        st.sidebar.error(f"Error reading CSV: {e}")

# ====================== TABS ======================
tab1, tab2, tab3, tab4 = st.tabs(["👥 Member Cash Balances", "📊 Club Holdings (Live)", "📈 Member Performance", "📋 Transaction History"])

with tab1:
    st.subheader("Member Cash Balances")
    
    df_display = df_members[["name", "total_contributed"]].copy()
    df_display["total_invested"] = [dynamic_totals.get(name, {}).get("invested", 0.0) for name in df_display["name"]]
    df_display["fees"] = [dynamic_totals.get(name, {}).get("fees", 0.0) for name in df_display["name"]]
    df_display["current_balance"] = df_display["total_contributed"] - df_display["total_invested"]
    
    total_data = {
        "name": "**TOTAL**",
        "total_contributed": round(df_display["total_contributed"].sum(), 2),
        "current_balance": round(df_display["current_balance"].sum(), 2),
        "total_invested": round(df_display["total_invested"].sum(), 2),
        "fees": round(df_display["fees"].sum(), 2)
    }
    
    df_with_total = pd.concat([df_display, pd.DataFrame([total_data])], ignore_index=True)
    
    edited_df = st.data_editor(
        df_with_total,
        column_config={
            "name": st.column_config.TextColumn("Member", disabled=True),
            "total_contributed": st.column_config.NumberColumn("Total Contributed $", format="$%.2f"),
            "current_balance": st.column_config.NumberColumn("Current Cash Balance $", format="$%.2f", disabled=True),
            "total_invested": st.column_config.NumberColumn("Total Invested $", format="$%.2f", disabled=True),
            "fees": st.column_config.NumberColumn("Fees $", format="$%.2f")
        },
        width="stretch",
        hide_index=True
    )
    
    if not edited_df.iloc[:-1].equals(df_display):
        for i, row in edited_df.iloc[:-1].iterrows():
            data["members"][i]["total_contributed"] = float(row["total_contributed"])
        save_data()
        st.success("✅ Balances updated")
        st.rerun()

    # Portfolio Performance Summary
    st.subheader("📈 Portfolio Performance Summary")
    perf_summary = []
    for ticker, h in holdings.items():
        qty = h["qty"]
        cost_basis = h["cost_basis"]
        if qty <= 0: continue
        live_price = prices.get(ticker, 0)
        market_value = qty * live_price
        pct_return = ((market_value / cost_basis) - 1) * 100 if cost_basis > 0 else 0
        perf_summary.append({"Ticker": ticker, "% Return": pct_return})
    
    if perf_summary:
        perf_df = pd.DataFrame(perf_summary).sort_values("% Return", ascending=False)
        total_cost = sum(h["cost_basis"] for h in holdings.values())
        total_market = sum(h["qty"] * prices.get(t, 0) for t, h in holdings.items())
        overall_return = ((total_market / total_cost) - 1) * 100 if total_cost > 0 else 0
        
        st.metric("Overall Portfolio Return", f"{overall_return:.2f}%")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Top 3 Performers**")
            st.dataframe(perf_df.head(3)[["Ticker", "% Return"]].style.format({"% Return": "{:.2f}%"}), hide_index=True)
        with col2:
            st.write("**Bottom 3 Performers**")
            st.dataframe(perf_df.tail(3)[["Ticker", "% Return"]].style.format({"% Return": "{:.2f}%"}), hide_index=True)
    else:
        st.info("No holdings yet.")

    # Funding Needs
    st.subheader("💰 Funding Needs")
    needs = []
    for m in data["members"]:
        contributed = m.get("total_contributed", 0)
        invested = dynamic_totals.get(m["name"], {}).get("invested", 0.0)
        current_balance = contributed - invested
        if current_balance < 0:
            needs.append(f"**{m['name']}** must provide admin with **${abs(current_balance):.2f}** to get balance to $0.00")
    
    if needs:
        for need in needs:
            st.warning(need)
    else:
        st.success("✅ All member balances are non-negative.")

    # Comments Section
    st.subheader("💬 Comments")
    with st.form("add_comment"):
        new_comment = st.text_input("Add a comment")
        if st.form_submit_button("Post Comment"):
            if new_comment.strip():
                comments.append({
                    "date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                    "author": "Member",
                    "text": new_comment.strip(),
                    "resolved": False
                })
                save_comments()
                st.success("Comment posted!")
                st.rerun()
    
    if comments:
        for i, comment in enumerate(comments):
            with st.expander(f"{comment['date']} - {comment['author']}"):
                st.write(comment["text"])
                col_a, col_b = st.columns([1,1])
                with col_a:
                    if st.button("Mark Resolved", key=f"res_{i}"):
                        comments[i]["resolved"] = True
                        save_comments()
                        st.rerun()
                with col_b:
                    if st.button("Delete", key=f"del_{i}"):
                        code = st.text_input("Admin Code (1998)", type="password", key=f"code_{i}")
                        if code == "1998":
                            del comments[i]
                            save_comments()
                            st.success("Comment deleted")
                            st.rerun()
                        else:
                            st.error("Incorrect code")
    else:
        st.info("No comments yet.")

# ====================== REMAINING TABS (unchanged) ======================
with tab2:
    st.subheader("Club Holdings with Live Prices")
    rows = []
    total_qty = total_cost = total_market = total_unrealized = 0.0
    
    for ticker, h in holdings.items():
        qty = h["qty"]
        cost_basis = h["cost_basis"]
        avg_price = cost_basis / qty if qty > 0 else 0
        live_price = prices.get(ticker, 0)
        market_value = qty * live_price
        unrealized = market_value - cost_basis
        pct_return = ((market_value / cost_basis) - 1) * 100 if cost_basis > 0 else 0
        
        rows.append({
            "Ticker": ticker,
            "Quantity": round(qty, 4),
            "Avg Purchase Price": f"${avg_price:,.4f}",
            "Cost Basis": f"${cost_basis:,.2f}",
            "Live Price": f"${live_price:,.2f}",
            "Market Value": f"${market_value:,.2f}",
            "Unrealized Gain/Loss": f"${unrealized:,.2f}",
            "% Return": f"{pct_return:.2f}%"
        })
        
        total_qty += qty
        total_cost += cost_basis
        total_market += market_value
        total_unrealized += unrealized
    
    total_pct_return = ((total_market / total_cost) - 1) * 100 if total_cost > 0 else 0
    rows.append({
        "Ticker": "**TOTAL**",
        "Quantity": round(total_qty, 4),
        "Avg Purchase Price": "—",
        "Cost Basis": f"${total_cost:,.2f}",
        "Live Price": "—",
        "Market Value": f"${total_market:,.2f}",
        "Unrealized Gain/Loss": f"${total_unrealized:,.2f}",
        "% Return": f"{total_pct_return:.2f}%"
    })
    
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

with tab3:
    st.subheader("Each Member’s Portfolio Performance")
    st.info("Portfolio Value = securities only (cash shown separately). Ownership based on Total Invested.")
    
    total_invested_per_member = [dynamic_totals.get(name, {}).get("invested", 0.0) for name in df_members["name"]]
    df_members["total_invested"] = total_invested_per_member
    total_invested_all = sum(total_invested_per_member)
    
    total_securities_value = sum(h["qty"] * prices.get(t, 0) for t, h in holdings.items())
    
    perf_rows = []
    grand_contributed = grand_invested = grand_cash = grand_portfolio = grand_unrealized = 0.0
    
    for i, m in df_members.iterrows():
        total_invested = m["total_invested"]
        ownership_pct = (total_invested / total_invested_all * 100) if total_invested_all > 0 else 0
        member_securities_value = total_securities_value * (total_invested / total_invested_all) if total_invested_all > 0 else 0
        unrealized_gain = member_securities_value - total_invested
        return_pct = (unrealized_gain / total_invested * 100) if total_invested > 0 else 0
        
        current_cash = m["total_contributed"] - total_invested
        
        perf_rows.append({
            "Member": m["name"],
            "Total Contributed": f"${m['total_contributed']:,.0f}",
            "Total Invested": f"${total_invested:,.0f}",
            "Current Cash": f"${current_cash:,.0f}",
            "% of Total Contribution": f"{ownership_pct:.2f}%",
            "Portfolio Value (Securities)": f"${member_securities_value:,.0f}",
            "Unrealized Gain": f"${unrealized_gain:,.0f}",
            "% Return": f"{return_pct:.2f}%"
        })
        
        grand_contributed += m['total_contributed']
        grand_invested += total_invested
        grand_cash += current_cash
        grand_portfolio += member_securities_value
        grand_unrealized += unrealized_gain
    
    perf_rows.append({
        "Member": "**TOTAL**",
        "Total Contributed": f"${grand_contributed:,.0f}",
        "Total Invested": f"${grand_invested:,.0f}",
        "Current Cash": f"${grand_cash:,.0f}",
        "% of Total Contribution": "100.00%",
        "Portfolio Value (Securities)": f"${grand_portfolio:,.0f}",
        "Unrealized Gain": f"${grand_unrealized:,.0f}",
        "% Return": "—"
    })
    
    st.dataframe(pd.DataFrame(perf_rows), width="stretch", hide_index=True)

with tab4:
    st.subheader("Transaction History Table")
    txn_df = pd.DataFrame(data["transactions"])
    if not txn_df.empty:
        txn_df = txn_df.sort_values("date", ascending=False).reset_index(drop=True)
        txn_df_display = txn_df.copy()
        txn_df_display["amount"] = txn_df_display.apply(
            lambda row: abs(row["amount"]) if str(row.get("type", "")).lower().startswith("buy") else row["amount"],
            axis=1
        )
        members_list = [m["name"] for m in data["members"]]
        for member in members_list:
            txn_df_display[member] = txn_df["allocations"].apply(lambda x: x.get(member, 0) if isinstance(x, dict) else 0)
        if "allocations" in txn_df_display.columns:
            txn_df_display = txn_df_display.drop(columns=["allocations"])
        st.dataframe(txn_df_display, width="stretch", hide_index=True)
    else:
        st.info("No transactions yet.")

    st.subheader("Change Log (Audit Trail)")
    if change_log:
        st.dataframe(pd.DataFrame(change_log), width="stretch", hide_index=True)
    else:
        st.info("No changes logged yet.")

    st.subheader("Individual Transaction Adjustments")
    if not txn_df.empty:
        for idx, row in txn_df.iterrows():
            col1, col2 = st.columns([9, 1])
            with col1:
                st.write(f"{row.get('date','')} | {row.get('type','')} | {row.get('ticker','')} | Qty: {row.get('quantity',0)} | Price: ${row.get('price',0):.2f} | Amount: ${abs(row.get('amount',0)):,.2f} | Comm: ${row.get('commission',0):.2f} | Notes: {row.get('notes','')}")
            with col2:
                if st.button("Adjust Allocation", key=f"adj_{idx}"):
                    st.session_state.editing_txn = idx
                    st.session_state.editing_row = row.to_dict()
    else:
        st.info("No transactions to adjust.")

    if "editing_txn" in st.session_state:
        idx = st.session_state.editing_txn
        row = st.session_state.editing_row
        with st.form("allocation_form"):
            st.subheader(f"Allocate {row.get('type','')} on {row.get('date','')}")
            num_members = 11
            members_list = [m["name"] for m in data["members"]]
            current_alloc = row.get("allocations", {})
            if not current_alloc:
                default = abs(row.get("amount", 0)) / num_members if row.get("amount", 0) != 0 else 0
                current_alloc = {name: default for name in members_list}
            new_alloc = {}
            total_entered = 0.0
            for name in members_list:
                val = st.number_input(f"{name}", value=float(current_alloc.get(name, 0)), step=0.01, key=f"alloc_{name}")
                new_alloc[name] = float(val)
                total_entered += float(val)
            reason = st.text_input("Reason for change (optional)")
            if st.form_submit_button("Save Allocation"):
                if abs(total_entered - abs(row.get("amount", 0))) > 0.01:
                    st.error("❌ Total must equal transaction amount")
                else:
                    change_entry = {
                        "date": str(datetime.now()),
                        "transaction_date": row.get("date", ""),
                        "changed_by": "AC",
                        "old_alloc": current_alloc,
                        "new_alloc": new_alloc,
                        "reason": reason or "No reason provided"
                    }
                    change_log.append(change_entry)
                    save_change_log()
                    for i, m in enumerate(data["members"]):
                        name = m["name"]
                        old_val = current_alloc.get(name, 0)
                        new_val = new_alloc.get(name, 0)
                        diff = new_val - old_val
                        data["members"][i]["current_balance"] += diff
                        data["members"][i]["total_contributed"] += diff
                    data["transactions"][idx]["allocations"] = new_alloc
                    save_data()
                    st.success("✅ Allocation saved")
                    del st.session_state.editing_txn
                    st.rerun()

st.caption("✅ Transaction History is the single source of truth • CSV upload with Append/Replace • Auto-allocation + Adjust button")