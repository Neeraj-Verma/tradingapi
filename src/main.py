"""
Zerodha Kite Trading Dashboard - Streamlit App
A web-based UI for trading operations using KiteTrader class.
Run with: streamlit run src/main.py
"""

import os
import sys
import webbrowser
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Ensure repo root is on sys.path (Streamlit often sets script dir as import root)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tips_research_agent.agent import generate_tips_research_data_csv

from src.kite_trader import KiteTrader, TraderConfig

# Load environment variables (prefer src/.env, then repo-root .env)
_src_env = REPO_ROOT / "src" / ".env"
_root_env = REPO_ROOT / ".env"
if _src_env.exists():
    load_dotenv(dotenv_path=_src_env, override=False)
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)

# Get API credentials
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Page configuration
st.set_page_config(
    page_title="Kite Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stButton>button { margin-bottom: 5px; }
    .metric-card { padding: 10px; border-radius: 5px; margin: 5px 0; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables"""
    if 'trader' not in st.session_state:
        config = TraderConfig.from_env()
        st.session_state.trader = KiteTrader(config)
    if 'logs' not in st.session_state:
        st.session_state.logs = []
    if 'access_token' not in st.session_state:
        st.session_state.access_token = ACCESS_TOKEN or ""
    if 'show_generate_flow' not in st.session_state:
        st.session_state.show_generate_flow = False


def add_log(message: str, level: str = "info"):
    """Add log message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.append({
        'time': timestamp,
        'level': level,
        'message': message
    })
    if len(st.session_state.logs) > 100:
        st.session_state.logs = st.session_state.logs[-100:]


def setup_trader_logging():
    """Setup trader to use our logging function"""
    st.session_state.trader.on_log = add_log


def display_sidebar() -> Dict:
    """Display sidebar with configuration"""
    trader = st.session_state.trader
    
    st.sidebar.title("⚙️ Configuration")
    
    # Connection status
    if trader.connected:
        st.sidebar.success(f"✅ Connected as {trader.user_name}")
        if st.sidebar.button("🔌 Disconnect"):
            trader.disconnect()
            st.rerun()
    else:
        st.sidebar.error("❌ Not Connected")
        
        if st.session_state.show_generate_flow:
            # Token generation flow
            st.sidebar.subheader("🔄 Generate Access Token")
            
            st.sidebar.markdown("**Step 1:** Click to open Kite login")
            if st.sidebar.button("🌐 Open Kite Login", width='stretch'):
                kite_temp = KiteConnect(api_key=API_KEY)
                login_url = kite_temp.login_url()
                webbrowser.open(login_url)
                st.sidebar.success("Browser opened!")
            
            st.sidebar.markdown("**Step 2:** Copy `request_token` from URL")
            st.sidebar.caption("URL: `...?request_token=XXXXX&action=login`")
            
            request_token = st.sidebar.text_input(
                "Request Token",
                placeholder="Paste request_token here"
            )
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("✅ Get Token", width='stretch'):
                    if request_token:
                        try:
                            kite_temp = KiteConnect(api_key=API_KEY)
                            data = kite_temp.generate_session(request_token, api_secret=API_SECRET)
                            access_token = data["access_token"]
                            st.session_state.access_token = access_token
                            
                            # Save to .env
                            env_path = os.path.join(os.path.dirname(__file__), '.env')
                            if os.path.exists(env_path):
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
                            
                            add_log("Access token generated!", "success")
                            st.session_state.show_generate_flow = False
                            trader.connect(access_token)
                            st.rerun()
                        except Exception as e:
                            add_log(f"Token generation failed: {e}", "error")
                            st.sidebar.error(str(e))
                    else:
                        st.sidebar.error("Enter request_token first")
            with col2:
                if st.button("❌ Cancel", width='stretch'):
                    st.session_state.show_generate_flow = False
                    st.rerun()
        else:
            # Normal connect flow
            st.sidebar.subheader("🔑 Enter Access Token")
            
            token_input = st.sidebar.text_input(
                "Access Token",
                value=st.session_state.access_token,
                type="password",
                placeholder="Paste your access token"
            )
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("🔌 Connect", width='stretch'):
                    if token_input:
                        if trader.connect(token_input):
                            st.session_state.access_token = token_input

                            # Persist token for other tools (ADK agents, CLI runs)
                            try:
                                env_path = os.path.join(os.path.dirname(__file__), '.env')
                                if os.path.exists(env_path):
                                    with open(env_path, 'r', encoding='utf-8') as f:
                                        content = f.read()
                                else:
                                    content = ""

                                if 'ACCESS_TOKEN=' in content:
                                    lines = content.split('\n')
                                    for i, line in enumerate(lines):
                                        if line.startswith('ACCESS_TOKEN='):
                                            lines[i] = f'ACCESS_TOKEN={token_input}'
                                    content = '\n'.join(lines)
                                else:
                                    if content and not content.endswith('\n'):
                                        content += '\n'
                                    content += f'ACCESS_TOKEN={token_input}\n'

                                with open(env_path, 'w', encoding='utf-8') as f:
                                    f.write(content)
                            except Exception as e:
                                add_log(f"Could not persist ACCESS_TOKEN to src/.env: {e}", "warning")

                            st.rerun()
                    else:
                        st.sidebar.error("Enter access token")
            with col2:
                if st.button("🔄 Generate", width='stretch'):
                    st.session_state.show_generate_flow = True
                    st.rerun()
    
    st.sidebar.divider()
    
    # Mode Settings
    st.sidebar.subheader("Mode Settings")
    
    live_mode = st.sidebar.toggle(
        "🔴 Live Mode",
        value=not trader.config.dry_run,
        help="Enable to execute real orders"
    )
    trader.config.dry_run = not live_mode
    
    qty_mode = st.sidebar.toggle(
        "📦 Quantity Mode",
        value=not trader.config.use_budget_mode,
        help="Use CSV quantities instead of budget"
    )
    trader.config.use_budget_mode = not qty_mode
    
    st.sidebar.divider()
    
    # Budget Settings
    st.sidebar.subheader("💰 Budget Settings")
    
    trader.config.daily_budget = float(st.sidebar.number_input(
        "Daily Budget (₹)",
        min_value=1000,
        max_value=10000000,
        value=int(trader.config.daily_budget),
        step=5000
    ))
    
    trader.config.per_stock_daily_budget = float(st.sidebar.number_input(
        "Per-Stock Budget (₹)",
        min_value=1000,
        max_value=1000000,
        value=int(trader.config.per_stock_daily_budget),
        step=5000
    ))
    
    trader.config.max_qty_per_stock = st.sidebar.number_input(
        "Max Qty per Stock",
        min_value=1,
        max_value=10000,
        value=trader.config.max_qty_per_stock,
        step=10
    )

    trader.config.base_order_qty = st.sidebar.number_input(
        "Base Order Qty (Phase 1)",
        min_value=1,
        max_value=100,
        value=trader.config.base_order_qty,
        step=1,
        help="Quantity per stock in Phase 1 (MARKET orders)"
    )

    trader.config.gtt_buy_budget_per_stock = float(st.sidebar.number_input(
        "GTT Buy Budget/Stock (₹)",
        min_value=1000,
        max_value=100000,
        value=int(trader.config.gtt_buy_budget_per_stock),
        step=1000,
        help="Min budget per GTT buy order (₹10k makes ₹15.34 brokerage worthwhile)"
    ))
    
    st.sidebar.divider()
    
    # File Settings
    st.sidebar.subheader("📁 File Settings")
    trader.config.order_book_file = st.sidebar.text_input(
        "Order Book File",
        value=trader.config.order_book_file
    )
    
    st.sidebar.subheader("🏷️ Rank Filter")
    rank_choice = st.sidebar.selectbox(
        "Trade/Display",
        options=["All", "Top5", "Top10", "Top15", "Top25"],
        index=0,
        help="Filter order book by Rank. Applies to Order Book tab and Tranche Strategy.",
    )
    rank_top_n = None
    if rank_choice.startswith("Top"):
        try:
            rank_top_n = int(rank_choice.replace("Top", ""))
        except Exception:
            rank_top_n = None
    
    # Market Status
    st.sidebar.divider()
    st.sidebar.subheader("🕐 Market Status")
    st.sidebar.write(f"Time: {datetime.now().strftime('%H:%M:%S')}")
    
    if trader.is_market_hours():
        st.sidebar.success("📈 Market OPEN")
    else:
        st.sidebar.warning("📉 Market CLOSED")
    
    # Return options
    return {
        'refresh': st.sidebar.toggle("🔄 Refresh Mode", value=False),
        'sliced': st.sidebar.toggle("🔪 Sliced Mode", value=False),
        'reprice_discount': st.sidebar.slider("Reprice Discount", 0.95, 1.0, 0.99, 0.01),
        'rank_top_n': rank_top_n,
    }


def display_order_book(options: Dict):
    """Display order book"""
    trader = st.session_state.trader
    
    st.subheader("📋 Order Book")
    
    orders = trader.read_order_book()
    if options.get('rank_top_n'):
        orders = [
            o for o in orders
            if trader._order_is_within_top_n(o.get('rank', ''), options['rank_top_n'])
        ]
    if not orders:
        suffix = f" (Top{options['rank_top_n']})" if options.get('rank_top_n') else ""
        st.warning(f"No orders found in {trader.config.order_book_file}{suffix}")
        return
    
    total_investment = sum(o['quantity'] * o['price'] for o in orders)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Stocks", len(orders))
    col2.metric("Total Investment", f"₹{total_investment:,.2f}")
    col3.metric("Daily Budget", f"₹{trader.config.daily_budget:,.2f}")
    
    df = pd.DataFrame(orders)
    st.dataframe(df, hide_index=True, use_container_width=True)


def display_holdings():
    """Display holdings"""
    trader = st.session_state.trader
    
    st.subheader("💼 Current Holdings")
    
    if not trader.connected:
        st.warning("Connect to Kite to view holdings")
        return
    
    try:
        holdings = trader.get_holdings()
        
        if not holdings:
            st.info("No holdings found")
            return
        
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
        
        summary = trader.get_portfolio_summary()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Stocks", summary['total_stocks'])
        col2.metric("Portfolio Value", f"₹{summary['total_value']:,.2f}")
        col3.metric("Total P&L", f"₹{summary['total_pnl']:,.2f}")
        col4.metric("P&L %", f"{summary['pnl_percent']:.2f}%")
        
        st.dataframe(df, hide_index=True, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")


def display_gtts():
    """Display GTT orders"""
    trader = st.session_state.trader
    
    st.subheader("📊 Active GTT Orders")
    
    if not trader.connected:
        st.warning("Connect to Kite to view GTTs")
        return
    
    try:
        gtts = trader.get_gtts()
        
        if not gtts:
            st.info("No active GTT orders")
            return
        
        sell_gtts = len([g for g in gtts if g.get('orders', [{}])[0].get('transaction_type') == 'SELL'])
        buy_gtts = len([g for g in gtts if g.get('orders', [{}])[0].get('transaction_type') == 'BUY'])
        
        col1, col2 = st.columns(2)
        col1.metric("Sell GTTs (Protection)", sell_gtts)
        col2.metric("Buy GTTs (Dip Accumulation)", buy_gtts)
        
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
        
        st.dataframe(df, hide_index=True, use_container_width=True)
    except Exception as e:
        st.error(f"Error: {e}")


def display_action_buttons(options: Dict):
    """Display action buttons"""
    trader = st.session_state.trader
    
    st.header("🎯 Trading Operations")
    
    # Warning banner
    if not trader.config.dry_run:
        st.error("⚠️ LIVE MODE - Real orders will be executed!")
    else:
        st.info("🔒 DRY RUN MODE - No real orders")
    
    # 4-column layout
    col1, col2, col3, col4 = st.columns(4)
    
    # Column 1: Buying
    with col1:
        st.subheader("📈 Buying")

        if trader.config.dry_run:
            if st.button("▶️ Run Tranche Strategy", type="primary", width='stretch', key="tranche_dry"):
                with st.spinner("Running (dry run)..."):
                    trader.run_tranche_strategy()
        else:
            if st.session_state.get('confirm_tranche'):
                st.warning("Live mode: confirm tranche strategy")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Confirm", type="primary", width='stretch', key="tranche_confirm"):
                        with st.spinner("Executing..."):
                            trader.run_tranche_strategy()
                        st.session_state.confirm_tranche = False
                        st.rerun()
                with c2:
                    if st.button("❌ Cancel", width='stretch', key="tranche_cancel"):
                        st.session_state.confirm_tranche = False
                        st.rerun()
            else:
                if st.button("▶️ Run Tranche Strategy", type="primary", width='stretch', key="tranche_arm"):
                    st.session_state.confirm_tranche = True
                    st.rerun()
        
        if st.button("🆕 Buy New Stocks", width='stretch'):
            with st.spinner("Processing..."):
                trader.buy_new_stocks()
        
        if st.button("🔄 Reprice Pending Buys", width='stretch'):
            with st.spinner("Repricing..."):
                trader.reprice_pending_limit_buys(options['reprice_discount'])
    
    # Column 2: Selling
    with col2:
        st.subheader("📉 Selling")

        if trader.config.dry_run:
            if st.button("🔴 Sell Negative P&L", width='stretch', key="sell_neg_dry"):
                with st.spinner("Selling (dry run)..."):
                    trader.sell_negative_holdings()
        else:
            if st.session_state.get('confirm_sell_neg'):
                st.warning("Live mode: confirm sell negative P&L")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Confirm", type="primary", width='stretch', key="sell_neg_confirm"):
                        with st.spinner("Selling..."):
                            trader.sell_negative_holdings()
                        st.session_state.confirm_sell_neg = False
                        st.rerun()
                with c2:
                    if st.button("❌ Cancel", width='stretch', key="sell_neg_cancel"):
                        st.session_state.confirm_sell_neg = False
                        st.rerun()
            else:
                if st.button("🔴 Sell Negative P&L", width='stretch', key="sell_neg_arm"):
                    st.session_state.confirm_sell_neg = True
                    st.rerun()
        

        if trader.config.dry_run:
            if st.button("⛔ Sell ALL Holdings", width='stretch', key="sell_all_dry"):
                with st.spinner("Selling ALL (dry run)..."):
                    trader.sell_all_holdings()
        else:
            if st.session_state.get('confirm_sell_all'):
                st.error("⚠️ DANGER: confirm SELL ALL")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Confirm SELL ALL", type="primary", width='stretch', key="sell_all_confirm"):
                        with st.spinner("Selling ALL..."):
                            trader.sell_all_holdings()
                        st.session_state.confirm_sell_all = False
                        st.rerun()
                with c2:
                    if st.button("❌ Cancel", width='stretch', key="sell_all_cancel"):
                        st.session_state.confirm_sell_all = False
                        st.rerun()
            else:
                if st.button("⛔ Sell ALL Holdings", width='stretch', key="sell_all_arm"):
                    st.session_state.confirm_sell_all = True
                    st.rerun()
        
        with st.expander("📝 Sell Specific Stock"):
            sell_symbol = st.text_input("Symbol", placeholder="RELIANCE", key="sell_sym")
            sell_qty = st.number_input("Quantity", min_value=1, value=1, key="sell_qty")
            sell_exchange = st.selectbox("Exchange", ["NSE", "BSE"], key="sell_ex")
            if st.button("Sell Stock", width='stretch'):
                if sell_symbol:
                    trader.sell_stock(sell_symbol.upper(), sell_qty, sell_exchange)
                else:
                    st.warning("Enter symbol")
    
    # Column 3: Protection
    with col3:
        st.subheader("🛡️ Protection")
        
        protect_label = "🛡️ Protect Holdings"
        if options.get('sliced'):
            protect_label += " (Sliced)"
        
        if st.button(protect_label, width='stretch'):
            with st.spinner("Protecting..."):
                if options.get('sliced'):
                    trader.protect_holdings_sliced(options.get('refresh', False))
                else:
                    trader.protect_holdings(options.get('refresh', False))
        
        if st.button("📉 Place GTT Buy Orders", width='stretch'):
            with st.spinner("Placing GTT buys..."):
                trader.place_gtt_buy_orders(options.get('refresh', False))
        

        if st.session_state.get('confirm_del_gtt'):
            st.warning("Confirm delete ALL BUY GTTs")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Confirm", type="primary", width='stretch', key="del_gtt_confirm"):
                    with st.spinner("Deleting..."):
                        trader.delete_existing_gtt_buys()
                    st.session_state.confirm_del_gtt = False
                    st.rerun()
            with c2:
                if st.button("❌ Cancel", width='stretch', key="del_gtt_cancel"):
                    st.session_state.confirm_del_gtt = False
                    st.rerun()
        else:
            if st.button("🗑️ Delete All BUY GTTs", width='stretch', key="del_gtt_arm"):
                st.session_state.confirm_del_gtt = True
                st.rerun()
    
    # Column 4: Utilities
    with col4:
        st.subheader("🔧 Utilities")

        if st.button("🧾 Generate Tips CSV", width='stretch'):
            # Ensure Kite creds are available for live LTP.
            # The generator prefers environment variables, so we set them from the connected session.
            if st.session_state.access_token:
                os.environ["ACCESS_TOKEN"] = st.session_state.access_token
            if API_KEY:
                os.environ["API_KEY"] = API_KEY

            with st.spinner("Generating data/tips_research_data.csv..."):
                result = generate_tips_research_data_csv(
                    top_n_rank=options.get('rank_top_n'),
                    daily_budget=trader.config.daily_budget,
                )

            if result.get("status") == "success":
                add_log(
                    f"Generated tips CSV: {result.get('output')} ({result.get('count')} rows, prices={result.get('price_source')})",
                    "success",
                )

                if result.get("price_source") != "kite_ltp":
                    ltp_error = result.get("ltp_error") or "Live prices not available (fell back to CSV prices)."
                    add_log(f"Tips used CSV prices (not Kite LTP): {ltp_error}", "warning")
                    st.warning(f"Tips prices were NOT updated from Kite LTP: {ltp_error}")

                with st.expander("📄 Preview tips_research_data.csv", expanded=False):
                    try:
                        df = pd.read_csv(result.get("output"))
                        st.dataframe(df, hide_index=True, use_container_width=True)
                    except Exception as e:
                        st.error(f"Unable to preview tips CSV: {e}")
            else:
                add_log(f"Tips CSV generation failed: {result.get('message', result)}", "error")
                st.error(result.get("message", "Tips CSV generation failed"))
        
        if st.button("💰 Update Prices in CSV", width='stretch'):
            with st.spinner("Updating..."):
                trader.update_order_book_prices()
        
        if st.button("🔌 Reconnect", width='stretch'):
            trader.disconnect()
            if st.session_state.access_token:
                trader.connect(st.session_state.access_token)
            st.rerun()
        
        if st.button("🗑️ Clear Logs", width='stretch'):
            st.session_state.logs = []
            st.rerun()


def display_logs():
    """Display logs"""
    st.subheader("📜 Operation Logs")
    
    if not st.session_state.logs:
        st.info("No logs yet")
        return
    
    for log in reversed(st.session_state.logs[-20:]):
        level = log['level']
        msg = f"[{log['time']}] {log['message']}"
        if level == 'error':
            st.error(msg)
        elif level == 'warning':
            st.warning(msg)
        elif level == 'success':
            st.success(msg)
        else:
            st.info(msg)


def display_strategy_info():
    """Display strategy information"""
    trader = st.session_state.trader
    
    with st.expander("ℹ️ Strategy Information"):
        st.markdown(f"""
        ### Tranche Buying Strategy
        
        **Phase 1: Base Orders**
        - Buy {trader.config.base_order_qty} shares of each stock at MARKET price
        
        **Phase 2: Hourly Tranches**
        - {trader.config.tranche_count} tranches, {int(trader.config.tranche_size*100)}% each
        - LIMIT orders at {(1-trader.config.ltp_discount)*100:.1f}% below LTP
        
        ### Protection Settings
        | Setting | Value |
        |---------|-------|
        | Stop Loss | {trader.config.stop_loss_percent*100:.0f}% below |
        | Target | {trader.config.target_percent*100:.0f}% above |
        | GTT Buy Lower | {trader.config.gtt_buy_lower_percent*100:.0f}% below |
        | GTT Buy Upper | {trader.config.gtt_buy_upper_percent*100:.0f}% below |
        | GTT Buy Budget/Stock | ₹{trader.config.gtt_buy_budget_per_stock:,.0f} |
        """)


def main():
    """Main application"""
    init_session_state()
    setup_trader_logging()
    
    # Title
    st.title("📈 Zerodha Kite Trading Dashboard")
    st.caption("Automated Trading with KiteTrader Class")
    
    # Sidebar
    options = display_sidebar()
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 Operations", "📋 Order Book", "💼 Holdings", "📊 GTT Orders"])
    
    with tab1:
        display_action_buttons(options)
        st.divider()
        display_logs()
        display_strategy_info()
    
    with tab2:
        display_order_book(options)
    
    with tab3:
        display_holdings()
    
    with tab4:
        display_gtts()


if __name__ == "__main__":
    main()
