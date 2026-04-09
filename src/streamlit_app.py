"""
Zerodha Kite Trading Dashboard - Streamlit App
A web-based UI for the buy_stocks.py trading operations.
Run with: streamlit run src/streamlit_app.py
"""

import os
import sys
import csv
import time
import webbrowser
import streamlit as st
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Add parent directory to path to import buy_stocks modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from buy_stocks.py after adding path
from src.buy_stocks import (
    # Configuration
    API_KEY, ACCESS_TOKEN, DRY_RUN, ORDER_BOOK_FILE,
    DAILY_BUDGET, PER_STOCK_DAILY_BUDGET, MAX_QTY_PER_STOCK,
    STOP_LOSS_PERCENT, TARGET_PERCENT, GTT_BUY_LOWER_PERCENT, GTT_BUY_UPPER_PERCENT,
    TRANCHE_COUNT, TRANCHE_SIZE, LTP_DISCOUNT, GTT_SLICES,
    CONFIG, Config,
    # Functions
    get_kite_client, validate_credentials, read_order_book,
    get_actual_holdings, get_todays_buy_orders, get_existing_gtts,
    batch_fetch_ltp, with_backoff,
    protect_existing_holdings, protect_existing_holdings_sliced,
    place_gtt_buy_orders_for_stocks, delete_existing_gtt_buys,
    delete_existing_gtts, get_existing_gtt_buy_symbols,
    update_order_book_prices, reprice_pending_limit_buy_orders,
    buy_new_stocks, find_new_stocks,
    run_base_price_orders, run_tranche_orders,
    initialize_tracker_from_orders, is_market_hours,
    _is_top15_rank, _compute_qty_from_budget,
    logger
)
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

# Get API_SECRET for token generation
API_SECRET = os.getenv("API_SECRET")

