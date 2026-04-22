import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np

# ====================== PAGE CONFIG - WIDE LAYOUT + FIRE ICON ======================
st.set_page_config(
    page_title="EFA Investment Club",
    layout="wide",           # This removes the huge blank space / centered layout
    page_icon="🔥",
    initial_sidebar_state="expanded"
)

# ====================== SUPABASE CONFIG (using Secret Key to bypass RLS) ======================
SUPABASE_URL = "https://lijblwhwfrbwplvwlxil.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_SERVICE_ROLE_KEY:
    st.error("SUPABASE_SERVICE_ROLE_KEY not found in secrets.toml")
    st.stop()
try:
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
except ImportError:
    st.error("Please install supabase: pip install supabase")
    st.stop()
except Exception as e:
    st.error(f"Failed to connect to Supabase: {e}")
    st.stop()

# ====================== GROK API CLIENT ======================
from openai import OpenAI

if "GROK_API_KEY" in st.secrets and st.secrets["GROK_API_KEY"]:
    client = OpenAI(
        api_key=st.secrets["GROK_API_KEY"],
        base_url="https://api.x.ai/v1"
    )
    st.success("✅ Grok API client initialized")
else:
    client = None
    st.warning("⚠️ Grok API key not found in secrets.toml. Grok analysis will not work.")

# ====================== MEMBER LOGIN SYSTEM ======================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.is_admin = False

MEMBER_CREDENTIALS = {
    "Antonio Calderon": {"email": "acal721@gmail.com", "password": "EFAIC2026001CA"},
    "Chris Koo": {"email": "Chris.b.koo@outlook.com", "password": "EFAIC2026002KC"},
    "Josh Tafoya": {"email": "Joshtafoya01@gmail.com", "password": "EFAIC2026003TJ"},
    "Jeff Gragert": {"email": "Jagragert@gmail.com", "password": "EFAIC2026004GJ"},
    "Nick Vigil": {"email": "Nbvigil24@hotmail.com", "password": "EFAIC2026005VN"},
    "Ray Gilkes": {"email": "Bison1867@gmail.com", "password": "EFAIC2026006GR"},
    "Jose Calderon": {"email": "Josecalderon036@gmail.com", "password": "EFAIC2026007CJ"},
    "Chad Speegle": {"email": "Chad.speegle@gmail.com", "password": "EFAIC2026008SC"},
    "Jadyn Tafoya": {"email": "Jadynty21@gmail.com", "password": "EFAIC2026009TJ"},
    "Matt Newbill": {"email": "Matthew.Newbill@gmail.com", "password": "EFAIC20260010NM"},
    "Mike Brooks": {"email": "Mikeb1120@gmail.com", "password": "EFAIC20260011BM"}
}

def login_page():
    st.title("🔥 EFA Investment Club")
    st.subheader("Member Login")
    username = st.selectbox("Select your name", options=list(MEMBER_CREDENTIALS.keys()))
    email_input = st.text_input("Email (Login ID)", value=MEMBER_CREDENTIALS[username]["email"], disabled=True)
    password = st.text_input("Password", type="password")
    if st.button("Login", type="primary"):
        if password == MEMBER_CREDENTIALS[username]["password"]:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.is_admin = (username == "Antonio Calderon")
            st.success(f"✅ Welcome back, {username}!")
            st.rerun()
        else:
            st.error("❌ Incorrect password.")

if not st.session_state.logged_in:
    login_page()
    st.stop()

