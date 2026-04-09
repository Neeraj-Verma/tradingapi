"""
Zerodha Kite Trading Dashboard V2 - Risk-Managed Edition
A web-based UI for trading with portfolio risk controls.
Run with: streamlit run src/main_v2.py
"""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kite_trader_v2 import KiteTraderV2, TraderConfigV2, RiskConfig

# Try to import tips_research_agent (optional)
try:
    from tips_research_agent.agent import generate_tips_research_data_csv
    TIPS_AGENT_AVAILABLE = True
except ImportError:
    TIPS_AGENT_AVAILABLE = False

# Try to import advisor_agent (optional)
try:
    from advisor_agent.agent import read_tips_csv, analyze_single_stock, update_recommendations, generate_advisor_report
    ADVISOR_AGENT_AVAILABLE = True
except ImportError:
    ADVISOR_AGENT_AVAILABLE = False

# Try to import market_agent (optional)
try:
    from src.market_agent import MarketAgent, run_market_analysis, MARKET_WATCHLIST
    MARKET_AGENT_AVAILABLE = True
except ImportError:
    try:
        from market_agent import MarketAgent, run_market_analysis, MARKET_WATCHLIST
        MARKET_AGENT_AVAILABLE = True
    except ImportError:
        MARKET_AGENT_AVAILABLE = False