# Page configuration
st.set_page_config(
    page_title="Kite Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        margin-bottom: 5px;
    }
    .success-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .warning-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
    }
    .error-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .info-box {
        padding: 10px;
        border-radius: 5px;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    if 'kite' not in st.session_state:
        st.session_state.kite = None
    if 'connected' not in st.session_state:
        st.session_state.connected = False
    if 'logs' not in st.session_state:
        st.session_state.logs = []
    if 'last_operation' not in st.session_state:
        st.session_state.last_operation = None
    if 'operation_result' not in st.session_state:
        st.session_state.operation_result = None
    if 'access_token' not in st.session_state:
        st.session_state.access_token = ACCESS_TOKEN or ""
    if 'show_token_input' not in st.session_state:
        st.session_state.show_token_input = False
    if 'show_generate_flow' not in st.session_state:
        st.session_state.show_generate_flow = False
    if 'login_url' not in st.session_state:
        st.session_state.login_url = ""


def add_log(message: str, level: str = "info"):
    """Add a message to the log."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append({
        'time': timestamp,
        'level': level,
        'message': message
    })
    # Keep only last 100 logs
    if len(st.session_state.logs) > 100:
        st.session_state.logs = st.session_state.logs[-100:]


def connect_to_kite(token: str = None):
    """Establish connection to Kite API."""
    try:
        # Use provided token or session state token
        access_token = token or st.session_state.access_token
        
        if not API_KEY:
            add_log("API_KEY not found in .env file", "error")
            return False
        
        if not access_token:
            add_log("Access token is required", "error")
            return False
        
        # Store the token in session state
        st.session_state.access_token = access_token
        
        # Update environment variable for the kite module
        os.environ['ACCESS_TOKEN'] = access_token
        
        # Create Kite client with the token
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(access_token)
        
        # Validate by fetching profile
        profile = kite.profile()
        
        st.session_state.kite = kite
        st.session_state.connected = True
        st.session_state.show_token_input = False
        add_log(f"Successfully connected as {profile.get('user_name', 'User')}", "success")
        return True
    except Exception as e:
        add_log(f"Connection failed: {str(e)}", "error")
        st.session_state.connected = False
        return False


def display_sidebar():
    """Display sidebar with configuration options."""
    st.sidebar.title("⚙️ Configuration")
    
    # Connection status
    if st.session_state.connected:
        st.sidebar.success("✅ Connected to Kite")
        if st.sidebar.button("🔌 Disconnect"):
            st.session_state.connected = False
            st.session_state.kite = None
            add_log("Disconnected from Kite", "info")
            st.rerun()
    else:
        st.sidebar.error("❌ Not Connected")
        
        # Check if we're in generate token flow
        if st.session_state.show_generate_flow:
            st.sidebar.subheader("🔄 Generate Access Token")
            
            # Step 1: Show login URL
            st.sidebar.markdown("**Step 1:** Click to open Kite login")
            if st.sidebar.button("🌐 Open Kite Login", width='stretch'):
                kite_temp = KiteConnect(api_key=API_KEY)
                login_url = kite_temp.login_url()
                st.session_state.login_url = login_url
                webbrowser.open(login_url)
                st.sidebar.success("Browser opened!")
            
            # Step 2: Enter request token
            st.sidebar.markdown("**Step 2:** After login, copy `request_token` from URL")
            st.sidebar.caption("URL format: `...?request_token=XXXXX&action=login`")
            
            request_token = st.sidebar.text_input(
                "Request Token",
                placeholder="Paste request_token here",
                help="Copy from the redirect URL after login"
            )
            
            # Step 3: Generate access token (same logic as generate_token.py)
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("✅ Get Token", width='stretch'):
                    if request_token:
                        try:
                            kite_temp = KiteConnect(api_key=API_KEY)
                            data = kite_temp.generate_session(request_token, api_secret=API_SECRET)
                            access_token = data["access_token"]
                            st.session_state.access_token = access_token
                            
                            # Save to .env file (same path as generate_token.py)
                            env_path = os.path.join(os.path.dirname(__file__), '.env')
                            with open(env_path, 'r') as f:
                                content = f.read()
                            
                            if 'ACCESS_TOKEN=' in content:
                                lines = content.split('\n')
                                for i, line in enumerate(lines):
                                    if line.startswith('ACCESS_TOKEN='):
                                        lines[i] = f'ACCESS_TOKEN={access_token}'
                                content = '\n'.join(lines)
                            else:
                                content += f'\nACCESS_TOKEN={access_token}'
                            
                            with open(env_path, 'w') as f:
                                f.write(content)
                            
                            add_log("Access token generated and saved to .env!", "success")
                            st.session_state.show_generate_flow = False
                            # Auto-connect
                            connect_to_kite(access_token)
                            st.rerun()
                        except Exception as e:
                            add_log(f"Token generation failed: {str(e)}", "error")
                            st.sidebar.error(f"Error: {str(e)}")
                    else:
                        st.sidebar.error("Enter request_token first")
            with col2:
                if st.button("❌ Cancel", width='stretch'):
                    st.session_state.show_generate_flow = False
                    st.rerun()
        else:
            # Normal connection flow
            st.sidebar.subheader("🔑 Enter Access Token")
            
            token_input = st.sidebar.text_input(
                "Access Token",
                value=st.session_state.access_token,
                type="password",
                help="Enter your Kite access token",
                placeholder="Paste your access token here"
            )
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("🔌 Connect", width='stretch'):
                    if token_input:
                        connect_to_kite(token_input)
                        st.rerun()
                    else:
                        st.sidebar.error("Please enter access token")
            with col2:
                if st.button("🔄 Generate", width='stretch', help="Generate new token"):
                    st.session_state.show_generate_flow = True
                    st.rerun()
    
    st.sidebar.divider()
    
    # Mode Settings
    st.sidebar.subheader("Mode Settings")
    
    live_mode = st.sidebar.toggle(
        "🔴 Live Mode",
        value=not CONFIG.dry_run,
        help="Enable to execute real orders. Keep OFF for testing."
    )
    CONFIG.dry_run = not live_mode
    
    qty_mode = st.sidebar.toggle(
        "📦 Quantity Mode",
        value=not CONFIG.use_budget_mode,
        help="Use CSV quantities instead of budget-based calculation"
    )
    CONFIG.use_budget_mode = not qty_mode
    
    st.sidebar.divider()
    
    # Budget Settings
    st.sidebar.subheader("💰 Budget Settings")
    
    daily_budget = st.sidebar.number_input(
        "Daily Budget (₹)",
        min_value=1000,
        max_value=10000000,
        value=int(CONFIG.daily_budget),
        step=5000,
        help="Total budget for the day"
    )
    CONFIG.daily_budget = float(daily_budget)
    
    per_stock_budget = st.sidebar.number_input(
        "Per-Stock Budget (₹)",
        min_value=1000,
        max_value=1000000,
        value=int(CONFIG.per_stock_daily_budget),
        step=5000,
        help="Maximum budget per stock per day"
    )
    CONFIG.per_stock_daily_budget = float(per_stock_budget)
    
    max_qty = st.sidebar.number_input(
        "Max Qty per Stock",
        min_value=1,
        max_value=10000,
        value=CONFIG.max_qty_per_stock,
        step=10,
        help="Maximum shares to buy per stock"
    )
    CONFIG.max_qty_per_stock = max_qty
    
    st.sidebar.divider()
    
    # File Settings
    st.sidebar.subheader("📁 File Settings")
    
    order_file = st.sidebar.text_input(
        "Order Book File",
        value=CONFIG.order_book_file,
        help="Path to order book CSV file"
    )
    CONFIG.order_book_file = order_file
    
    # Display current time and market status
    st.sidebar.divider()
    st.sidebar.subheader("🕐 Market Status")
    now = datetime.now()
    st.sidebar.write(f"Current Time: {now.strftime('%H:%M:%S')}")
    
    if is_market_hours():
        st.sidebar.success("📈 Market is OPEN")
    else:
        st.sidebar.warning("📉 Market is CLOSED")
    
    return {
        'live_mode': live_mode,
        'qty_mode': qty_mode,
        'refresh': st.sidebar.toggle("🔄 Refresh Mode", value=False, help="Delete and recreate GTTs"),
        'sliced': st.sidebar.toggle("🔪 Sliced Mode", value=False, help="Use graduated SL/Target levels"),
        'reprice_discount': st.sidebar.slider("Reprice Discount", 0.95, 1.0, 0.99, 0.01)
    }


def display_order_book():
    """Display the order book in a table."""
    st.subheader("📋 Order Book")
    
    orders = read_order_book(CONFIG.order_book_file)
    if not orders:
        st.warning(f"No orders found in {CONFIG.order_book_file}")
        return
    
    # Calculate totals
    total_investment = sum(o['quantity'] * o['price'] for o in orders)
    
    # Create dataframe for display
    import pandas as pd
    df = pd.DataFrame(orders)
    if 'symbol' in df.columns:
        df = df[['symbol', 'quantity', 'price', 'product'] + [c for c in df.columns if c not in ['symbol', 'quantity', 'price', 'product']]]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Stocks", len(orders))
    with col2:
        st.metric("Total Investment", f"₹{total_investment:,.2f}")
    with col3:
        st.metric("Daily Budget", f"₹{CONFIG.daily_budget:,.2f}")
    
    st.dataframe(df, width='stretch', hide_index=True)


def display_holdings():
    """Display current holdings."""
    st.subheader("💼 Current Holdings")
    
    if not st.session_state.connected:
        st.warning("Connect to Kite to view holdings")
        return
    
    try:
        kite = st.session_state.kite
        # Use Kite API directly to get all holdings
        holdings = with_backoff(kite.holdings)
        
        if not holdings:
            st.info("No holdings found")
            return
        
        # Filter to only show stocks with quantity > 0
        holdings = [h for h in holdings if h.get('quantity', 0) > 0]
        
        if not holdings:
            st.info("No holdings found")
            return
        
        import pandas as pd
        df = pd.DataFrame([
            {
                'Symbol': h['tradingsymbol'],
                'Quantity': h['quantity'],
                'Avg. Price': f"₹{h['average_price']:,.2f}",
                'LTP': f"₹{h.get('last_price', 0):,.2f}",
                'P&L': f"₹{h.get('pnl', 0):,.2f}",
                'Day Change': f"{h.get('day_change_percentage', 0):.2f}%"
            }
            for h in holdings
        ])
        
        total_value = sum(h['quantity'] * h.get('last_price', h['average_price']) for h in holdings)
        total_pnl = sum(h.get('pnl', 0) for h in holdings)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Stocks", len(holdings))
        with col2:
            st.metric("Portfolio Value", f"₹{total_value:,.2f}")
        with col3:
            st.metric("Total P&L", f"₹{total_pnl:,.2f}")
        
        st.dataframe(df, width='stretch', hide_index=True)
    except Exception as e:
        st.error(f"Error fetching holdings: {str(e)}")


def display_gtts():
    """Display active GTT orders."""
    st.subheader("📊 Active GTT Orders")
    
    if not st.session_state.connected:
        st.warning("Connect to Kite to view GTTs")
        return
    
    try:
        kite = st.session_state.kite
        gtts = with_backoff(kite.get_gtts)
        
        if not gtts:
            st.info("No active GTT orders")
            return
        
        sell_gtts = [g for g in gtts if g.get('condition', {}).get('trigger_values')]
        buy_gtts = [g for g in gtts if 'buy' in str(g.get('orders', [{}])[0].get('transaction_type', '')).lower()]
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Sell GTTs (Protection)", len([g for g in gtts if g.get('type') == 'two-leg']))
        with col2:
            st.metric("Buy GTTs (Dip Accumulation)", len(buy_gtts))
        
        import pandas as pd
        df = pd.DataFrame([
            {
                'ID': g.get('id'),
                'Symbol': g.get('tradingsymbol'),
                'Type': g.get('type'),
                'Status': g.get('status'),
                'Triggers': str(g.get('condition', {}).get('trigger_values', [])),
                'Created': g.get('created_at', '')[:10] if g.get('created_at') else ''
            }
            for g in gtts
        ])
        
        st.dataframe(df, width='stretch', hide_index=True)
    except Exception as e:
        st.error(f"Error fetching GTTs: {str(e)}")


def run_tranche_strategy(options: dict):
    """Execute the main tranche buying strategy."""
    add_log("Starting Tranche Buying Strategy...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    if not CONFIG.dry_run and not is_market_hours():
        add_log("Market is closed. Cannot execute live orders.", "error")
        return False
    
    kite = st.session_state.kite
    orders = read_order_book(CONFIG.order_book_file)
    
    if not orders:
        add_log("No orders found in order book", "error")
        return False
    
    add_log(f"Found {len(orders)} stocks in order book", "info")
    
    # Initialize tracker
    symbols = [o['symbol'] for o in orders]
    bought_tracker, actual_spent = initialize_tracker_from_orders(kite, symbols)
    
    # Check if already complete
    all_complete = all(
        bought_tracker.get(o['symbol'], 0) >= o['quantity']
        for o in orders
    )
    
    if all_complete:
        add_log("All orders already complete from previous run!", "success")
        return True
    
    # Phase 1: Base orders
    stocks_needing_base = [o for o in orders if bought_tracker.get(o['symbol'], 0) < 1]
    if stocks_needing_base:
        add_log(f"Phase 1: Placing base orders for {len(stocks_needing_base)} stocks", "info")
        run_base_price_orders(kite, stocks_needing_base, bought_tracker, actual_spent)
    else:
        add_log("Phase 1: All base orders already placed", "info")
    
    # Phase 2: Tranches
    for tranche in range(1, TRANCHE_COUNT + 1):
        add_log(f"Phase 2: Executing tranche {tranche}/{TRANCHE_COUNT}", "info")
        tranches_remaining = TRANCHE_COUNT - tranche + 1
        run_tranche_orders(kite, orders, tranche, bought_tracker, tranches_remaining, actual_spent)
        
        if tranche < TRANCHE_COUNT and not CONFIG.dry_run:
            add_log(f"Waiting for next tranche...", "info")
            # In real scenarios, this would wait. For UI, we show progress
    
    add_log(f"Strategy complete. Total spent: ₹{actual_spent['total']:,.2f}", "success")
    return True


def run_protect_holdings(options: dict):
    """Protect existing holdings with GTT OCO orders."""
    add_log("Starting Holdings Protection...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    
    # Check existing GTTs
    existing_gtts = get_existing_gtts(kite)
    if existing_gtts:
        add_log(f"Found {len(existing_gtts)} existing GTT orders", "info")
        if options.get('refresh'):
            add_log("Refresh mode: Deleting existing GTTs...", "info")
            deleted = delete_existing_gtts(kite)
            add_log(f"Deleted {deleted} GTT orders", "info")
    
    # Run protection
    if options.get('sliced'):
        add_log("Using SLICED protection (multiple SL/Target levels)", "info")
        protect_existing_holdings_sliced(kite)
    else:
        add_log("Using standard GTT OCO protection", "info")
        protect_existing_holdings(kite)
    
    add_log("Holdings protection complete", "success")
    return True


def run_gtt_buy(options: dict):
    """Place GTT buy orders for dip accumulation."""
    add_log("Starting GTT Buy Orders for Dip Accumulation...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    
    # Get existing GTT buys
    existing_buy_gtts = get_existing_gtt_buy_symbols(kite)
    
    # Read orders
    orders = read_order_book(CONFIG.order_book_file)
    if not orders:
        add_log("No orders found in order book", "error")
        return False
    
    # Filter for Top15
    orders = [o for o in orders if _is_top15_rank(o.get('rank', ''))]
    if not orders:
        add_log("No Top15 stocks found", "warning")
        return False
    
    add_log(f"Found {len(orders)} Top15 stocks", "info")
    
    symbols_in_book = {o['symbol'] for o in orders}
    
    if options.get('refresh'):
        add_log("Refresh mode: Deleting existing BUY GTTs...", "info")
        deleted = delete_existing_gtt_buys(kite, symbols_to_refresh=symbols_in_book)
        add_log(f"Deleted {deleted} GTT orders", "info")
        existing_buy_gtts = set()
    else:
        # Skip existing
        before = len(orders)
        orders = [o for o in orders if o['symbol'] not in existing_buy_gtts]
        skipped = before - len(orders)
        if skipped > 0:
            add_log(f"Skipping {skipped} symbols with existing GTT BUYs", "info")
    
    if not orders:
        add_log("All stocks already have GTT BUY orders", "info")
        return True
    
    # Fetch LTPs
    symbols = [o['symbol'] for o in orders]
    add_log(f"Fetching prices for {len(symbols)} stocks...", "info")
    
    try:
        ltp_data = with_backoff(kite.ltp, ['NSE:' + s for s in symbols])
        stocks_data = []
        
        for order in orders:
            symbol = order['symbol']
            key = f"NSE:{symbol}"
            if key in ltp_data:
                ltp = ltp_data[key]['last_price']
                qty = int(order.get('quantity', 1))
                qty = min(qty, CONFIG.max_qty_per_stock) if CONFIG.max_qty_per_stock > 0 else qty
                
                if qty > 0:
                    stocks_data.append({
                        'symbol': symbol,
                        'quantity': qty,
                        'ltp': ltp,
                        'product': order.get('product', 'CNC'),
                        'allocation': float(order.get('allocation', 0.0) or 0.0)
                    })
        
        if stocks_data:
            place_gtt_buy_orders_for_stocks(kite, stocks_data)
            add_log(f"Placed GTT BUY orders for {len(stocks_data)} stocks", "success")
        else:
            add_log("No valid stock data for GTT BUY orders", "warning")
            
    except Exception as e:
        add_log(f"Error placing GTT BUY orders: {str(e)}", "error")
        return False
    
    return True


def run_delete_buy_gtts():
    """Delete all BUY-side GTTs."""
    add_log("Deleting all BUY-side GTTs...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    deleted = delete_existing_gtt_buys(kite, symbols_to_refresh=None)
    add_log(f"Deleted {deleted} BUY-side GTT(s)", "success")
    return True


def run_update_prices():
    """Update order book prices with current LTP."""
    add_log("Updating order book prices with current LTP...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    update_order_book_prices(kite, CONFIG.order_book_file)
    add_log("Order book prices updated", "success")
    return True


def run_reprice_pending_buys(discount: float):
    """Reprice pending LIMIT BUY orders."""
    add_log(f"Repricing pending LIMIT BUY orders with discount {discount}...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    reprice_pending_limit_buy_orders(kite, discount=discount)
    add_log("Pending orders repriced", "success")
    return True


def run_buy_new_stocks():
    """Buy new stocks from research data."""
    add_log("Buying new stocks from research data...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    research_file = "data/research_data.csv"
    buy_new_stocks(kite, research_file)
    add_log("New stocks purchase complete", "success")
    return True


def get_negative_holdings(kite):
    """Get holdings with negative P&L"""
    try:
        holdings = with_backoff(kite.holdings)
        negative_holdings = []
        
        for stock in holdings:
            pnl = stock.get('pnl', 0)
            quantity = stock.get('quantity', 0)
            
            if pnl < 0 and quantity > 0:
                negative_holdings.append({
                    'tradingsymbol': stock['tradingsymbol'],
                    'exchange': stock['exchange'],
                    'quantity': quantity,
                    'pnl': pnl,
                    'average_price': stock.get('average_price', 0),
                    'last_price': stock.get('last_price', 0)
                })
        
        return negative_holdings
    except Exception as e:
        add_log(f"Error fetching holdings: {e}", "error")
        return []


def sell_stock(kite, stock):
    """Place sell order for a stock"""
    try:
        order_params = {
            'tradingsymbol': stock['tradingsymbol'],
            'exchange': stock['exchange'],
            'transaction_type': kite.TRANSACTION_TYPE_SELL,
            'quantity': stock['quantity'],
            'order_type': kite.ORDER_TYPE_MARKET,
            'product': kite.PRODUCT_CNC,
            'variety': kite.VARIETY_REGULAR
        }
        
        if CONFIG.dry_run:
            add_log(f"[DRY RUN] Would sell: {stock['tradingsymbol']} x {stock['quantity']} (P&L: ₹{stock['pnl']:.2f})", "info")
            return None
        else:
            order_id = kite.place_order(**order_params)
            add_log(f"Sold: {stock['tradingsymbol']} x {stock['quantity']} - Order ID: {order_id}", "success")
            return order_id
            
    except Exception as e:
        add_log(f"Error selling {stock['tradingsymbol']}: {e}", "error")
        return None


def run_sell_negative_stocks():
    """Sell all stocks with negative P&L."""
    add_log("Selling stocks with negative P&L...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    negative_holdings = get_negative_holdings(kite)
    
    if not negative_holdings:
        add_log("No stocks with negative P&L found!", "info")
        return True
    
    total_loss = sum(h['pnl'] for h in negative_holdings)
    add_log(f"Found {len(negative_holdings)} stocks with total loss: ₹{total_loss:.2f}", "warning")
    
    orders_placed = 0
    for stock in negative_holdings:
        result = sell_stock(kite, stock)
        if result or CONFIG.dry_run:
            orders_placed += 1
    
    add_log(f"Processed {orders_placed}/{len(negative_holdings)} sell orders", "success")
    return True


def run_sell_all_holdings():
    """Sell all holdings."""
    add_log("Selling ALL holdings...", "warning")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    holdings = with_backoff(kite.holdings)
    holdings = [h for h in holdings if h.get('quantity', 0) > 0]
    
    if not holdings:
        add_log("No holdings to sell!", "info")
        return True
    
    total_value = sum(h['quantity'] * h.get('last_price', h['average_price']) for h in holdings)
    add_log(f"Selling {len(holdings)} stocks worth ₹{total_value:.2f}", "warning")
    
    orders_placed = 0
    for stock in holdings:
        stock_data = {
            'tradingsymbol': stock['tradingsymbol'],
            'exchange': stock['exchange'],
            'quantity': stock['quantity'],
            'pnl': stock.get('pnl', 0)
        }
        result = sell_stock(kite, stock_data)
        if result or CONFIG.dry_run:
            orders_placed += 1
    
    add_log(f"Processed {orders_placed}/{len(holdings)} sell orders", "success")
    return True


def run_sell_selected_stock(symbol: str, quantity: int, exchange: str = "NSE"):
    """Sell a specific stock."""
    add_log(f"Selling {symbol} x {quantity}...", "info")
    
    if not st.session_state.connected:
        add_log("Not connected to Kite", "error")
        return False
    
    kite = st.session_state.kite
    stock_data = {
        'tradingsymbol': symbol,
        'exchange': exchange,
        'quantity': quantity,
        'pnl': 0
    }
    
    result = sell_stock(kite, stock_data)
    return result is not None or CONFIG.dry_run


def display_action_buttons(options: dict):
    """Display main action buttons."""
    st.header("🎯 Trading Operations")
    
    # Warning banner
    if not CONFIG.dry_run:
        st.error("⚠️ LIVE MODE ENABLED - Real orders will be executed!")
    else:
        st.info("🔒 DRY RUN MODE - No real orders will be placed")
    
    # Main action buttons in columns
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.subheader("📈 Buying")
        
        if st.button("▶️ Run Tranche Strategy", type="primary", width='stretch'):
            if not CONFIG.dry_run:
                if st.session_state.get('confirm_tranche'):
                    with st.spinner("Executing tranche strategy..."):
                        run_tranche_strategy(options)
                    st.session_state.confirm_tranche = False
                else:
                    st.session_state.confirm_tranche = True
                    st.warning("Click again to confirm LIVE execution")
            else:
                with st.spinner("Running tranche strategy (dry run)..."):
                    run_tranche_strategy(options)
        
        if st.button("🆕 Buy New Stocks", width='stretch'):
            if not CONFIG.dry_run:
                st.warning("⚠️ This will buy 1 share of NEW stocks!")
            with st.spinner("Processing new stocks..."):
                run_buy_new_stocks()
        
        if st.button("🔄 Reprice Pending Buys", width='stretch'):
            with st.spinner("Repricing pending orders..."):
                run_reprice_pending_buys(options['reprice_discount'])
    
    with col2:
        st.subheader("📉 Selling")
        
        if st.button("🔴 Sell Negative P&L", width='stretch'):
            if not CONFIG.dry_run:
                if st.session_state.get('confirm_sell_negative'):
                    with st.spinner("Selling negative P&L stocks..."):
                        run_sell_negative_stocks()
                    st.session_state.confirm_sell_negative = False
                else:
                    st.session_state.confirm_sell_negative = True
                    st.warning("⚠️ Click again to confirm SELL")
            else:
                with st.spinner("Selling negative P&L stocks (dry run)..."):
                    run_sell_negative_stocks()
        
        if st.button("⛔ Sell ALL Holdings", width='stretch'):
            if not CONFIG.dry_run:
                if st.session_state.get('confirm_sell_all'):
                    with st.spinner("Selling ALL holdings..."):
                        run_sell_all_holdings()
                    st.session_state.confirm_sell_all = False
                else:
                    st.session_state.confirm_sell_all = True
                    st.error("⚠️ DANGER! Click again to SELL ALL")
            else:
                with st.spinner("Selling ALL holdings (dry run)..."):
                    run_sell_all_holdings()
        
        # Custom sell section
        with st.expander("📝 Sell Specific Stock"):
            sell_symbol = st.text_input("Symbol", placeholder="RELIANCE", key="sell_symbol")
            sell_qty = st.number_input("Quantity", min_value=1, value=1, key="sell_qty")
            sell_exchange = st.selectbox("Exchange", ["NSE", "BSE"], key="sell_exchange")
            if st.button("Sell Stock", width='stretch'):
                if sell_symbol:
                    run_sell_selected_stock(sell_symbol.upper(), sell_qty, sell_exchange)
                else:
                    st.warning("Enter a symbol")
    
    with col3:
        st.subheader("🛡️ Protection")
        
        protect_label = "🛡️ Protect Holdings"
        if options.get('sliced'):
            protect_label += " (Sliced)"
        if options.get('refresh'):
            protect_label += " [Refresh]"
        
        if st.button(protect_label, width='stretch'):
            with st.spinner("Protecting holdings..."):
                run_protect_holdings(options)
        
        gtt_buy_label = "📉 Place GTT Buy Orders"
        if options.get('refresh'):
            gtt_buy_label += " [Refresh]"
        
        if st.button(gtt_buy_label, width='stretch'):
            with st.spinner("Placing GTT buy orders..."):
                run_gtt_buy(options)
        
        if st.button("🗑️ Delete All BUY GTTs", width='stretch'):
            if st.session_state.get('confirm_delete'):
                with st.spinner("Deleting BUY GTTs..."):
                    run_delete_buy_gtts()
                st.session_state.confirm_delete = False
            else:
                st.session_state.confirm_delete = True
                st.warning("Click again to confirm deletion")
    
    with col4:
        st.subheader("🔧 Utilities")
        
        if st.button("💰 Update Prices in CSV", width='stretch'):
            with st.spinner("Updating prices..."):
                run_update_prices()
        
        if st.button("🔌 Reconnect to Kite", width='stretch'):
            st.session_state.connected = False
            connect_to_kite()
            st.rerun()
        
        if st.button("🗑️ Clear Logs", width='stretch'):
            st.session_state.logs = []
            st.rerun()


def display_logs():
    """Display operation logs."""
    st.subheader("📜 Operation Logs")
    
    if not st.session_state.logs:
        st.info("No logs yet. Perform an operation to see logs.")
        return
    
    # Show logs in reverse order (newest first)
    for log in reversed(st.session_state.logs[-20:]):
        level = log['level']
        if level == 'error':
            st.error(f"[{log['time']}] {log['message']}")
        elif level == 'warning':
            st.warning(f"[{log['time']}] {log['message']}")
        elif level == 'success':
            st.success(f"[{log['time']}] {log['message']}")
        else:
            st.info(f"[{log['time']}] {log['message']}")


def display_strategy_info():
    """Display information about the trading strategy."""
    with st.expander("ℹ️ Strategy Information", expanded=False):
        st.markdown(f"""
        ### Tranche Buying Strategy
        
        **Phase 1: Base Orders**
        - Buy 1 share of each stock at MARKET price
        - Establishes base position in each stock
        
        **Phase 2: Hourly Tranches**
        - {TRANCHE_COUNT} tranches, each buying {int(TRANCHE_SIZE*100)}% of remaining quantity
        - LIMIT orders at {(1-LTP_DISCOUNT)*100:.1f}% below LTP
        
        ### Protection Settings
        
        | Setting | Value |
        |---------|-------|
        | Stop Loss | {STOP_LOSS_PERCENT*100:.0f}% below cost |
        | Target | {TARGET_PERCENT*100:.0f}% above cost |
        | GTT Buy Lower | {GTT_BUY_LOWER_PERCENT*100:.0f}% below LTP |
        | GTT Buy Upper | {GTT_BUY_UPPER_PERCENT*100:.0f}% below LTP |
        
        ### Sliced GTT OCO Configuration
        """)
        
        for i, (qty_pct, sl_pct, tgt_pct) in enumerate(GTT_SLICES, 1):
            st.markdown(f"- **Slice {i}:** {qty_pct*100:.0f}% qty → SL -{sl_pct*100:.0f}% / Target +{tgt_pct*100:.0f}%")


def main():
    """Main application entry point."""
    init_session_state()
    
    # Title
    st.title("📈 Zerodha Kite Trading Dashboard")
    st.caption("Automated Tranche Buying Strategy with GTT Protection")
    
    # Sidebar
    options = display_sidebar()
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Operations", "📋 Order Book", "💼 Holdings", "📊 GTT Orders"])
    
    with tab1:
        display_action_buttons(options)
        st.divider()
        display_logs()
        display_strategy_info()
    
    with tab2:
        display_order_book()
    
    with tab3:
        display_holdings()
    
    with tab4:
        display_gtts()


if __name__ == "__main__":
    main()