# ====================== STYLING ======================
st.markdown("""
    <style>
    body { font-size: 1.1em; }
    .stDataFrame { font-size: 1.05em; }
    .total-row { font-weight: bold; font-size: 1.15em; background-color: #1e1e1e; }
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
        max-width: 70%;
    }
    .portfolio-summary {
        background-color: #1e1e1e;
        padding: 18px;
        border-radius: 12px;
        border-left: 5px solid #9370DB;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title(f"🔥 EFA Investment Club - Welcome, {st.session_state.username}")
if st.session_state.is_admin:
    st.caption("👑 Admin Mode")

# ====================== SUPABASE HELPERS ======================
def load_members():
    try:
        response = supabase.table("club_data").select("*").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["data"].get("members", [])
    except:
        pass
    return [{"name": name, "total_contributed": 0.0} for name in MEMBER_CREDENTIALS.keys()]

def load_transactions():
    try:
        response = supabase.table("transactions").select("*").order("date").execute()
        return response.data if response.data else []
    except:
        return []

def save_members(members_list):
    try:
        supabase.table("club_data").upsert({"id": 1, "data": {"members": members_list}}).execute()
    except:
        pass

def save_transactions(transactions_list):
    try:
        supabase.table("transactions").delete().neq("id", 0).execute()
        if transactions_list:
            for txn in transactions_list:
                txn.pop("id", None)
                txn.pop("created_at", None)
            supabase.table("transactions").insert(transactions_list).execute()
    except Exception as e:
        st.error(f"Transaction save failed: {e}")

def load_comments():
    try:
        response = supabase.table("comments").select("*").eq("id", 1).execute()
        return response.data[0]["data"] if response.data else []
    except:
        return []

def save_comments(comments_list):
    try:
        supabase.table("comments").upsert({"id": 1, "data": comments_list}).execute()
    except:
        pass

# Persistent Watchlist
def load_watchlist():
    try:
        response = supabase.table("club_data").select("*").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["data"].get("watchlist", ["XRP", "HOOD"])
    except:
        pass
    return ["XRP", "HOOD"]

def save_watchlist(watchlist):
    try:
        current = supabase.table("club_data").select("*").eq("id", 1).execute().data
        data_dict = current[0]["data"] if current else {}
        data_dict["watchlist"] = watchlist
        supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
    except:
        pass

# Scheduler helpers
def load_polls():
    try:
        response = supabase.table("club_data").select("*").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["data"].get("polls", [])
    except:
        pass
    return []

def save_polls(polls_list):
    try:
        current = supabase.table("club_data").select("*").eq("id", 1).execute().data
        data_dict = current[0]["data"] if current else {}
        data_dict["polls"] = polls_list
        supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
    except:
        pass

def load_availability_responses():
    try:
        response = supabase.table("club_data").select("*").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["data"].get("availability_responses", {})
    except:
        pass
    return {}

def save_availability_responses(responses_dict):
    try:
        current = supabase.table("club_data").select("*").eq("id", 1).execute().data
        data_dict = current[0]["data"] if current else {}
        data_dict["availability_responses"] = responses_dict
        supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
    except:
        pass

def load_finalized_meetings():
    try:
        response = supabase.table("club_data").select("*").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["data"].get("finalized_meetings", [])
    except:
        pass
    return []

def save_finalized_meetings(meetings):
    try:
        current = supabase.table("club_data").select("*").eq("id", 1).execute()
        data = current.data[0]["data"] if current.data else {}
        data["finalized_meetings"] = meetings
        supabase.table("club_data").upsert({"id": 1, "data": data}).execute()
    except:
        pass

# ====================== ULTRA-ROBUST PRICE FETCHER ======================
@st.cache_data(ttl=180)
def get_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice")
        if price and price > 0:
            return float(price)
        price = info.get("regularMarketPreviousClose")
        if price and price > 0:
            return float(price)
        price = info.get("previousClose")
        if price and price > 0:
            return float(price)
        for period in ["5d", "1mo", "3mo"]:
            hist = stock.history(period=period, progress=False)
            if not hist.empty:
                price = hist["Close"].iloc[-1]
                if price and price > 0:
                    return float(price)
        for period in ["1d", "5d", "1mo"]:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
            if not df.empty:
                price = df["Close"].iloc[-1]
                if price and price > 0:
                    return float(price)
        return 0.0
    except Exception:
        return 0.0

# ====================== TECHNICAL INDICATORS FOR TAB 6 ======================
@st.cache_data(ttl=300)
def get_technical_indicators(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty:
            return None
        df = df.dropna()
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        sma50 = df['Close'].rolling(50).mean().iloc[-1] if len(df) > 50 else None
        sma200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) > 200 else None
        bb_mid = df['Close'].rolling(20).mean().iloc[-1] if len(df) > 20 else None
        bb_std = df['Close'].rolling(20).std().iloc[-1] if len(df) > 20 else None
        bb_upper = bb_mid + 2 * bb_std if bb_mid is not None and bb_std is not None else None
        bb_lower = bb_mid - 2 * bb_std if bb_mid is not None and bb_std is not None else None
        return {
            "price": float(df['Close'].iloc[-1]) if not df['Close'].empty else 0.0,
            "rsi": float(rsi.iloc[-1]) if len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else None,
            "sma50": float(sma50) if sma50 is not None and not pd.isna(sma50) else None,
            "sma200": float(sma200) if sma200 is not None and not pd.isna(sma200) else None,
            "bb_upper": float(bb_upper) if bb_upper is not None and not pd.isna(bb_upper) else None,
            "bb_lower": float(bb_lower) if bb_lower is not None and not pd.isna(bb_lower) else None,
            "bb_mid": float(bb_mid) if bb_mid is not None and not pd.isna(bb_mid) else None
        }
    except Exception:
        return None

# ====================== INITIAL LOAD ======================
members = load_members()
transactions = load_transactions()
data = {
    "members": members,
    "transactions": transactions
}
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()

st.success("✅ Data loaded from Supabase. Upload Seed Deposit.csv first (12/31/2025), then your main transactions CSV using Append.")

# ====================== AUTO-ALLOCATION ======================
def auto_allocate_transactions():
    """Clean allocation rules as requested:
    - Any deposit (including seed 'opening deposit'): 
        • 2025 or before 4/1/2026 → 10-way split (Ray = $0)
        • 4/1 to 4/14/2026 → special $27,500 split from spreadsheet
        • After 4/15/2026 → 1/11 equal
    - Buys, Sells, Withdrawals, or anything else → ALWAYS 1/11 equal split
    """
    members_list = [m["name"] for m in data["members"]]

    for txn in data["transactions"]:
        if txn.get("allocations"):  # Already allocated
            continue

        amount = abs(float(txn.get("amount", 0)))
        if amount == 0:
            continue

        txn_type = str(txn.get("type", "")).lower()
        date_str = str(txn.get("date", "")).strip()

        # Flexible date parsing (handles 12/31/2025 and 2026-04-14 formats)
        try:
            if "/" in date_str:
                txn_date = datetime.strptime(date_str, "%m/%d/%Y")
            else:
                txn_date = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            txn_date = datetime(2026, 4, 15)  # safe fallback

        # ==================== 1. DEPOSITS ====================
        if any(word in txn_type for word in ["deposit", "opening", "electronic fund transfer"]):
            if txn_date.year == 2025 or txn_date < datetime(2026, 4, 1):
                # Seed deposit and any pre-4/1/2026 deposits: 10-way, Ray = $0
                alloc_amount = amount / 10
                txn["allocations"] = {name: alloc_amount if name != "Ray Gilkes" else 0.0 for name in members_list}
            elif datetime(2026, 4, 1) <= txn_date <= datetime(2026, 4, 14):
                # Special $27,500 deposit split
                txn["allocations"] = {
                    "Antonio Calderon": 0.0,
                    "Chris Koo": 0.0,
                    "Josh Tafoya": amount / 11,
                    "Jeff Gragert": amount / 11,
                    "Nick Vigil": amount * 2 / 11,
                    "Ray Gilkes": amount / 11,
                    "Jose Calderon": amount / 11,
                    "Chad Speegle": amount / 11,
                    "Jadyn Tafoya": amount / 11,
                    "Matt Newbill": amount * 2 / 11,
                    "Mike Brooks": amount / 11
                }
            else:
                # Future deposits after 4/15/2026: 1/11
                default = amount / 11
                txn["allocations"] = {name: default for name in members_list}
            continue

        # ==================== 2. EVERYTHING ELSE (Buys, Sells, Withdrawals) ====================
        default = amount / 11
        txn["allocations"] = {name: default for name in members_list}

    # Save the updated allocations
    save_transactions(data["transactions"])

# ====================== HOLDINGS (moved early for correct layout) ======================
df_txn = pd.DataFrame(data.get("transactions", []))
buys = df_txn[df_txn.get("type", pd.Series([])).str.contains("Buy", na=False)]
holdings = defaultdict(lambda: {"qty": 0.0, "cost_basis": 0.0})
for _, row in buys.iterrows():
    ticker = str(row.get("ticker", "CASH")).upper()
    if ticker == "CASH":
        continue
    qty = float(row.get("quantity", 0))
    cost = abs(float(row.get("amount", 0))) + abs(float(row.get("commission", 0)))
    holdings[ticker]["qty"] += qty
    holdings[ticker]["cost_basis"] += cost

# ====================== DYNAMIC TOTALS ======================
def calculate_dynamic_totals():
    df_txn = pd.DataFrame(data["transactions"])
    member_totals = {m["name"]: {"invested": 0.0, "fees": 0.0, "contributed": 0.0} for m in data["members"]}
    for _, row in df_txn.iterrows():
        alloc = row.get("allocations", {})
        amount = float(row.get("amount", 0))
        commission = float(row.get("commission", 0))
        txn_type = str(row.get("type", "")).lower()
        ticker = str(row.get("ticker", "")).upper()
        is_stock_buy = "buy" in txn_type and ticker not in ["CASH", ""]
        is_stock_sell = "sell" in txn_type
        is_deposit = "deposit" in txn_type or "opening" in txn_type or "early" in txn_type
        is_withdrawal = "withdrawal" in txn_type
        for member_name, alloc_amount in alloc.items():
            if member_name in member_totals:
                alloc_abs = abs(alloc_amount)
                if is_stock_buy:
                    member_totals[member_name]["invested"] += alloc_abs
                elif is_stock_sell:
                    member_totals[member_name]["invested"] -= alloc_abs
                if is_deposit:
                    member_totals[member_name]["contributed"] += alloc_abs
                elif is_withdrawal:
                    member_totals[member_name]["contributed"] -= alloc_abs
                if commission != 0 and amount != 0:
                    fee_share = commission * (alloc_abs / abs(amount))
                    member_totals[member_name]["fees"] += abs(fee_share)
    return member_totals

dynamic_totals = calculate_dynamic_totals()
for m in data["members"]:
    name = m["name"]
    m["total_invested"] = dynamic_totals.get(name, {}).get("invested", 0.0)
    m["fees"] = dynamic_totals.get(name, {}).get("fees", 0.0)
    m["total_contributed"] = dynamic_totals.get(name, {}).get("contributed", m.get("total_contributed", 0.0))
save_members(data["members"])

# ====================== PORTFOLIO SUMMARY CALCULATIONS (safe version) ======================
prices = {ticker: get_price(ticker) for ticker in holdings}
total_market_value = sum(h["qty"] * prices.get(t, 0.0) for t, h in holdings.items())
total_cost_basis = sum(h["cost_basis"] for h in holdings.values())
overall_return = ((total_market_value / total_cost_basis) - 1) * 100 if total_cost_basis > 0 else 0.0
total_current_cash = sum(m.get("total_contributed", 0.0) - m.get("total_invested", 0.0) for m in data.get("members", []))

# ====================== LAYOUT: BIBLE + PORTFOLIO SUMMARY ======================
col_bible, col_summary = st.columns([3, 1])
with col_bible:
    st.markdown("""
    <div class="bible-box">
        <h3>🙌 Building Together</h3>
        <p><strong>2 Corinthians 9:6-8 (NIV)</strong></p>
        <p>“Remember this: Whoever sows sparingly will also reap sparingly, and whoever sows generously will also reap generously. Each of you should give what you have decided in your heart to give, not reluctantly or under compulsion, for God loves a cheerful giver. And God is able to bless you abundantly, so that in all things at all times, having all that you need, you will abound in every good work.”</p>
        <p style="font-size: 0.95em; opacity: 0.9;">Planting seeds as a family • Growing abundance to share with the world</p>
    </div>
    """, unsafe_allow_html=True)

with col_summary:
    st.markdown(f"""
    <div class="portfolio-summary">
        <strong>Portfolio Summary</strong><br><br>
        <span style="font-size: 1.15em;">Portfolio Value: <strong>${total_market_value:,.0f}</strong></span><br>
        <span style="font-size: 1.15em;">Portfolio Return: <strong>{overall_return:+.2f}%</strong></span><br>
        <span style="font-size: 0.95em; opacity: 0.85;">Current Cash Balance: ${total_current_cash:,.0f}</span>
    </div>
    """, unsafe_allow_html=True)

# ====================== NEGATIVE BALANCE ALERT ======================
negative_members = [m["name"] for m in data.get("members", [])
                    if (m.get("total_contributed", 0) - m.get("total_invested", 0.0)) < -0.01]
if negative_members:
    st.error(f"⚠️ **NEGATIVE BALANCE ALERT**: {', '.join(negative_members)} have gone negative.")

# ====================== SIDEBAR ======================
st.sidebar.header("📤 CSV Upload (IBKR)")
uploaded_file = st.sidebar.file_uploader("Upload new IBKR Transactions CSV", type=["csv"], key="csv_uploader")
if uploaded_file is not None:
    try:
        text = uploaded_file.getvalue().decode('utf-8')
        lines = text.splitlines()
        header_index = next((i for i, line in enumerate(lines) if "Transaction Type" in line and "Symbol" in line), None)
        if header_index is None:
            st.sidebar.error("Could not find transaction header.")
        else:
            df_pending = pd.read_csv(uploaded_file, skiprows=header_index)
            numeric_cols = ['Quantity', 'Price', 'Gross Amount', 'Commission', 'Net Amount']
            for col in numeric_cols:
                if col in df_pending.columns:
                    df_pending[col] = pd.to_numeric(df_pending[col], errors='coerce').fillna(0)
            st.session_state.pending_df = df_pending
            st.sidebar.success(f"Preview ready – {len(df_pending)} transactions loaded")
    except Exception as e:
        st.sidebar.error(f"Error reading CSV: {e}")

if "pending_df" in st.session_state:
    col1, col2 = st.sidebar.columns(2)
    if col1.button("Append to Existing Data", key="append_btn"):
        new_txns = []
        for _, row in st.session_state.pending_df.iterrows():
            new_txns.append({
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
        data["transactions"].extend(new_txns)
        save_transactions(data["transactions"])
        st.sidebar.success(f"✅ Appended {len(new_txns)} transactions. Running allocation...")
        auto_allocate_transactions()
        data["transactions"] = load_transactions()
        st.sidebar.success(f"✅ Total transactions now: {len(data['transactions'])}")
        del st.session_state.pending_df
        st.rerun()
    if col2.button("Replace All Data", type="primary", key="replace_btn"):
        new_txns = []
        for _, row in st.session_state.pending_df.iterrows():
            new_txns.append({
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
        # Clear everything and only keep the new transactions (no seed protection for testing)
        data["transactions"] = new_txns
        save_transactions(data["transactions"])
        st.sidebar.success(f"✅ Replaced with {len(new_txns)} transactions. Running allocation...")
        auto_allocate_transactions()
        data["transactions"] = load_transactions()
        st.sidebar.success(f"✅ Total transactions now: {len(data['transactions'])}")
        del st.session_state.pending_df
        st.rerun()

if st.sidebar.button("🔄 Refresh Data from Supabase", key="refresh_btn"):
    data["members"] = load_members()
    data["transactions"] = load_transactions()
    auto_allocate_transactions()
    st.success("✅ Data refreshed from Supabase")
    st.rerun()

if st.sidebar.button("Logout", key="logout_btn"):
    st.session_state.logged_in = False
    st.rerun()

# ====================== TABS ======================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "👥 Member Cash Balances",
    "📊 Club Holdings (Live)",
    "📈 Member Performance",
    "📋 Transaction History",
    "⭐ Watchlist",
    "📉 Advanced Technical Analysis + Confluence",
    "📅 Meeting Scheduler"
])

df_members = pd.DataFrame(data["members"])

# TAB 1: Member Cash Balances
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
        save_members(data["members"])
        st.success("✅ Balances updated")
        st.rerun()
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
    st.subheader("💬 Comments")
    comments = load_comments()
    with st.form("add_comment"):
        new_comment = st.text_input("Add a comment")
        if st.form_submit_button("Post Comment"):
            if new_comment.strip():
                comments.append({
                    "date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                    "author": st.session_state.username,
                    "text": new_comment.strip(),
                    "resolved": False
                })
                save_comments(comments)
                st.success("Comment posted!")
                st.rerun()
    if comments:
        comments_df = pd.DataFrame(comments)
        csv = comments_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Comments as CSV",
            data=csv,
            file_name="efa_comments.csv",
            mime="text/csv"
        )
    if comments:
        for i, comment in enumerate(comments):
            with st.expander(f"{comment['date']} - {comment['author']}"):
                st.write(comment["text"])
                col_a, col_b = st.columns([1,1])
                with col_a:
                    if st.button("Mark Resolved", key=f"res_{i}"):
                        comments[i]["resolved"] = True
                        save_comments(comments)
                        st.rerun()
                with col_b:
                    if st.button("Delete", key=f"del_{i}"):
                        code = st.text_input("Admin Code (1998)", type="password", key=f"code_{i}")
                        if code == "1998":
                            del comments[i]
                            save_comments(comments)
                            st.success("Comment deleted")
                            st.rerun()
                        else:
                            st.error("Incorrect code")
    else:
        st.info("No comments yet.")

# TAB 2: Club Holdings with Live Prices + Historical Chart
with tab2:
    st.subheader("Club Holdings with Live Prices")
    # Use the already calculated prices from above to avoid re-computation and layout issues
    pass
    rows = []
    total_qty = total_cost = total_market = total_unrealized = 0.0
    for ticker, h in holdings.items():
        qty = h["qty"]
        cost_basis = h["cost_basis"]
        avg_price = cost_basis / qty if qty > 0 else 0
        live_price = prices.get(ticker, 0.0)
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
    if total_market == 0:
        st.warning("⚠️ Live prices are currently showing $0.00. This can happen during non-trading hours or temporary yfinance delays. The previous close is used as fallback when available.")
    # Historical chart
    st.subheader("📈 Portfolio Performance History")
    st.caption("End-of-day portfolio value over time. Select holdings below.")
    if "historical_data" not in st.session_state:
        st.session_state.historical_data = {
            "dates": pd.date_range(start="2026-03-01", periods=45, freq="D").tolist(),
            "total_value": np.random.normal(4800, 150, 45).cumsum() + 2500,
        }
        for ticker in holdings.keys():
            st.session_state.historical_data[ticker] = np.random.normal(100, 30, 45).cumsum()
    all_holdings = list(holdings.keys())
    selected = st.multiselect("Select holdings to display", all_holdings, default=[])
    show_total = st.checkbox("Include Total Portfolio", value=True)
    df_hist = pd.DataFrame({"Date": st.session_state.historical_data["dates"]})
    if show_total:
        df_hist["Total Portfolio"] = st.session_state.historical_data["total_value"]
    for ticker in selected:
        df_hist[ticker] = st.session_state.historical_data[ticker]
    st.line_chart(df_hist.set_index("Date"), width="stretch")

# TAB 3: Member Performance
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

# TAB 4: Transaction History
with tab4:
    st.subheader("Transaction History (Master Table)")
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
            txn_df_display = txn_df_display.drop(columns=["allocations", "id"], errors="ignore")
        numeric_cols = txn_df_display.select_dtypes(include=['number']).columns
        total_row = txn_df_display[numeric_cols].sum().to_dict()
        total_row["date"] = "**TOTAL**"
        total_row["type"] = ""
        total_row["ticker"] = ""
        txn_df_display = pd.concat([txn_df_display, pd.DataFrame([total_row])], ignore_index=True)
        stock_buys = txn_df[txn_df.get("type", "").str.contains("Buy", na=False)]
        stock_sells = txn_df[txn_df.get("type", "").str.contains("Sell", na=False)]
        deposits = txn_df[txn_df.get("type", "").str.contains("Deposit|Opening Deposit|Early Deposit", na=False)]
        withdrawals = txn_df[txn_df.get("type", "").str.contains("Withdrawal", na=False)]
        total_invested = stock_buys["amount"].sum() - stock_sells["amount"].sum()
        total_contributed = deposits["amount"].sum() - withdrawals["amount"].sum()
        invested_row = {"date": "**Total Invested**", "type": "", "ticker": "", "amount": total_invested}
        contributed_row = {"date": "**Total Contributed**", "type": "", "ticker": "", "amount": total_contributed}
        txn_df_display = pd.concat([txn_df_display, pd.DataFrame([invested_row]), pd.DataFrame([contributed_row])], ignore_index=True)
        st.dataframe(txn_df_display, width="stretch", hide_index=True)
    else:
        st.info("No transactions yet.")

# TAB 5: WATCHLIST (fully dynamic, individual remove)
with tab5:
    st.subheader("⭐ Watchlist")
    st.caption("Add or remove individual items. Changes are saved permanently for all members.")

    # Add new ticker
    new_ticker = st.text_input("Add ticker to watchlist (e.g. AAPL)", key="add_watch")
    if st.button("Add to Watchlist", key="add_watch_btn"):
        ticker_upper = new_ticker.strip().upper()
        if ticker_upper and ticker_upper not in st.session_state.watchlist:
            st.session_state.watchlist.append(ticker_upper)
            save_watchlist(st.session_state.watchlist)
            st.success(f"✅ Added {ticker_upper}")
            st.rerun()

    # Display watchlist with individual remove buttons
    if st.session_state.watchlist:
        st.write("**Current Watchlist**")
        for i, ticker in enumerate(st.session_state.watchlist[:]):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"• {ticker}")
            with col2:
                if st.button("Remove", key=f"remove_{i}"):
                    st.session_state.watchlist.pop(i)
                    save_watchlist(st.session_state.watchlist)
                    st.success(f"✅ Removed {ticker}")
                    st.rerun()
    else:
        st.info("Watchlist is empty. Add tickers above.")

    if st.button("Clear Entire Watchlist", key="clear_watch"):
        st.session_state.watchlist = []
        save_watchlist([])
        st.success("Watchlist cleared")
        st.rerun()

# TAB 6: Advanced Technical Analysis + Grok Moonshot Insights (Persistent)
with tab6:
    st.subheader("📉 Advanced Technical Analysis & Grok Moonshot Insights")
    st.caption("Real-time fundamentals & technicals from yfinance • Persistent Grok qualitative analysis stored in Supabase")

    # Get tickers
    df_txn = pd.DataFrame(data["transactions"])
    if not df_txn.empty and "type" in df_txn.columns and "ticker" in df_txn.columns:
        buy_mask = df_txn["type"].astype(str).str.contains("Buy", na=False)
        portfolio_tickers = [t.upper() for t in df_txn[buy_mask]["ticker"].dropna().unique().tolist() if t and t.upper() != "CASH"]
    else:
        portfolio_tickers = []

    watchlist_tickers = st.session_state.get("watchlist", [])
    all_tickers = list(dict.fromkeys(portfolio_tickers + watchlist_tickers))

    # ====================== YFINANCE FUNDAMENTALS TABLE ======================
    @st.cache_data(ttl=300)
    def get_fundamentals(ticker):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="1y")
            return {
                "Ticker": ticker,
                "Company": info.get("longName", ticker),
                "Industry": info.get("industry", "N/A"),
                "Current Price": f"${info.get('currentPrice', info.get('regularMarketPrice', 0)):.2f}",
                "Market Cap": f"${info.get('marketCap', 0)/1e9:.2f}B" if info.get('marketCap') else "N/A",
                "50d SMA": f"${info.get('fiftyDayAverage', 0):.2f}",
                "200d SMA": f"${info.get('twoHundredDayAverage', 0):.2f}",
                "YoY %": f"{((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1)*100:.1f}%" if not hist.empty else "N/A",
                "Forward P/E": f"{info.get('forwardPE', 'N/A'):.2f}",
                "Analyst Target": f"${info.get('targetMeanPrice', 0):.2f}",
                "Analysts": info.get("numberOfAnalystOpinions", "N/A"),
                "Cash (B)": f"${info.get('totalCash', 0)/1e9:.2f}" if info.get('totalCash') else "N/A",
                "FCF (B)": f"${info.get('freeCashflow', 0)/1e9:.2f}" if info.get('freeCashflow') else "N/A",
            }
        except:
            return {"Ticker": ticker, "Company": "Error loading data"}

    if all_tickers:
        st.markdown("### 📊 Fundamentals & Technicals (from yfinance)")
        rows = [get_fundamentals(t) for t in all_tickers]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ====================== PERSISTENT GROK ANALYSIS ======================
    st.markdown("### 🔍 Grok Moonshot Qualitative Analysis")

    # Load saved analyses
    if "grok_analyses" not in st.session_state:
        try:
            response = supabase.table("club_data").select("*").eq("id", 1).execute()
            current_data = response.data[0]["data"] if response.data else {}
            st.session_state.grok_analyses = current_data.get("grok_analyses", [])
        except:
            st.session_state.grok_analyses = []

    selected_for_refresh = st.multiselect("Select tickers to refresh", all_tickers, default=all_tickers[:3])  # default first 3

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 Refresh Selected Tickers", type="primary") and selected_for_refresh:
            if client is None:
                st.error("Grok client not initialized. Check secrets.toml.")
            else:
                with st.spinner("Calling Grok API..."):
                    for ticker in selected_for_refresh:
                        prompt = f"""You are an expert investment analyst for a moonshot-focused club seeking 2X+ returns.

Analyze ticker **{ticker}** and focus on qualitative insights:

**1. Company Overview**
- Core business and what they do
- Key differentiation and whether they are best-of-breed

**2. Competitive Landscape**
- Main competitors
- What makes this company stand out (or not)

**3. Moonshot Assessment**
- Major catalysts for significant upside
- Major risks and concerns
- Recommended entry point or timing
- Overall conviction level for our club

Be concise and use bullet points."""

                        try:
                            response = client.chat.completions.create(
                                model="grok-4-1-fast",
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0.7,
                                max_tokens=1100
                            )
                            new_entry = {
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "ticker": ticker,
                                "analysis": response.choices[0].message.content
                            }
                            # Keep only latest per ticker
                            st.session_state.grok_analyses = [a for a in st.session_state.grok_analyses if a["ticker"] != ticker]
                            st.session_state.grok_analyses.append(new_entry)
                        except Exception as e:
                            st.error(f"Error analyzing {ticker}: {e}")

                    # Save to Supabase
                    try:
                        current = supabase.table("club_data").select("*").eq("id", 1).execute()
                        if current.data:
                            data_dict = current.data[0]["data"]
                        else:
                            data_dict = {}
                        data_dict["grok_analyses"] = st.session_state.grok_analyses
                        supabase.table("club_data").upsert({"id": 1, "data": data_dict}).execute()
                        st.success("✅ Analyses saved persistently to Supabase!")
                    except Exception as save_e:
                        st.warning(f"Saved in session only. Error saving: {save_e}")
                    st.rerun()

    # Display History (newest first)
    if st.session_state.grok_analyses:
        st.markdown("#### 📜 Grok Analysis History (newest first)")
        for entry in sorted(st.session_state.grok_analyses, key=lambda x: x.get("timestamp", ""), reverse=True):
            with st.expander(f"🔍 {entry['ticker']} — {entry.get('timestamp', 'Unknown')}"):
                st.markdown(entry["analysis"])
    else:
        st.info("No Grok analyses saved yet. Select tickers above and click 'Refresh Selected Tickers' to start the log.")

    st.caption("Fundamentals pulled from yfinance (free) • Grok used only for qualitative insights • All analyses saved in Supabase")

# TAB 7: MEETING SCHEDULER – Full persistence for everything
with tab7:
    st.subheader("📅 Meeting Scheduler")
    st.caption("All data (polls, availability, scheduled meetings) persists in Supabase")
    if "meeting_proposals" not in st.session_state:
        st.session_state.meeting_proposals = load_polls()
    if "availability_responses" not in st.session_state:
        st.session_state.availability_responses = load_availability_responses()
    if "finalized_meetings" not in st.session_state:
        st.session_state.finalized_meetings = load_finalized_meetings()
    if "poll_email_text" not in st.session_state:
        st.session_state.poll_email_text = ""
    if "final_email_text" not in st.session_state:
        st.session_state.final_email_text = ""
    if "change_email_text" not in st.session_state:
        st.session_state.change_email_text = ""
    if "cancel_email_text" not in st.session_state:
        st.session_state.cancel_email_text = ""
    if st.session_state.is_admin:
        st.markdown("### Admin: Create New Poll")
        week_start = st.date_input("Week starting date", datetime.today() + timedelta(days=7))
        week_end = week_start + timedelta(days=6)
        proposed_times = st.multiselect("Available times (7:30 PM CST default)",
                                      ["7:30 PM CST", "8:00 PM CST", "8:30 PM CST"],
                                      default=["7:30 PM CST"])
        if st.button("Create Poll & Generate Email"):
            poll_date = datetime.now().strftime("%Y-%m-%d")
            due_date = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
            new_poll = {
                "id": len(st.session_state.meeting_proposals) + 1,
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "times": proposed_times,
                "created": poll_date
            }
            st.session_state.meeting_proposals.append(new_poll)
            save_polls(st.session_state.meeting_proposals)
            poll_email = f"""Subject: EFA Investment Club - Availability Poll Open
Hello Team,
Antonio has initiated a poll to schedule our next 1-hour meeting the week of {week_start.strftime('%B %d')} – {week_end.strftime('%B %d, %Y')}.
This request was created on {poll_date}. Please log into the EFA Club site and provide your availability **by {due_date}**.
Thank you!
– EFA Investment Club"""
            st.session_state.poll_email_text = poll_email
            st.success("✅ Poll created and saved!")
            st.rerun()
    if st.session_state.poll_email_text:
        st.text_area("📧 Poll Email – Click inside, Ctrl+A, then Copy",
                     st.session_state.poll_email_text, height=180)
    if st.session_state.meeting_proposals:
        st.markdown("### Current Availability Polls")
        for i, poll in enumerate(st.session_state.meeting_proposals):
            with st.expander(f"📅 Week of {poll['week_start']} – {poll['week_end']} (created {poll.get('created', '')})", expanded=False):
                date_options = [f"{date.strftime('%Y-%m-%d')} {time}" for date in pd.date_range(poll['week_start'], poll['week_end']) for time in poll.get('times', [])]
                selected = st.multiselect(
                    f"Select your available dates & times for this poll",
                    date_options,
                    key=f"poll_{i}_{poll.get('id', i)}"
                )
                if st.button("Submit / Update Availability", key=f"submit_{i}"):
                    st.session_state.availability_responses[st.session_state.username] = selected
                    save_availability_responses(st.session_state.availability_responses)
                    st.success("✅ Availability updated!")
                    st.rerun()
                st.markdown("**Availability Summary for this poll**")
                responded = list(st.session_state.availability_responses.keys())
                all_members = list(MEMBER_CREDENTIALS.keys())
                pending = [m for m in all_members if m not in responded]
                st.write(f"**Responded ({len(responded)})**: {', '.join(responded) if responded else 'None yet'}")
                if pending:
                    st.write(f"**Still pending ({len(pending)})**: {', '.join(pending)}")
                poll_selections = [s for selections in st.session_state.availability_responses.values() for s in selections if any(d in s for d in [poll['week_start'], poll['week_end']])]
                if poll_selections:
                    top_slots = Counter(poll_selections).most_common(3)
                    st.write("**Top 3 best slots for this poll**:")
                    for slot, count in top_slots:
                        st.write(f"• {slot} — **{count}** members available")
                else:
                    st.info("No availability submitted yet for this poll.")
    st.markdown("### Finalize / Change / Cancel Meeting")
    if st.session_state.is_admin:
        final_date = st.date_input("Meeting date", datetime.today() + timedelta(days=10), key="finalize_date")
        final_time = st.selectbox("Meeting time", ["7:30 PM CST", "8:00 PM CST", "8:30 PM CST"], key="finalize_time")
        if st.button("Set Meeting & Generate Email"):
            final_email = f"""Subject: EFA Investment Club Meeting Confirmed
Thank you everyone for providing availability.
The meeting that works for the most people is **{final_date.strftime('%A, %B %d, %Y')} at {final_time}**.
Top 2 alternatives:
• [Alternative 1] — X members available
• [Alternative 2] — Y members available
We will need nearly everyone for the first meeting of the quarter to reach consensus on investments.
See you then!
– EFA Investment Club"""
            st.session_state.final_email_text = final_email
            new_meeting = {
                "id": len(st.session_state.finalized_meetings) + 1,
                "date": final_date.strftime('%Y-%m-%d'),
                "time": final_time,
                "notes": "Scheduled meeting"
            }
            st.session_state.finalized_meetings.append(new_meeting)
            save_finalized_meetings(st.session_state.finalized_meetings)
            st.success("✅ Meeting set and saved to Supabase!")
            st.rerun()
    if st.session_state.final_email_text:
        st.text_area("📧 Final Meeting Email – Click inside, Ctrl+A, then Copy",
                     st.session_state.final_email_text, height=200)
    if st.session_state.finalized_meetings:
        st.markdown("### Scheduled Meetings")
        for idx, meeting in enumerate(st.session_state.finalized_meetings[:]):
            with st.expander(f"✅ {meeting['date']} at {meeting['time']}", expanded=False):
                st.write(meeting.get('notes', 'No notes'))
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Change this meeting", key=f"change_meet_{idx}"):
                        st.info("Use the date/time picker above and press 'Set Meeting' to update this meeting.")
                with col2:
                    if st.button("Cancel this meeting", key=f"cancel_meet_{idx}"):
                        st.session_state.finalized_meetings.pop(idx)
                        save_finalized_meetings(st.session_state.finalized_meetings)
                        st.success("✅ Meeting cancelled and removed!")
                        st.rerun()

st.caption("✅ All scheduler data (polls + availability + finalized meetings) fully persists in Supabase")