# Load environment variables
_src_env = REPO_ROOT / "src" / ".env"
_root_env = REPO_ROOT / ".env"
if _src_env.exists():
    load_dotenv(dotenv_path=_src_env, override=False)
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Page configuration
st.set_page_config(
    page_title="Kite Trading V2 - Risk Managed",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .risk-ok { background-color: #d4edda; padding: 10px; border-radius: 5px; margin: 5px 0; }
    .risk-warn { background-color: #fff3cd; padding: 10px; border-radius: 5px; margin: 5px 0; }
    .risk-danger { background-color: #f8d7da; padding: 10px; border-radius: 5px; margin: 5px 0; }
    .metric-card { padding: 15px; border-radius: 10px; margin: 10px 0; }
    .stButton>button { margin-bottom: 5px; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables"""
    if 'trader' not in st.session_state:
        config = TraderConfigV2.from_env()
        st.session_state.trader = KiteTraderV2(config)
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
    
    st.sidebar.title("🛡️ V2 Risk-Managed Trading")
    
    # Connection status
    if trader.connected:
        st.sidebar.success(f"✅ Connected as {trader.user_name}")
        if st.sidebar.button("🔌 Disconnect"):
            trader.disconnect()
            st.rerun()
    else:
        st.sidebar.error("❌ Not Connected")
        
        if st.session_state.show_generate_flow:
            st.sidebar.subheader("🔄 Generate Access Token")
            st.sidebar.markdown("**Step 1:** Click to open Kite login")
            if st.sidebar.button("🌐 Open Kite Login", width='stretch'):
                kite_temp = KiteConnect(api_key=API_KEY)
                login_url = kite_temp.login_url()
                webbrowser.open(login_url)
                st.sidebar.success("Browser opened!")
            
            st.sidebar.markdown("**Step 2:** Copy `request_token` from URL")
            request_token = st.sidebar.text_input("Request Token", placeholder="Paste request_token here")
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("✅ Get Token", width='stretch'):
                    if request_token:
                        try:
                            kite_temp = KiteConnect(api_key=API_KEY)
                            data = kite_temp.generate_session(request_token, api_secret=API_SECRET)
                            access_token = data["access_token"]
                            st.session_state.access_token = access_token
                            
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
                            st.sidebar.error(str(e))
            with col2:
                if st.button("❌ Cancel", width='stretch'):
                    st.session_state.show_generate_flow = False
                    st.rerun()
        else:
            st.sidebar.subheader("🔑 Enter Access Token")
            token_input = st.sidebar.text_input("Access Token", value=st.session_state.access_token, type="password")
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("🔌 Connect", width='stretch'):
                    if token_input:
                        if trader.connect(token_input):
                            st.session_state.access_token = token_input
                            
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
                                add_log(f"Could not persist ACCESS_TOKEN: {e}", "warning")
                            
                            st.rerun()
            with col2:
                if st.button("🔄 Generate", width='stretch'):
                    st.session_state.show_generate_flow = True
                    st.rerun()
    
    st.sidebar.divider()
    
    # Mode Settings
    st.sidebar.subheader("⚙️ Mode Settings")
    
    live_mode = st.sidebar.toggle(
        "🔴 Live Mode",
        value=not trader.config.dry_run,
        help="""**DRY RUN vs LIVE MODE**

🔒 **OFF (Dry Run)**: Orders are simulated only. No real money is used. Use this to test strategies safely.

⚠️ **ON (Live)**: REAL orders will be placed with your broker. Real money at risk!

**Best Practice**: Always test new strategies in Dry Run mode first."""
    )
    trader.config.dry_run = not live_mode
    
    st.sidebar.divider()
    
    # Risk Settings
    st.sidebar.subheader("🛡️ Risk Controls")
    
    trader.config.risk.max_sector_exposure = st.sidebar.slider(
        "Max Sector Exposure",
        0.10, 0.50, trader.config.risk.max_sector_exposure, 0.05,
        help="""**SECTOR CONCENTRATION RISK**

Limits how much of your portfolio can be in any single sector (IT, Banking, Pharma, etc.).

**Why it matters**: If IT sector crashes 20%, and you have 50% in IT stocks, your portfolio drops 10%. With 30% limit, damage is only 6%.

**Recommended**: 25-30% for diversification.

**Example**: Portfolio ₹10L, IT stocks ₹3L = 30% exposure. Can't buy more IT stocks."""
    )
    
    trader.config.risk.max_drawdown_limit = st.sidebar.slider(
        "Max Drawdown Limit",
        0.05, 0.20, trader.config.risk.max_drawdown_limit, 0.01,
        help="""**DRAWDOWN PROTECTION**

Drawdown = How much your portfolio has fallen from its peak value.

**Formula**: (Peak - Current) / Peak

**How it works**: If portfolio drops below this limit, ALL buying stops until recovery.

**Why**: Prevents 'revenge trading' when losing. A 50% loss requires 100% gain to recover!

**Recovery math**:
- 10% loss → need 11% gain
- 20% loss → need 25% gain
- 50% loss → need 100% gain

**Recommended**: 10% for conservative, 15% for moderate."""
    )
    
    trader.config.risk.max_stocks_per_sector = st.sidebar.number_input(
        "Max Stocks/Sector",
        1, 10, trader.config.risk.max_stocks_per_sector,
        help="""**STOCK DIVERSIFICATION**

Maximum number of different stocks you can hold in one sector.

**Why**: Even within a sector, stocks can move differently. But holding 10 IT stocks isn't much better than 3—they're still correlated.

**Example**: With limit=3, you can hold HDFCBANK, ICICIBANK, SBIN (Banking), but not KOTAKBANK until you sell one.

**Recommended**: 2-3 per sector for good diversification without over-spreading."""
    )
    
    st.sidebar.divider()
    
    # Momentum Filter
    st.sidebar.subheader("📈 Momentum Filter")
    
    trader.config.risk.require_above_50dma = st.sidebar.checkbox(
        "Require > 50 DMA",
        value=trader.config.risk.require_above_50dma,
        help="""**50-DAY MOVING AVERAGE FILTER**

DMA = Average of last 50 days' closing prices. Smooths out noise to show the trend.

**The Rule**: Only buy stocks trading ABOVE their 50 DMA.

**Why**:
- Price > 50 DMA = Stock is in UPTREND (buyers in control)
- Price < 50 DMA = Stock is in DOWNTREND (sellers in control)

**Philosophy**: 'The trend is your friend.' Don't fight the market—buy what's already going up.

**Avoids**: 'Catching falling knives' (buying stocks that keep falling).

**Recommended**: Keep ON for trend-following strategy."""
    )
    
    trader.config.risk.require_above_200dma = st.sidebar.checkbox(
        "Require > 200 DMA",
        value=trader.config.risk.require_above_200dma,
        help="""**200-DAY MOVING AVERAGE FILTER (Stricter)**

200 DMA is the gold standard for identifying long-term trends.

**Market Wisdom**:
- Price > 200 DMA = BULL MARKET for that stock
- Price < 200 DMA = BEAR MARKET for that stock

**Famous Signals**:
- 'Golden Cross': 50 DMA crosses ABOVE 200 DMA → Strong BUY signal
- 'Death Cross': 50 DMA crosses BELOW 200 DMA → Strong SELL signal

**When to use**: Enable during uncertain markets for extra safety. Disable in strong bull markets to catch more opportunities.

**Trade-off**: Stricter filter = fewer trades but higher quality."""
    )
    
    st.sidebar.divider()
    
    # ATR Stop Loss
    st.sidebar.subheader("📉 Dynamic Stop Loss")
    
    trader.config.risk.use_atr_stop_loss = st.sidebar.checkbox(
        "Use ATR-Based SL",
        value=trader.config.risk.use_atr_stop_loss,
        help="""**ATR = Average True Range (Volatility Measure)**

ATR tells you how much a stock typically moves in a day.

**Problem with Fixed % Stop Loss**:
- Stock A: Moves ₹2/day → 8% SL gives 4 days of buffer
- Stock B: Moves ₹8/day → 8% SL gives only 1 day of buffer
- Stock B gets stopped out by normal movement!

**Solution**: ATR-based stop loss adapts to each stock's volatility.
- Volatile stocks → Wider stop loss
- Stable stocks → Tighter stop loss

**Formula**: Stop Loss = Entry Price - (ATR × Multiple)

**Recommended**: Keep ON for intelligent risk management."""
    )
    
    if trader.config.risk.use_atr_stop_loss:
        trader.config.risk.atr_sl_multiple = st.sidebar.slider(
            "ATR Multiple",
            1.0, 4.0, trader.config.risk.atr_sl_multiple, 0.5,
            help="""**ATR MULTIPLE SELECTION**

How many 'average daily moves' to allow before stop loss triggers.

**Formula**: SL Distance = ATR × This Multiple

**Example** (Stock with ATR = ₹5):
- 1.0× = ₹5 buffer (tight, frequent stops)
- 2.0× = ₹10 buffer (balanced)
- 3.0× = ₹15 buffer (loose, fewer stops)

**Guidelines**:
- 1.0-1.5×: Day/swing trading (tight risk)
- **2.0×**: Position trading (recommended)
- 3.0-4.0×: Long-term investing (wide tolerance)

**Trade-off**: Higher multiple = fewer false stops but larger losses when hit."""
        )
    
    st.sidebar.divider()
    
    # Exit Strategy
    st.sidebar.subheader("🎯 Exit Strategy")
    
    trader.config.risk.enable_trailing_stop = st.sidebar.checkbox(
        "Enable Trailing Stop",
        value=trader.config.risk.enable_trailing_stop,
        help="""**TRAILING STOP = PROFIT PROTECTION**

A trailing stop 'follows' the price up, locking in profits.

**Problem**: Fixed stop loss doesn't protect profits. Stock goes from ₹100 → ₹150 → back to ₹92 (your SL). You lose money despite being right!

**Solution**: Trail the stop loss upward as price rises.

**How it works**:
1. Buy at ₹100, initial SL at ₹92
2. Price rises to ₹120 → Trail stop moves to ₹114
3. Price rises to ₹150 → Trail stop moves to ₹142.50
4. Price drops to ₹142 → SELL triggered
5. Profit: ₹42 (42%) instead of potential ₹0

**Key benefit**: 'Let winners run, cut losers short.'"""
    )
    
    if trader.config.risk.enable_trailing_stop:
        trader.config.risk.trailing_activation_pct = st.sidebar.slider(
            "Activate After Gain %",
            0.05, 0.15, trader.config.risk.trailing_activation_pct, 0.01,
            format="%.0f%%",
            help="""**TRAILING STOP ACTIVATION THRESHOLD**

The stock must gain THIS MUCH before trailing stop kicks in.

**Why not trail immediately?**
- Small gains often reverse (noise)
- Waiting for +8% confirms you have a real winner
- Prevents whipsaw exits on minor fluctuations

**Example** (8% activation):
- Buy at ₹100
- Stock at ₹105 (+5%) → Trailing NOT active yet
- Stock at ₹108 (+8%) → Trailing ACTIVATES, tracking peak

**Guidelines**:
- 5%: Aggressive (start trailing early)
- **8%**: Balanced (recommended)
- 10-15%: Conservative (only trail big winners)"""
        )
        trader.config.risk.trailing_stop_pct = st.sidebar.slider(
            "Trail Distance %",
            0.02, 0.10, trader.config.risk.trailing_stop_pct, 0.01,
            help="""**TRAIL DISTANCE (How tight to follow)**

How far below the PEAK PRICE the trailing stop sits.

**Example** (5% trail):
- Peak price = ₹150
- Trail stop = ₹150 × 0.95 = ₹142.50
- If price drops to ₹142.50 → SELL triggered

**Trade-off**:
- Tight (2-3%): Locks more profit, but exits on minor dips
- **Medium (5%)**: Balanced (recommended)
- Loose (8-10%): Allows bigger pullbacks, but keeps less profit

**Tip**: Match trail distance to ATR. If stock moves 3%/day normally, trail at 5% to avoid noise."""
        )
    
    trader.config.risk.enable_partial_exit = st.sidebar.checkbox(
        "Enable Partial Exit",
        value=trader.config.risk.enable_partial_exit,
        help="""**PARTIAL PROFIT BOOKING**

Sell PART of your position at a profit target, let the rest ride.

**Strategy**: 'You can't go broke taking profits.'

**How it works** (50% partial at +10%):
- Buy 100 shares at ₹100
- Price hits ₹110 (+10%)
- SELL 50 shares (book ₹500 profit)
- Keep 50 shares running with trailing stop

**Benefits**:
- Guarantees SOME profit even if stock reverses
- Reduces psychological pressure ('at least I got something')
- Remaining shares ride with 'house money'

**Psychology**: Easier to hold through dips when you've already banked profit."""
    )
    
    if trader.config.risk.enable_partial_exit:
        trader.config.risk.partial_exit_trigger_pct = st.sidebar.slider(
            "Partial Exit at Gain %",
            0.05, 0.20, trader.config.risk.partial_exit_trigger_pct, 0.01,
            help="""**PARTIAL EXIT TRIGGER POINT**

At what gain % to book partial profits.

**Example** (10% trigger, 50% exit):
- Buy 100 shares at ₹100 = ₹10,000 invested
- Price hits ₹110 (+10%)
- Sell 50 shares at ₹110 = ₹5,500 received
- Profit booked: ₹500
- Remaining: 50 shares (cost basis effectively ₹90/share)

**Guidelines**:
- 5-7%: Book early, safer
- **10%**: Balanced (recommended)
- 15-20%: Let it run longer, riskier

**Math**: If you book 50% at +10%, your breakeven on remaining shares improves. Even if stock returns to entry, you're still profitable!"""
        )
    
    st.sidebar.divider()
    
    # Budget Settings
    st.sidebar.subheader("💰 Budget Settings")
    
    trader.config.daily_budget = float(st.sidebar.number_input(
        "Daily Budget (₹)",
        1000, 10000000, int(trader.config.daily_budget), 5000
    ))
    
    trader.config.per_stock_daily_budget = float(st.sidebar.number_input(
        "Per-Stock Budget (₹)",
        1000, 100000, int(trader.config.per_stock_daily_budget), 1000
    ))
    
    trader.config.max_qty_per_stock = st.sidebar.number_input(
        "Max Qty/Stock",
        1, 1000, trader.config.max_qty_per_stock, 50,
        help="""**MAXIMUM SHARES PER STOCK**

Caps the number of shares you can buy of any single stock.

**Why needed?**
Cheap stocks (price ₹20-50) can result in huge quantities.

**Example** (Budget ₹10,000):
- TCS at ₹4,000 → 2 shares (no cap needed)
- Penny stock at ₹20 → 500 shares (needs cap!)

**Risk**: Holding 1,000 shares of a ₹20 stock means ₹1,000 gain/loss per ₹1 move!

**Recommended**: 500 for retail traders. Handles most scenarios while preventing over-exposure to low-price stocks."""
    )
    
    trader.config.gtt_buy_budget_per_stock = float(st.sidebar.number_input(
        "GTT Buy Budget/Stock (₹)",
        1000, 100000, int(trader.config.gtt_buy_budget_per_stock), 1000,
        help="""**GTT DIP-BUY BUDGET**

Budget allocated per GTT (Good Till Triggered) buy order.

**What is GTT Dip-Buy?**
A standing order to automatically buy if a stock drops to a lower price.

**Example** (GTT Budget ₹10,000, 5% dip):
- HDFCBANK current: ₹1,700
- GTT trigger: ₹1,615 (-5%)
- If price hits ₹1,615 → Auto-buy ₹10,000/₹1,615 = 6 shares

**Use case**: Accumulate quality stocks on temporary dips without monitoring constantly.

**Important**: Only place GTT dip-buys on stocks already above their DMA (in uptrend). Dip-buying downtrending stocks = catching falling knives!"""
    ))
    
    st.sidebar.divider()
    
    # Market Status
    st.sidebar.subheader("🕐 Market Status")
    st.sidebar.write(f"Time: {datetime.now().strftime('%H:%M:%S')}")
    
    if trader.is_market_hours():
        st.sidebar.success("📈 Market OPEN")
    else:
        st.sidebar.warning("📉 Market CLOSED")
    
    # Cache control
    if st.sidebar.button("🔄 Refresh Data Cache", width='stretch'):
        trader.clear_analysis_cache()
        st.sidebar.success("Cache cleared!")
    
    return {'refresh': st.sidebar.toggle("🔄 Refresh Mode", value=False)}


def display_risk_dashboard():
    """Display portfolio risk dashboard"""
    trader = st.session_state.trader
    
    st.header("🛡️ Risk Dashboard")
    
    if not trader.connected:
        st.warning("Connect to Kite to view risk metrics")
        return
    
    summary = trader.get_portfolio_summary()
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Stocks", summary['total_stocks'])
    
    with col2:
        st.metric("Portfolio Value", f"₹{summary['total_value']:,.0f}")
    
    with col3:
        pnl_color = "normal" if summary['total_pnl'] >= 0 else "inverse"
        st.metric("Total P&L", f"₹{summary['total_pnl']:,.0f}", 
                  f"{summary['pnl_percent']:.1f}%", delta_color=pnl_color)
    
    with col4:
        drawdown_pct = summary['current_drawdown'] * 100
        limit_pct = trader.config.risk.max_drawdown_limit * 100
        if drawdown_pct >= limit_pct:
            st.metric("Drawdown", f"{drawdown_pct:.1f}%", "LIMIT REACHED", delta_color="inverse")
        elif drawdown_pct >= limit_pct * 0.7:
            st.metric("Drawdown", f"{drawdown_pct:.1f}%", "NEAR LIMIT", delta_color="off")
        else:
            st.metric("Drawdown", f"{drawdown_pct:.1f}%", "OK")
    
    st.divider()
    
    # Sector exposure
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏢 Sector Exposure")
        
        if summary['sector_exposure']:
            sector_df = pd.DataFrame([
                {
                    'Sector': sector,
                    'Exposure': f"{exp:.1%}",
                    'Stocks': summary['sector_counts'].get(sector, 0),
                    'Status': '⚠️ Over' if exp > trader.config.risk.max_sector_exposure else '✅ OK'
                }
                for sector, exp in sorted(summary['sector_exposure'].items(), key=lambda x: -x[1])
            ])
            st.dataframe(sector_df, hide_index=True, width='stretch')
            
            # Warning for over-exposed sectors
            over_exposed = [s for s, e in summary['sector_exposure'].items() 
                          if e > trader.config.risk.max_sector_exposure]
            if over_exposed:
                st.error(f"⚠️ Over-exposed sectors: {', '.join(over_exposed)}")
        else:
            st.info("No sector data available")
    
    with col2:
        st.subheader("📊 Risk Status")
        
        # Drawdown status
        drawdown_ok = summary['current_drawdown'] < trader.config.risk.max_drawdown_limit
        st.markdown(f"""
        **Drawdown Protection:**  
        {'✅' if drawdown_ok else '❌'} Current: {summary['current_drawdown']:.1%} | Limit: {trader.config.risk.max_drawdown_limit:.1%}
        """)
        
        # Sector status
        max_sector = summary.get('max_sector', 0)
        sector_ok = max_sector <= trader.config.risk.max_sector_exposure
        st.markdown(f"""
        **Sector Concentration:**  
        {'✅' if sector_ok else '⚠️'} Max: {max_sector:.1%} | Limit: {trader.config.risk.max_sector_exposure:.1%}
        """)
        
        # Count stocks below DMA
        holdings = trader.get_holdings()
        below_50dma = 0
        for h in holdings:
            analysis = trader.analyze_stock(h['tradingsymbol'], h.get('last_price', 0))
            if not analysis.above_50dma:
                below_50dma += 1
        
        st.markdown(f"""
        **Momentum Health:**  
        {'✅' if below_50dma == 0 else '⚠️'} Stocks below 50 DMA: {below_50dma}/{len(holdings)}
        """)
        
        # Trailing stop candidates
        trailing_candidates = len([h for h in holdings 
                                   if h['average_price'] > 0 and 
                                   h.get('last_price', 0) > h['average_price'] * (1 + trader.config.risk.trailing_activation_pct)])
        st.markdown(f"""
        **Big Winners (>8% gain):**  
        💰 {trailing_candidates} stocks eligible for trailing stop
        """)


def display_holdings_analysis():
    """Display holdings with analysis"""
    trader = st.session_state.trader
    
    st.subheader("📊 Holdings Analysis")
    
    if not trader.connected:
        st.warning("Connect to view holdings")
        return
    
    holdings = trader.get_holdings()
    
    if not holdings:
        st.info("No holdings found")
        return
    
    # Analyze each holding
    rows = []
    for h in holdings:
        analysis = trader.analyze_stock(h['tradingsymbol'], h.get('last_price', 0))
        
        avg_price = h['average_price']
        ltp = h.get('last_price', 0)
        gain_pct = ((ltp - avg_price) / avg_price * 100) if avg_price > 0 else 0
        
        rows.append({
            'Symbol': h['tradingsymbol'],
            'Sector': analysis.sector,
            'Qty': h['quantity'],
            'Avg Price': f"₹{avg_price:,.2f}",
            'LTP': f"₹{ltp:,.2f}",
            'P&L': f"₹{h.get('pnl', 0):,.0f}",
            'Gain %': f"{gain_pct:+.1f}%",
            '50 DMA': '✅' if analysis.above_50dma else '❌',
            '200 DMA': '✅' if analysis.above_200dma else '❌',
            'ATR SL': f"{analysis.suggested_sl_pct:.1%}",
        })
    
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width='stretch')


def display_stock_analyzer():
    """Display single stock analysis tool"""
    trader = st.session_state.trader
    
    st.subheader("🔍 Analyze Stock")
    
    if not trader.connected:
        st.warning("Connect to analyze stocks")
        return
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        symbol = st.text_input("Enter Symbol", placeholder="e.g., HDFCBANK").upper()
    
    with col2:
        st.write("")
        st.write("")
        analyze_btn = st.button("🔍 Analyze", width='stretch')
    
    if analyze_btn and symbol:
        with st.spinner(f"Analyzing {symbol}..."):
            analysis = trader.analyze_stock(symbol)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("LTP", f"₹{analysis.ltp:,.2f}" if analysis.ltp else "N/A")
            
            with col2:
                st.metric("Sector", analysis.sector)
            
            with col3:
                dma_50_label = f"₹{analysis.dma_50:,.2f}" if analysis.dma_50 else "N/A"
                st.metric("50 DMA", dma_50_label, 
                          "Above ✅" if analysis.above_50dma else "Below ❌")
            
            with col4:
                st.metric("ATR-Based SL", f"{analysis.suggested_sl_pct:.1%}")
            
            # Buy eligibility
            st.divider()
            
            budget = trader.config.per_stock_daily_budget
            can_buy, reason = trader.check_risk_limits(symbol, budget)
            
            if analysis.passes_momentum and can_buy:
                st.success(f"✅ {symbol} passes all checks. Ready to buy!")
            else:
                issues = []
                if not analysis.passes_momentum:
                    issues.append(f"Momentum: {analysis.reason}")
                if not can_buy:
                    issues.append(f"Risk: {reason}")
                st.error(f"❌ {symbol} blocked: {'; '.join(issues)}")


def display_action_buttons(options: Dict):
    """Display trading action buttons"""
    trader = st.session_state.trader
    
    st.header("🎯 Trading Operations")
    
    # Mode banner
    if not trader.config.dry_run:
        st.error("⚠️ LIVE MODE - Real orders will be executed!")
    else:
        st.info("🔒 DRY RUN MODE - No real orders")
    
    col1, col2, col3 = st.columns(3)
    
    # Column 1: Smart Investing
    with col1:
        st.subheader("📈 Smart Invest (Recommended)")
        
        st.caption("Buys stocks that pass momentum + risk checks")
        
        # Rank filter dropdown
        top_n_options = {
            "Top 5 (High conviction)": 5,
            "Top 10 (Core picks)": 10,
            "Top 15 (Standard)": 15,
            "Top 25 (Extended)": 25,
            "Top 40 (Full research)": 40,
            "All (Include holdings)": 0,
        }
        selected_filter = st.selectbox(
            "📊 Rank Filter",
            options=list(top_n_options.keys()),
            index=2,  # Default to Top 15
            key="smart_invest_top_n",
            help="Select which ranks to include. Top5=highest conviction, All=all stocks including holdings"
        )
        top_n_value = top_n_options[selected_filter]
        
        if st.button("🚀 Run Smart Investment", type="primary", use_container_width=True, key="smart_invest"):
            if not trader.connected:
                st.error("Connect first!")
            else:
                with st.spinner(f"Running smart investment (Top{top_n_value if top_n_value > 0 else 'All'})..."):
                    results = trader.run_simple_investment(top_n=top_n_value)
                    
                    if 'error' in results:
                        st.error(results['error'])
                    else:
                        st.success(f"Analyzed: {results['analyzed']}, "
                                   f"Passed: {results['passed_momentum']}, "
                                   f"Bought: {results['bought']}, "
                                   f"Protected: {results['protected']}")
                        
                        # Budget telemetry
                        if results.get('daily_budget'):
                            spent = results.get('total_spent', 0)
                            remaining = results.get('remaining_budget', 0)
                            daily = results.get('daily_budget', 0)
                            pct_used = (spent / daily * 100) if daily > 0 else 0
                            st.info(f"💰 Budget: ₹{spent:,.0f} spent / ₹{daily:,.0f} daily ({pct_used:.0f}% used) | ₹{remaining:,.0f} remaining")
                        
                        if results.get('details'):
                            df = pd.DataFrame(results['details'])
                            st.dataframe(df, hide_index=True, width='stretch')
    
    # Column 2: Protection
    with col2:
        st.subheader("🛡️ Protection")
        
        st.caption("ATR-based stop loss protection")
        
        if st.button("🛡️ Protect All Holdings", width='stretch', key="protect"):
            if not trader.connected:
                st.error("Connect first!")
            else:
                with st.spinner("Protecting holdings..."):
                    count = trader.protect_holdings_smart(refresh=options.get('refresh', False))
                    st.success(f"Protected {count} holdings with ATR-based SL")
        
        st.divider()
        
        if trader.config.risk.enable_trailing_stop:
            if st.button("📈 Check Trailing Stops", width='stretch', key="trailing"):
                if not trader.connected:
                    st.error("Connect first!")
                else:
                    with st.spinner("Checking..."):
                        triggers = trader.check_trailing_stops()
                        if triggers:
                            st.warning(f"Found {len(triggers)} trailing stop triggers!")
                            for t in triggers:
                                st.write(f"• {t['symbol']}: {t['reason']}")
                            
                            if st.button("Execute Trailing Stops", key="exec_trailing"):
                                count = trader.execute_trailing_stops()
                                st.success(f"Executed {count} trailing stops")
                        else:
                            st.info("No trailing stops triggered")
        
        if trader.config.risk.enable_partial_exit:
            if st.button("💰 Check Partial Exits", width='stretch', key="partial"):
                if not trader.connected:
                    st.error("Connect first!")
                else:
                    with st.spinner("Checking..."):
                        exits = trader.check_partial_exits()
                        if exits:
                            st.warning(f"Found {len(exits)} partial exit candidates!")
                            for e in exits:
                                st.write(f"• {e['symbol']}: +{e['gain_pct']:.1%} - sell {e['quantity']} shares")
                            
                            if st.button("Execute Partial Exits", key="exec_partial"):
                                count = trader.execute_partial_exits()
                                st.success(f"Executed {count} partial exits")
                        else:
                            st.info("No partial exits needed")
    
    # Column 3: Selling
    with col3:
        st.subheader("📉 Selling")
        
        negative = trader.get_negative_holdings() if trader.connected else []
        st.caption(f"Found {len(negative)} stocks with negative P&L")
        
        if st.button("🔴 Sell Negative P&L", width='stretch', key="sell_neg"):
            if not trader.connected:
                st.error("Connect first!")
            elif not negative:
                st.info("No negative holdings")
            else:
                with st.spinner("Selling..."):
                    count = trader.sell_negative_holdings()
                    if trader.config.dry_run:
                        st.success(f"[DRY RUN] Would sell {count} stocks")
                    else:
                        st.success(f"Sold {count} stocks")
        
        st.divider()
        
        # Sell All at +0.05% Above LTP
        st.caption("💰 Sell All Holdings at Premium")
        
        sell_premium_pct = st.slider(
            "Premium Above LTP %",
            min_value=0.01,
            max_value=1.0,
            value=0.05,
            step=0.01,
            format="%.2f%%",
            key="sell_premium_slider",
            help="""**SELL PRICE PREMIUM**

Sell at LTP + this percentage.

**Example** (LTP = ₹100):
- 0.05% → Sell at ₹100.05
- 0.10% → Sell at ₹100.10
- 0.50% → Sell at ₹100.50

**Why use premium?** Ensures limit order executes quickly while getting slightly better price than market order."""
        )
        
        holdings_count = len(trader.get_holdings()) if trader.connected else 0
        
        # Show preview of what will be sold
        if trader.connected and holdings_count > 0:
            premium_decimal = sell_premium_pct / 100
            holdings = trader.get_holdings()
            preview_data = []
            total_est = 0
            for h in holdings:
                ltp = h.get('last_price', 0)
                qty = h.get('quantity', 0)
                if ltp > 0 and qty > 0:
                    sell_price = ltp * (1 + premium_decimal)
                    est = qty * sell_price
                    total_est += est
                    preview_data.append({
                        'Symbol': h['tradingsymbol'],
                        'Qty': qty,
                        'LTP': f"₹{ltp:,.2f}",
                        'Sell @': f"₹{sell_price:,.2f}",
                        'Est Value': f"₹{est:,.0f}"
                    })
            
            if preview_data:
                with st.expander(f"📋 Preview: {len(preview_data)} stocks ≈ ₹{total_est:,.0f}"):
                    st.dataframe(pd.DataFrame(preview_data), hide_index=True)
        
        # Mode indicator
        if not trader.config.dry_run:
            st.warning(f"⚠️ LIVE MODE - Real orders!")
        
        if st.button(f"💸 Sell ALL ({holdings_count}) at +{sell_premium_pct:.2f}%", width='stretch', key="sell_all_premium", type="secondary"):
            if not trader.connected:
                st.error("Connect first!")
            elif holdings_count == 0:
                st.info("No holdings to sell")
            else:
                premium_decimal = sell_premium_pct / 100  # Convert % to decimal
                
                with st.spinner(f"Selling all at +{sell_premium_pct:.2f}%..."):
                    results = trader.sell_all_holdings_above_ltp(premium_pct=premium_decimal)
                    
                    if results['success'] > 0:
                        if trader.config.dry_run:
                            st.success(f"[DRY RUN] Would sell {results['success']} stocks for ≈₹{results['total_value']:,.0f}")
                        else:
                            st.success(f"✅ Sold {results['success']} stocks for ≈₹{results['total_value']:,.0f}")
                    if results['failed'] > 0:
                        st.error(f"❌ Failed: {results['failed']} stocks")
                    
                    if results['details']:
                        df = pd.DataFrame(results['details'])
                        df['ltp'] = df['ltp'].apply(lambda x: f"₹{x:,.2f}")
                        df['sell_price'] = df['sell_price'].apply(lambda x: f"₹{x:,.2f}")
                        df['est_value'] = df['est_value'].apply(lambda x: f"₹{x:,.0f}")
                        st.dataframe(df[['symbol', 'qty', 'ltp', 'sell_price', 'est_value', 'status']], hide_index=True)


def display_risk_report():
    """Display full risk report"""
    trader = st.session_state.trader
    
    st.subheader("📋 Full Risk Report")
    
    if not trader.connected:
        st.warning("Connect to generate report")
        return
    
    if st.button("📊 Generate Report", width='stretch'):
        with st.spinner("Generating risk report..."):
            report = trader.generate_risk_report()
            st.code(report, language=None)


def display_logs():
    """Display activity logs"""
    st.subheader("📜 Activity Log")
    
    if not st.session_state.logs:
        st.info("No activity yet")
        return
    
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


def display_order_book():
    """Display current order book"""
    trader = st.session_state.trader
    
    # Check which file will be used
    tips_path = REPO_ROOT / "data" / "tips_research_data.csv"
    using_tips = tips_path.exists()
    
    if using_tips:
        st.subheader("📋 Order Book (tips_research_data.csv)")
    else:
        st.subheader("📋 Order Book (order_book.csv)")
    
    orders = trader.read_order_book()
    top15 = [o for o in orders if trader.is_top15_rank(o.get('rank', ''))]
    
    if not top15:
        st.info("No Top15 stocks in order book")
        return
    
    st.write(f"Found {len(top15)} Top15 stocks")
    
    df = pd.DataFrame(top15)
    st.dataframe(df, hide_index=True, width='stretch')


def terminal_log(message: str, level: str = "INFO"):
    """Log message to terminal (stdout) with timestamp - visible in terminal running streamlit"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "BUY": "🛒"}.get(level, "•")
    log_line = f"[{timestamp}] {prefix} {level}: {message}"
    print(log_line, flush=True)  # flush ensures immediate output
    return log_line


def display_force_buy():
    """Display force buy section with stock selection checkboxes, custom qty, and GTT option"""
    trader = st.session_state.trader
    
    st.subheader("⚡ Force Buy (Override Risk Checks)")
    st.caption("Select stocks to buy regardless of momentum/risk filters")
    
    tips_path = REPO_ROOT / "data" / "tips_research_data.csv"
    
    if not tips_path.exists():
        st.warning("No tips_research_data.csv found. Generate one in Tips Research tab.")
        return
    
    if not trader.connected:
        st.warning("Connect to Kite first to enable force buy")
        return
    
    try:
        tips_df = pd.read_csv(tips_path)
    except Exception as e:
        st.error(f"Error reading tips CSV: {e}")
        return
    
    if tips_df.empty:
        st.info("No stocks in tips file")
        return
    
    # Initialize session state for selections and custom quantities
    if 'force_buy_selections' not in st.session_state:
        st.session_state.force_buy_selections = {}
    if 'force_buy_custom_qty' not in st.session_state:
        st.session_state.force_buy_custom_qty = {}
    
    # Mode warning
    if not trader.config.dry_run:
        st.error("⚠️ LIVE MODE - Selected stocks will be ACTUALLY PURCHASED!")
    else:
        st.info("🔒 DRY RUN - No real orders will be placed")
    
    terminal_log("Force Buy section loaded", "INFO")
    
    # Order type selection
    st.write("**Order Settings:**")
    col_order_type, col_gtt_dip = st.columns([1, 1])
    
    with col_order_type:
        order_type = st.radio(
            "Order Type",
            options=["LIMIT", "GTT (Dip Buy)"],
            horizontal=True,
            help="""**LIMIT**: Place order at current price (executes immediately if price matched)

**GTT (Dip Buy)**: Place GTT order that triggers when price drops by specified %"""
        )
        use_gtt = order_type == "GTT (Dip Buy)"
    
    with col_gtt_dip:
        if use_gtt:
            gtt_dip_pct = st.slider(
                "GTT Dip %",
                min_value=1,
                max_value=15,
                value=int(trader.config.gtt_buy_lower_percent * 100),
                help="""**DIP PERCENTAGE**

GTT triggers when price drops by this % from current LTP.

Example: 5% dip on ₹100 stock → Trigger at ₹95

**Recommendation**: 3-5% for quality stocks, 5-10% for volatile ones"""
            ) / 100.0
        else:
            gtt_dip_pct = 0.05  # default
            st.caption("GTT dip % only applies when GTT mode selected")
    
    st.divider()
    
    # Display stocks with checkboxes
    st.write(f"**{len(tips_df)} stocks available** - Select stocks and customize quantity:")
    
    # Select all / Deselect all
    col_a, col_b, col_reset = st.columns([1, 1, 1])
    with col_a:
        if st.button("☑️ Select All", key="select_all_force"):
            for idx in tips_df.index:
                st.session_state.force_buy_selections[idx] = True
            terminal_log(f"Selected all {len(tips_df)} stocks", "INFO")
            st.rerun()
    with col_b:
        if st.button("☐ Clear All", key="clear_all_force"):
            st.session_state.force_buy_selections = {}
            terminal_log("Cleared all selections", "INFO")
            st.rerun()
    with col_reset:
        if st.button("🔄 Reset Qty", key="reset_qty_force"):
            st.session_state.force_buy_custom_qty = {}
            terminal_log("Reset all custom quantities to default", "INFO")
            st.rerun()
    
    st.divider()
    
    # Header row
    hcol1, hcol2, hcol3, hcol4, hcol5, hcol6 = st.columns([0.4, 1.5, 1, 1, 1, 1])
    with hcol1:
        st.write("**✓**")
    with hcol2:
        st.write("**Symbol**")
    with hcol3:
        st.write("**Default Qty**")
    with hcol4:
        st.write("**Custom Qty**")
    with hcol5:
        st.write("**Price**")
    with hcol6:
        st.write("**Est. Value**")
    
    # Build selection UI
    selected_stocks = []
    
    for idx, row in tips_df.iterrows():
        symbol = row.get('Symbol', '')
        default_qty = max(1, int(row.get('Quantity', 0) or 0))  # Ensure at least 1
        price = float(row.get('Price', 0) or 0)
        rank = row.get('Rank', '')
        
        # Get custom qty or use default (ensure at least 1)
        custom_qty = max(1, st.session_state.force_buy_custom_qty.get(idx, default_qty))
        
        # Checkbox for each stock
        is_selected = st.session_state.force_buy_selections.get(idx, False)
        
        col1, col2, col3, col4, col5, col6 = st.columns([0.4, 1.5, 1, 1, 1, 1])
        
        with col1:
            new_selected = st.checkbox(
                f"Select {symbol}",
                value=is_selected,
                key=f"force_buy_{idx}",
                label_visibility="collapsed"
            )
            if new_selected != is_selected:
                st.session_state.force_buy_selections[idx] = new_selected
                action = "Selected" if new_selected else "Deselected"
                terminal_log(f"{action}: {symbol} (Qty: {custom_qty}, Price: ₹{price:.2f})", "INFO")
        
        with col2:
            rank_badge = f"🏆{rank}" if rank else ""
            st.write(f"**{symbol}** {rank_badge}")
        
        with col3:
            st.caption(f"{default_qty}")
        
        with col4:
            new_qty = st.number_input(
                f"Quantity for {symbol}",
                min_value=1,
                max_value=10000,
                value=max(1, int(custom_qty)),
                step=1,
                key=f"qty_{idx}",
                label_visibility="collapsed"
            )
            if new_qty != custom_qty:
                st.session_state.force_buy_custom_qty[idx] = new_qty
                terminal_log(f"Qty changed for {symbol}: {custom_qty} → {new_qty}", "INFO")
        
        with col5:
            if use_gtt:
                trigger_price = price * (1 - gtt_dip_pct)
                st.write(f"₹{trigger_price:,.2f}")
                st.caption(f"(LTP: {price:,.0f})")
            else:
                st.write(f"₹{price:,.2f}")
        
        with col6:
            final_qty = new_qty if new_qty else custom_qty
            final_price = price * (1 - gtt_dip_pct) if use_gtt else price
            est_value = final_qty * final_price
            st.write(f"₹{est_value:,.0f}")
        
        if new_selected:
            selected_stocks.append({
                'symbol': symbol,
                'quantity': int(new_qty if new_qty else custom_qty),
                'price': price,
                'rank': rank,
                'target_value': est_value,
                'idx': idx
            })
    
    # Summary and Execute button
    st.divider()
    
    num_selected = len([k for k, v in st.session_state.force_buy_selections.items() if v])
    total_value = sum(s['target_value'] for s in selected_stocks)
    
    col_sum, col_exec = st.columns([2, 1])
    
    with col_sum:
        if num_selected > 0:
            order_mode = "GTT DIP BUY" if use_gtt else "LIMIT"
            st.success(f"**Selected: {num_selected} stocks** | Mode: {order_mode} | Total Value: ₹{total_value:,.0f}")
        else:
            st.info("No stocks selected. Check the boxes to select stocks for force buy.")
    
    with col_exec:
        btn_label = f"🎯 EXECUTE GTT ({num_selected})" if use_gtt else f"🚀 EXECUTE LIMIT ({num_selected})"
        execute_btn = st.button(
            btn_label,
            type="primary",
            disabled=(num_selected == 0),
            key="execute_force_buy"
        )
    
    # Execute force buy
    if execute_btn and num_selected > 0:
        order_mode = "GTT" if use_gtt else "LIMIT"
        terminal_log(f"=" * 50, "INFO")
        terminal_log(f"FORCE BUY EXECUTION STARTED - MODE: {order_mode}", "BUY")
        terminal_log(f"Stocks: {num_selected}, Total Value: ₹{total_value:,.0f}", "INFO")
        if use_gtt:
            terminal_log(f"GTT Dip: {gtt_dip_pct:.1%}", "INFO")
        terminal_log(f"Mode: {'LIVE' if not trader.config.dry_run else 'DRY RUN'}", "WARNING" if not trader.config.dry_run else "INFO")
        terminal_log(f"=" * 50, "INFO")
        
        add_log(f"Force buy started ({order_mode}): {num_selected} stocks, ₹{total_value:,.0f}", "warning")
        
        success_count = 0
        fail_count = 0
        results = []
        
        progress_bar = st.progress(0, text="Starting force buy...")
        
        for i, stock in enumerate(selected_stocks):
            symbol = stock['symbol']
            qty = stock['quantity']
            ltp = stock['price']
            
            terminal_log(f"Processing {i+1}/{num_selected}: {symbol} x {qty}", "INFO")
            progress_bar.progress((i + 1) / num_selected, text=f"Processing {symbol}...")
            
            try:
                if use_gtt:
                    # GTT order
                    trigger_price = trader.round_to_tick(ltp * (1 - gtt_dip_pct), symbol=symbol)
                    limit_price = trader.round_to_tick(trigger_price * 1.001, symbol=symbol)
                    
                    if trader.config.dry_run:
                        terminal_log(f"DRY RUN GTT: {symbol} x {qty} @ trigger ₹{trigger_price:.2f}", "BUY")
                        add_log(f"DRY GTT: {symbol} x {qty} @ ₹{trigger_price:.2f}", "info")
                        results.append({
                            'Symbol': symbol,
                            'Qty': qty,
                            'Trigger': f"₹{trigger_price:.2f}",
                            'Type': 'GTT',
                            'Status': '🔵 DRY RUN',
                            'ID': 'N/A'
                        })
                        success_count += 1
                    else:
                        terminal_log(f"LIVE GTT: {symbol} x {qty} @ trigger ₹{trigger_price:.2f}", "BUY")
                        
                        gtt_id = trader.kite.place_gtt(
                            trigger_type=trader.kite.GTT_TYPE_SINGLE,
                            tradingsymbol=symbol,
                            exchange='NSE',
                            trigger_values=[trigger_price],
                            last_price=ltp,
                            orders=[{
                                'transaction_type': trader.kite.TRANSACTION_TYPE_BUY,
                                'quantity': qty,
                                'order_type': trader.kite.ORDER_TYPE_LIMIT,
                                'product': trader.kite.PRODUCT_CNC,
                                'price': limit_price,
                            }]
                        )
                        
                        terminal_log(f"SUCCESS GTT: {symbol} - ID: {gtt_id}", "SUCCESS")
                        add_log(f"GTT placed: {symbol} x {qty} @ ₹{trigger_price:.2f} (ID: {gtt_id})", "success")
                        results.append({
                            'Symbol': symbol,
                            'Qty': qty,
                            'Trigger': f"₹{trigger_price:.2f}",
                            'Type': 'GTT',
                            'Status': '✅ SUCCESS',
                            'ID': gtt_id
                        })
                        success_count += 1
                else:
                    # Regular LIMIT order
                    if trader.config.dry_run:
                        terminal_log(f"DRY RUN LIMIT: {symbol} x {qty} @ ₹{ltp:.2f}", "BUY")
                        add_log(f"DRY: Buy {qty} x {symbol} @ ₹{ltp:.2f}", "info")
                        results.append({
                            'Symbol': symbol,
                            'Qty': qty,
                            'Price': f"₹{ltp:.2f}",
                            'Type': 'LIMIT',
                            'Status': '🔵 DRY RUN',
                            'ID': 'N/A'
                        })
                        success_count += 1
                    else:
                        terminal_log(f"LIVE LIMIT: {symbol} x {qty} @ ₹{ltp:.2f}", "BUY")
                        
                        order_id = trader.kite.place_order(
                            variety=trader.kite.VARIETY_REGULAR,
                            exchange="NSE",
                            tradingsymbol=symbol,
                            transaction_type=trader.kite.TRANSACTION_TYPE_BUY,
                            quantity=qty,
                            product=trader.kite.PRODUCT_CNC,
                            order_type=trader.kite.ORDER_TYPE_LIMIT,
                            price=ltp
                        )
                        
                        terminal_log(f"SUCCESS LIMIT: {symbol} - Order ID: {order_id}", "SUCCESS")
                        add_log(f"Bought {qty} x {symbol} @ ₹{ltp:.2f} (ID: {order_id})", "success")
                        results.append({
                            'Symbol': symbol,
                            'Qty': qty,
                            'Price': f"₹{ltp:.2f}",
                            'Type': 'LIMIT',
                            'Status': '✅ SUCCESS',
                            'ID': order_id
                        })
                        success_count += 1
                    
            except Exception as e:
                error_msg = str(e)
                terminal_log(f"FAILED: {symbol} - {error_msg}", "ERROR")
                add_log(f"Failed: {symbol} - {error_msg}", "error")
                results.append({
                    'Symbol': symbol,
                    'Qty': qty,
                    'Price': f"₹{ltp:.2f}" if not use_gtt else f"Trig: ₹{ltp * (1 - gtt_dip_pct):.2f}",
                    'Type': 'GTT' if use_gtt else 'LIMIT',
                    'Status': '❌ FAILED',
                    'ID': error_msg[:25]
                })
                fail_count += 1
        
        progress_bar.progress(1.0, text="Complete!")
        
        # Summary
        terminal_log(f"=" * 50, "INFO")
        terminal_log(f"FORCE BUY COMPLETE ({order_mode}): {success_count} success, {fail_count} failed", "SUCCESS" if fail_count == 0 else "WARNING")
        terminal_log(f"=" * 50, "INFO")
        
        if success_count > 0:
            st.success(f"✅ Successfully processed {success_count} {order_mode} orders")
        if fail_count > 0:
            st.error(f"❌ Failed {fail_count} orders")
        
        # Show results table
        if results:
            st.write("**Order Results:**")
            st.dataframe(pd.DataFrame(results), hide_index=True, width='stretch')
        
        # Clear selections after execution
        st.session_state.force_buy_selections = {}
        add_log(f"Force buy complete ({order_mode}): {success_count} success, {fail_count} failed", "success" if fail_count == 0 else "warning")


def display_tips_research():
    """Display tips research management tab"""
    trader = st.session_state.trader
    
    st.header("📰 Tips Research Manager")
    st.caption("Update your trading universe with latest market data using tips_research_agent")
    
    tips_path = REPO_ROOT / "data" / "tips_research_data.csv"
    research_path = REPO_ROOT / "data" / "research_data.csv"
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Current tips data
        st.subheader("📊 Current Tips Universe")
        
        if tips_path.exists():
            try:
                tips_df = pd.read_csv(tips_path)
                
                # Show stats
                modified_time = datetime.fromtimestamp(tips_path.stat().st_mtime)
                st.info(f"📅 Last updated: {modified_time.strftime('%Y-%m-%d %H:%M:%S')} | 📈 {len(tips_df)} stocks")
                
                # Configure columns for better display
                column_config = {
                    "Symbol": st.column_config.TextColumn("Symbol", width="small"),
                    "Quantity": st.column_config.NumberColumn("Qty", width="small"),
                    "Price": st.column_config.NumberColumn("Price", format="₹%.2f", width="small"),
                    "Holding_Qty": st.column_config.NumberColumn("Hold", width="small"),
                    "Avg_Cost": st.column_config.NumberColumn("AvgCost", format="₹%.2f", width="small"),
                    "Holding_Value": st.column_config.NumberColumn("HoldVal", format="₹%.0f", width="small"),
                    "PnL": st.column_config.NumberColumn("P&L", format="₹%.0f", width="small"),
                    "PnL_Pct": st.column_config.NumberColumn("P&L%", format="%.2f%%", width="small"),
                    "DMA50": st.column_config.NumberColumn("DMA50", format="%.2f", width="small"),
                    "DMA200": st.column_config.NumberColumn("DMA200", format="%.2f", width="small"),
                    "RSI14": st.column_config.NumberColumn("RSI", format="%.1f", width="small"),
                    "DMA_Trend": st.column_config.TextColumn("Trend", width="small"),
                    "Momentum_Score": st.column_config.NumberColumn("Mom", width="small"),
                    "Transaction": st.column_config.TextColumn("Txn", width="small"),
                    "Variety": st.column_config.TextColumn("Variety", width="small"),
                    "Product": st.column_config.TextColumn("Product", width="small"),
                    "Order_Type": st.column_config.TextColumn("Type", width="small"),
                    "Rank": st.column_config.TextColumn("Rank", width="small"),
                    "Recommendation": st.column_config.TextColumn("Reco", width="small"),
                    "Allocation": st.column_config.NumberColumn("Alloc", format="₹%d", width="small"),
                    "TargetValue": st.column_config.NumberColumn("Target", format="₹%d", width="small"),
                    "Rationale": st.column_config.TextColumn("Rationale", width="large"),
                }
                
                st.dataframe(tips_df, hide_index=True, width='stretch', height=500, column_config=column_config)
            except Exception as e:
                st.error(f"Error reading tips CSV: {e}")
        else:
            st.warning("No tips_research_data.csv found. Generate one below.")
        
        # Source research data
        st.subheader("📋 Source: research_data.csv")
        
        if research_path.exists():
            try:
                research_df = pd.read_csv(research_path)
                st.write(f"Source file has {len(research_df)} stocks")
                with st.expander("View Source Data", expanded=False):
                    st.dataframe(research_df, hide_index=True, width='stretch')
            except Exception as e:
                st.error(f"Error reading research CSV: {e}")
        else:
            st.warning("No research_data.csv found. Run deep_search_agent first.")
    
    with col2:
        st.subheader("🔄 Update Tips")
        
        # Budget settings
        daily_budget = st.number_input(
            "Daily Budget (₹)",
            min_value=10000,
            max_value=10000000,
            value=int(trader.config.daily_budget),
            step=10000,
            help="""**DAILY BUDGET FOR ALLOCATION**

The tips agent uses this to calculate how many shares of each stock to buy.

**How allocation works**:
1. Each stock has a RANK (1=best, 15=good)
2. Higher ranked stocks get larger % allocation
3. Budget is distributed across Top N stocks

**Example** (Budget ₹1,00,000, 15 stocks):
- Rank 1-5: ₹10,000 each = ₹50,000
- Rank 6-10: ₹7,000 each = ₹35,000  
- Rank 11-15: ₹3,000 each = ₹15,000

**Tip**: Start conservative. You can always increase later."""
        )
        
        # Note: top_n filtering is controlled by research_data.csv Rank column
        # Agent includes all stocks from the source file
        st.caption("💡 Stocks included are based on Rank in research_data.csv")
        
        per_stock_budget = st.number_input(
            "Per-Stock Budget (₹)",
            min_value=1000,
            max_value=100000,
            value=int(trader.config.per_stock_daily_budget),
            step=1000,
            help="""**MAX BUDGET PER STOCK**

Caps how much can be allocated to any single stock.

**Why cap?** Even high-conviction picks shouldn't dominate your portfolio.

**Example** (Daily ₹1L, Top15, Per-stock ₹10k):
- Without cap: Rank 1 might get ₹20k
- With ₹10k cap: Rank 1 gets max ₹10k

This ensures diversification even among top picks."""
        )
        
        max_qty = st.number_input(
            "Max Qty/Stock",
            min_value=1,
            max_value=1000,
            value=trader.config.max_qty_per_stock,
            step=50,
            help="""**MAX SHARES PER STOCK**

Caps the number of shares for any stock.

**Why needed?** Low-price stocks (₹20-50) can result in huge quantities.

**Example** (Budget ₹10k):
- TCS at ₹4,000 → 2 shares (OK)
- Penny at ₹20 → 500 shares (needs cap!)

**Default**: 500 shares max."""
        )
        
        st.divider()
        
        # Generate button
        if TIPS_AGENT_AVAILABLE:
            if st.button("🚀 Generate Tips CSV + Advisor Analysis", type="primary", width='stretch'):
                # Set credentials for live LTP
                if st.session_state.access_token:
                    os.environ["ACCESS_TOKEN"] = st.session_state.access_token
                if API_KEY:
                    os.environ["API_KEY"] = API_KEY
                
                # Step 1: Generate tips CSV with technicals
                with st.spinner("Step 1/2: Generating tips_research_data.csv with live prices & technicals..."):
                    try:
                        result = generate_tips_research_data_csv(
                            top_n_rank=None,  # Include all stocks from research_data.csv
                            daily_budget=daily_budget,
                            per_stock_budget=per_stock_budget,
                            max_qty_per_stock=max_qty,
                        )
                        
                        if result.get("status") == "success":
                            st.success(f"✅ Step 1: Generated {result.get('count')} stocks (prices: {result.get('price_source')})")
                            add_log(f"Tips CSV generated: {result.get('count')} stocks", "success")
                            terminal_log(f"Tips CSV generated: {result.get('count')} stocks", "SUCCESS")
                            
                            if result.get("price_source") != "kite_ltp":
                                st.warning(f"⚠️ Used CSV prices (not live): {result.get('ltp_error', 'Kite LTP unavailable')}")
                        else:
                            st.error(f"Step 1 Failed: {result.get('message', 'Unknown error')}")
                            st.stop()
                    except Exception as e:
                        st.error(f"Step 1 Error: {e}")
                        st.stop()
                
                # Step 2: Run advisor agent to analyze and update recommendations
                if ADVISOR_AGENT_AVAILABLE:
                    with st.spinner("Step 2/2: Advisor analyzing stocks & updating recommendations..."):
                        try:
                            # Read tips CSV
                            tips_data = read_tips_csv()
                            if tips_data.get("status") != "success":
                                st.error(f"Advisor: Failed to read tips CSV")
                                st.stop()
                            
                            rows = tips_data.get("rows", [])
                            analyses = []
                            updates = []
                            
                            progress = st.progress(0, text="Analyzing stocks...")
                            
                            for i, row in enumerate(rows):
                                symbol = row.get("Symbol", "")
                                progress.progress((i + 1) / len(rows), text=f"Analyzing {symbol}...")
                                
                                # Call analyze_single_stock with all technical data
                                analysis_result = analyze_single_stock(
                                    symbol=symbol,
                                    rationale=row.get("Rationale", ""),
                                    rank=row.get("Rank", ""),
                                    price=float(row.get("Price", 0) or 0),
                                    quantity=int(row.get("Quantity", 0) or 0),
                                    dma50=float(row.get("DMA50", 0) or 0),
                                    dma200=float(row.get("DMA200", 0) or 0),
                                    rsi14=float(row.get("RSI14", 50) or 50),
                                    dma_trend=row.get("DMA_Trend", "N/A"),
                                    momentum_score=int(row.get("Momentum_Score", 0) or 0),
                                )
                                
                                if analysis_result.get("status") == "success":
                                    analysis = analysis_result.get("analysis", {})
                                    analyses.append(analysis)
                                    updates.append({
                                        "symbol": symbol,
                                        "recommendation": analysis.get("recommendation", "REVIEW")
                                    })
                            
                            progress.progress(1.0, text="Updating recommendations...")
                            
                            # Update recommendations in CSV
                            update_result = update_recommendations(updates)
                            
                            # Generate advisor report
                            report_result = generate_advisor_report(analyses)
                            
                            if update_result.get("status") == "success":
                                st.success(f"✅ Step 2: Analyzed {len(analyses)} stocks, updated {update_result.get('updated_count')} recommendations")
                                add_log(f"Advisor: Updated {update_result.get('updated_count')} recommendations", "success")
                                terminal_log(f"Advisor: Updated {update_result.get('updated_count')} recommendations", "SUCCESS")
                                
                                # Show recommendation summary
                                reco_counts = {}
                                for a in analyses:
                                    r = a.get("recommendation", "UNKNOWN")
                                    reco_counts[r] = reco_counts.get(r, 0) + 1
                                
                                st.info(f"📊 Recommendations: {reco_counts}")
                            else:
                                st.warning(f"Advisor update issue: {update_result.get('message')}")
                                
                        except Exception as e:
                            st.warning(f"Advisor error (non-fatal): {e}")
                            terminal_log(f"Advisor error: {e}", "WARNING")
                else:
                    st.info("ℹ️ Advisor agent not available - skipping recommendation analysis")
                
                st.rerun()
        else:
            st.warning("tips_research_agent not available")
            st.caption("Install or check tips_research_agent module")
        
        st.divider()
        
        # Alternative: Run via CLI
        st.subheader("💻 CLI Alternative")
        st.caption("Run agents separately in terminal:")
        st.code('adk run tips_research_agent  # Generate CSV with technicals\nadk run advisor_agent        # Analyze & update recommendations', language='bash')
        
        st.divider()
        
        # Reports
        st.subheader("📄 Reports")
        
        report_path = REPO_ROOT / "data" / "tips_research_report.md"
        audit_path = REPO_ROOT / "data" / "tips_research_generation.md"
        advisor_path = REPO_ROOT / "data" / "advisor_report.md"
        
        if report_path.exists():
            with st.expander("📊 Research Report"):
                st.markdown(report_path.read_text(encoding='utf-8'))
        
        if advisor_path.exists():
            with st.expander("🎯 Advisor Report (Buy/Hold/Sell)"):
                st.markdown(advisor_path.read_text(encoding='utf-8'))
        
        if audit_path.exists():
            with st.expander("📋 Generation Audit"):
                st.markdown(audit_path.read_text(encoding='utf-8'))


def display_market_agent():
    """Display Market Agent tab for daily market analysis"""
    trader = st.session_state.trader
    
    st.header("📈 Market Agent - Daily Analysis")
    st.caption("Analyze top gainers, losers, market heroes, and best sectors for today")
    
    if not MARKET_AGENT_AVAILABLE:
        st.error("❌ Market Agent module not available. Check market_agent.py in src/")
        return
    
    if not trader.connected:
        st.warning("⚠️ Connect to Kite to run market analysis")
        return
    
    # Initialize session state for market data
    if 'market_analysis' not in st.session_state:
        st.session_state.market_analysis = None
    if 'market_analysis_time' not in st.session_state:
        st.session_state.market_analysis_time = None
    
    # Day Run button
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        if st.button("🚀 Day Run - Analyze Market", type="primary", use_container_width=True, key="market_day_run"):
            with st.spinner("Analyzing market... fetching data for 100+ stocks..."):
                try:
                    # Use trader's kite instance
                    agent = MarketAgent(kite=trader.kite)
                    result = agent.analyze_market()
                    
                    if result.get("status") == "success":
                        st.session_state.market_analysis = result
                        st.session_state.market_analysis_time = datetime.now()
                        add_log(f"Market analysis complete: {result['total_stocks']} stocks", "success")
                        terminal_log(f"Market analysis: {result['total_stocks']} stocks analyzed", "SUCCESS")
                    else:
                        st.error(f"Analysis failed: {result.get('message')}")
                        add_log(f"Market analysis failed: {result.get('message')}", "error")
                except Exception as e:
                    st.error(f"Error: {e}")
                    add_log(f"Market analysis error: {e}", "error")
                st.rerun()
    
    with col2:
        if st.session_state.market_analysis_time:
            st.info(f"🕐 Last run: {st.session_state.market_analysis_time.strftime('%H:%M:%S')}")
    
    with col3:
        if st.button("🔄 Clear Cache", key="clear_market_cache"):
            st.session_state.market_analysis = None
            st.session_state.market_analysis_time = None
            st.rerun()
    
    # Display results if available
    if st.session_state.market_analysis:
        result = st.session_state.market_analysis
        
        st.divider()
        
        # Market Breadth Summary
        breadth = result.get("market_breadth", {})
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("📊 Total Stocks", result.get("total_stocks", 0))
        with col2:
            st.metric("🟢 Gainers", breadth.get("gainers", 0))
        with col3:
            st.metric("🔴 Losers", breadth.get("losers", 0))
        with col4:
            best = result.get("best_sector", {})
            st.metric("🏆 Best Sector", best.get("name", "N/A"), f"{best.get('avg_change', 0):+.2f}%")
        
        st.divider()
        
        # Three columns for Gainers, Losers, Heroes
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🟢 Top Gainers")
            gainers = result.get("top_gainers", [])
            if gainers:
                df = pd.DataFrame(gainers)[['symbol', 'ltp', 'change_pct', 'sector']]
                df.columns = ['Symbol', 'LTP', 'Change %', 'Sector']
                df['LTP'] = df['LTP'].apply(lambda x: f"₹{x:,.2f}")
                df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                st.info("No gainers found")
        
        with col2:
            st.subheader("🔴 Top Losers")
            losers = result.get("top_losers", [])
            if losers:
                df = pd.DataFrame(losers)[['symbol', 'ltp', 'change_pct', 'sector']]
                df.columns = ['Symbol', 'LTP', 'Change %', 'Sector']
                df['LTP'] = df['LTP'].apply(lambda x: f"₹{x:,.2f}")
                df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                st.info("No losers found")
        
        with col3:
            st.subheader("🦸 Market Heroes")
            st.caption("High momentum stocks (>2% gain, trading near high)")
            heroes = result.get("market_heroes", [])
            if heroes:
                df = pd.DataFrame(heroes)[['symbol', 'ltp', 'change_pct', 'momentum_score', 'sector']]
                df.columns = ['Symbol', 'LTP', 'Change %', 'Score', 'Sector']
                df['LTP'] = df['LTP'].apply(lambda x: f"₹{x:,.2f}")
                df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                st.info("No market heroes today")
        
        st.divider()
        
        # Best Sector with Top 5 Stocks
        st.subheader(f"🏆 Best Sector: {best.get('name', 'N/A')}")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.metric("Average Change", f"{best.get('avg_change', 0):+.2f}%")
            st.metric("Stocks in Sector", best.get("stocks_count", 0))
        
        with col2:
            st.write("**Top 5 Stocks in Best Sector:**")
            top5 = best.get("top_5", [])
            if top5:
                df = pd.DataFrame(top5)[['symbol', 'ltp', 'change_pct', 'volume']]
                df.columns = ['Symbol', 'LTP', 'Change %', 'Volume']
                df['LTP'] = df['LTP'].apply(lambda x: f"₹{x:,.2f}")
                df['Change %'] = df['Change %'].apply(lambda x: f"{x:+.2f}%")
                df['Volume'] = df['Volume'].apply(lambda x: f"{x:,.0f}")
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                st.info("No stocks data")
        
        st.divider()
        
        # All Sectors Performance
        st.subheader("📊 All Sectors Performance")
        
        all_sectors = result.get("all_sectors", {})
        if all_sectors:
            # Sort sectors by performance
            sorted_sectors = sorted(all_sectors.values(), key=lambda x: x['avg_change_pct'], reverse=True)
            
            sector_rows = []
            for s in sorted_sectors:
                sector_rows.append({
                    'Sector': s['sector'],
                    'Avg Change %': f"{s['avg_change_pct']:+.2f}%",
                    'Stocks': s['stocks_count'],
                    'Gainers': s['gainers'],
                    'Losers': s['losers'],
                    'Status': '🟢' if s['avg_change_pct'] > 0 else '🔴' if s['avg_change_pct'] < 0 else '⚪'
                })
            
            st.dataframe(pd.DataFrame(sector_rows), hide_index=True, use_container_width=True)
            
            # Expandable detail for each sector
            with st.expander("📋 View Sector Details"):
                for s in sorted_sectors[:5]:  # Top 5 sectors detail
                    st.write(f"**{s['sector']}** ({s['avg_change_pct']:+.2f}%)")
                    top5 = s.get('top_5', [])
                    if top5:
                        for stock in top5:
                            st.caption(f"  • {stock['symbol']}: ₹{stock['ltp']:,.2f} ({stock['change_pct']:+.2f}%)")
        else:
            st.info("No sector data available")
        
        st.divider()
        
        # Quick Actions
        st.subheader("⚡ Quick Actions")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📥 Add Top Gainers to Research", key="add_gainers"):
                # This would add top gainers to research_data.csv
                st.info("Feature coming soon: Add gainers to research_data.csv")
        
        with col2:
            if st.button("📥 Add Heroes to Research", key="add_heroes"):
                st.info("Feature coming soon: Add heroes to research_data.csv")
        
        with col3:
            if st.button("📥 Add Best Sector to Research", key="add_sector"):
                st.info("Feature coming soon: Add sector stocks to research_data.csv")
    
    else:
        st.info("👆 Click 'Day Run' to analyze today's market")
        
        # Show what the analysis will provide
        with st.expander("ℹ️ What will be analyzed?"):
            st.markdown("""
**The Market Agent analyzes 100+ stocks including:**
- All NIFTY 50 constituents
- Key mid-cap stocks across sectors
- Defense, IT, Banking, Pharma, Auto, FMCG, Metals, and more

**Analysis includes:**
1. 🟢 **Top 10 Gainers** - Stocks with highest % gain today
2. 🔴 **Top 10 Losers** - Stocks with highest % loss today  
3. 🦸 **Market Heroes** - High momentum stocks showing:
   - Change > 2%
   - Trading near day's high
   - Strong volume activity
4. 🏆 **Best Sector** - Sector with highest average gain + Top 5 stocks
5. 📊 **All Sectors** - Performance breakdown by sector
            """)


# ==================== MAIN ====================

def main():
    """Main application entry point"""
    init_session_state()
    setup_trader_logging()
    
    # Title
    st.title("🛡️ Kite Trading V2 - Risk Managed")
    st.caption("Portfolio risk controls, ATR-based stops, momentum filters, and trailing exits")
    
    # Sidebar
    options = display_sidebar()
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🛡️ Risk Dashboard",
        "📊 Holdings",
        "🎯 Trade",
        "📰 Tips Research",
        "📈 Market Agent",
        "🔍 Analyze",
        "📜 Logs"
    ])
    
    with tab1:
        display_risk_dashboard()
        st.divider()
        display_risk_report()
    
    with tab2:
        display_holdings_analysis()
    
    with tab3:
        display_action_buttons(options)
        st.divider()
        display_order_book()
        st.divider()
        display_force_buy()
    
    with tab4:
        display_tips_research()
    
    with tab5:
        display_market_agent()
    
    with tab6:
        display_stock_analyzer()
    
    with tab7:
        display_logs()


if __name__ == "__main__":
    main()
