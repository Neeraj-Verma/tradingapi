"""
Zerodha Kite Trading Dashboard V3 - Cloud AI Enhanced
A web-based UI for trading with Cloud AI research capabilities.
Run with: streamlit run src/main_v3.py

Features:
- All V2 risk management features
- Cloud AI Research via deployed GCP API
- AI-powered stock sentiment analysis  
- Enhanced tips research with Gemini AI
- User Authentication for secure access
"""

import os
import sys
import subprocess
import webbrowser
import hashlib
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# App root directory
APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT  # For compatibility

from kite_trader_v2 import KiteTraderV2, TraderConfigV2, RiskConfig

# Import Cloud API Client
try:
    from cloud_api_client import CloudAPIClient, CloudAPIConfig, get_cloud_client
    CLOUD_API_AVAILABLE = True
except ImportError:
    CLOUD_API_AVAILABLE = False

# Optional agents (not available in cloud deployment)
TIPS_AGENT_AVAILABLE = False
ADVISOR_AGENT_AVAILABLE = False
MARKET_AGENT_AVAILABLE = False

# Load environment variables
_app_env = APP_ROOT / ".env"
if _app_env.exists():
    load_dotenv(dotenv_path=_app_env, override=False)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Cloud API Configuration
CLOUD_API_URL = os.getenv("CLOUD_API_URL", "https://gemini-adk-agents-vpunjpdcba-uc.a.run.app")
CLOUD_API_KEY = os.getenv("CLOUD_API_KEY", "kite-agents-2026-secure-key")

# ==================== AUTHENTICATION ====================
# Default users (override via .streamlit/secrets.toml or environment)
DEFAULT_USERS = {
    "admin": "admin123",      # Change in production!
    "neeraj": "trading2026",  # Change in production!
}

# Get users from secrets or environment
def get_auth_users() -> Dict[str, str]:
    """Get authentication users from secrets or defaults"""
    try:
        if hasattr(st, 'secrets') and 'auth' in st.secrets and 'users' in st.secrets.auth:
            return dict(st.secrets.auth.users)
    except Exception:
        pass
    
    # Try environment variable (comma-separated user:pass pairs)
    auth_env = os.getenv("AUTH_USERS", "")
    if auth_env:
        users = {}
        for pair in auth_env.split(","):
            if ":" in pair:
                user, passwd = pair.split(":", 1)
                users[user.strip()] = passwd.strip()
        if users:
            return users
    
    return DEFAULT_USERS


def hash_password(password: str) -> str:
    """Hash password for comparison"""
    return hashlib.sha256(password.encode()).hexdigest()


def check_auth_enabled() -> bool:
    """Check if authentication is enabled"""
    try:
        if hasattr(st, 'secrets') and 'auth' in st.secrets:
            return st.secrets.auth.get('enabled', True)
    except Exception:
        pass
    return os.getenv("AUTH_ENABLED", "true").lower() == "true"


def login_page():
    """Display login page"""
    st.set_page_config(
        page_title="Kite Trading V3 - Login",
        page_icon="🔐",
        layout="centered"
    )
    
    st.markdown("""
    <style>
        .login-container {
            max-width: 400px;
            margin: 0 auto;
            padding: 40px;
            border-radius: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
        }
        .login-title {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .login-subtitle {
            opacity: 0.8;
            margin-bottom: 30px;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style="text-align: center; padding: 20px;">
        <h1>🤖 Kite Trading V3</h1>
        <p style="color: #666;">Cloud AI Enhanced Trading Dashboard</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### 🔐 Login")
        
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            remember = st.checkbox("Remember me for 8 hours")
            
            submitted = st.form_submit_button("Login", use_container_width=True, type="primary")
            
            if submitted:
                users = get_auth_users()
                
                if username in users and users[username] == password:
                    st.session_state.authenticated = True
                    st.session_state.username = username
                    st.session_state.login_time = datetime.now()
                    if remember:
                        st.session_state.session_timeout = 480  # 8 hours
                    else:
                        st.session_state.session_timeout = 60  # 1 hour
                    st.success(f"Welcome, {username}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        
        st.divider()
        
        st.caption("🔒 Secure trading dashboard with Cloud AI research")
        st.caption(f"API: {CLOUD_API_URL[:50]}...")


def check_session_valid() -> bool:
    """Check if current session is still valid"""
    if not st.session_state.get('authenticated', False):
        return False
    
    login_time = st.session_state.get('login_time')
    timeout = st.session_state.get('session_timeout', 60)
    
    if login_time:
        elapsed = (datetime.now() - login_time).total_seconds() / 60
        if elapsed > timeout:
            st.session_state.authenticated = False
            return False
    
    return True


def logout():
    """Logout current user"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.login_time = None
    st.rerun()


def apply_custom_css():
    """Apply custom CSS styles"""
    st.markdown("""
    <style>
        .risk-ok { background-color: #d4edda; padding: 10px; border-radius: 5px; margin: 5px 0; }
        .risk-warn { background-color: #fff3cd; padding: 10px; border-radius: 5px; margin: 5px 0; }
        .risk-danger { background-color: #f8d7da; padding: 10px; border-radius: 5px; margin: 5px 0; }
        .ai-response { background-color: #e3f2fd; padding: 15px; border-radius: 10px; margin: 10px 0; border-left: 4px solid #2196f3; }
        .metric-card { padding: 15px; border-radius: 10px; margin: 10px 0; }
        .stButton>button { margin-bottom: 5px; }
        .cloud-status { padding: 5px 10px; border-radius: 15px; font-size: 12px; }
        .cloud-online { background-color: #c8e6c9; color: #2e7d32; }
        .cloud-offline { background-color: #ffcdd2; color: #c62828; }
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
    if 'cloud_client' not in st.session_state:
        if CLOUD_API_AVAILABLE:
            config = CloudAPIConfig(base_url=CLOUD_API_URL, api_key=CLOUD_API_KEY)
            st.session_state.cloud_client = CloudAPIClient(config)
        else:
            st.session_state.cloud_client = None
    if 'cloud_status' not in st.session_state:
        st.session_state.cloud_status = None
    if 'ai_research_cache' not in st.session_state:
        st.session_state.ai_research_cache = {}


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


def check_cloud_status() -> Dict:
    """Check Cloud API status"""
    if not st.session_state.cloud_client:
        return {"status": "unavailable", "message": "Cloud client not initialized"}
    
    try:
        result = st.session_state.cloud_client.health_check()
        if result.get("status") == "healthy":
            st.session_state.cloud_status = {
                "online": True,
                "gemini": result.get("gemini_available", False),
                "vertex": result.get("vertex_available", False),
                "timestamp": datetime.now()
            }
            return {"status": "online", "data": result}
        else:
            st.session_state.cloud_status = {"online": False}
            return {"status": "offline", "error": result.get("error", "Unknown")}
    except Exception as e:
        st.session_state.cloud_status = {"online": False}
        return {"status": "error", "error": str(e)}


def display_sidebar() -> Dict:
    """Display sidebar with configuration"""
    trader = st.session_state.trader
    
    st.sidebar.title("🤖 V3 Cloud AI Trading")
    
    # Cloud Status
    cloud_status = st.session_state.cloud_status
    if cloud_status and cloud_status.get("online"):
        st.sidebar.markdown('<span class="cloud-status cloud-online">☁️ Cloud AI Online</span>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<span class="cloud-status cloud-offline">☁️ Cloud AI Offline</span>', unsafe_allow_html=True)
    
    st.sidebar.divider()
    
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
            if st.sidebar.button("🌐 Open Kite Login", use_container_width=True):
                kite_temp = KiteConnect(api_key=API_KEY)
                login_url = kite_temp.login_url()
                webbrowser.open(login_url)
                st.sidebar.success("Browser opened!")
            
            st.sidebar.markdown("**Step 2:** Copy `request_token` from URL")
            request_token = st.sidebar.text_input("Request Token", placeholder="Paste request_token here")
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("✅ Get Token", use_container_width=True):
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
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state.show_generate_flow = False
                    st.rerun()
        else:
            st.sidebar.subheader("🔑 Enter Access Token")
            token_input = st.sidebar.text_input("Access Token", value=st.session_state.access_token, type="password")
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                if st.button("🔌 Connect", use_container_width=True):
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
                if st.button("🔄 Generate", use_container_width=True):
                    st.session_state.show_generate_flow = True
                    st.rerun()
    
    st.sidebar.divider()
    
    # Cloud API Settings
    st.sidebar.subheader("☁️ Cloud API Settings")
    
    new_api_url = st.sidebar.text_input(
        "API URL",
        value=CLOUD_API_URL,
        help="URL of deployed Gemini ADK Agents API"
    )
    
    new_api_key = st.sidebar.text_input(
        "API Key",
        value=CLOUD_API_KEY,
        type="password",
        help="X-API-Key for authentication"
    )
    
    if st.sidebar.button("🔄 Reconnect Cloud", use_container_width=True):
        config = CloudAPIConfig(base_url=new_api_url, api_key=new_api_key)
        st.session_state.cloud_client = CloudAPIClient(config)
        result = check_cloud_status()
        if result.get("status") == "online":
            st.sidebar.success("Cloud API connected!")
            add_log("Cloud API connected", "success")
        else:
            st.sidebar.error(f"Connection failed: {result.get('error')}")
        st.rerun()
    
    st.sidebar.divider()
    
    # Mode Settings
    st.sidebar.subheader("⚙️ Mode Settings")
    
    live_mode = st.sidebar.toggle(
        "🔴 Live Mode",
        value=not trader.config.dry_run,
        help="OFF = Dry Run (simulated), ON = LIVE (real orders)"
    )
    trader.config.dry_run = not live_mode
    
    st.sidebar.divider()
    
    # Risk Settings (collapsed)
    with st.sidebar.expander("🛡️ Risk Controls"):
        trader.config.risk.max_sector_exposure = st.slider(
            "Max Sector Exposure", 0.10, 0.50, trader.config.risk.max_sector_exposure, 0.05
        )
        trader.config.risk.max_drawdown_limit = st.slider(
            "Max Drawdown Limit", 0.05, 0.20, trader.config.risk.max_drawdown_limit, 0.01
        )
        trader.config.risk.max_stocks_per_sector = st.number_input(
            "Max Stocks/Sector", 1, 10, trader.config.risk.max_stocks_per_sector
        )
        trader.config.risk.require_above_50dma = st.checkbox(
            "Require > 50 DMA", value=trader.config.risk.require_above_50dma
        )
        trader.config.risk.require_above_200dma = st.checkbox(
            "Require > 200 DMA", value=trader.config.risk.require_above_200dma
        )
    
    # Budget Settings (collapsed)
    with st.sidebar.expander("💰 Budget Settings"):
        trader.config.daily_budget = float(st.number_input(
            "Daily Budget (₹)", 1000, 10000000, int(trader.config.daily_budget), 5000
        ))
        trader.config.per_stock_daily_budget = float(st.number_input(
            "Per-Stock Budget (₹)", 1000, 100000, int(trader.config.per_stock_daily_budget), 1000
        ))
        trader.config.max_qty_per_stock = st.number_input(
            "Max Qty/Stock", 1, 1000, trader.config.max_qty_per_stock, 50
        )
    
    st.sidebar.divider()
    
    # Market Status
    st.sidebar.subheader("🕐 Market Status")
    st.sidebar.write(f"Time: {datetime.now().strftime('%H:%M:%S')}")
    
    if trader.is_market_hours():
        st.sidebar.success("📈 Market OPEN")
    else:
        st.sidebar.warning("📉 Market CLOSED")
    
    return {'refresh': st.sidebar.toggle("🔄 Auto Refresh", value=False)}


# ==================== CLOUD AI RESEARCH TAB ====================

def display_cloud_ai_research():
    """Display Cloud AI Research tab"""
    st.header("🤖 Cloud AI Research")
    st.caption("Powered by Gemini ADK Agents on Google Cloud Run")
    
    client = st.session_state.cloud_client
    
    if not client:
        st.error("Cloud API client not available. Check cloud_api_client.py")
        return
    
    # Cloud Status Check
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Check Status", use_container_width=True):
            with st.spinner("Checking cloud..."):
                result = check_cloud_status()
                if result.get("status") == "online":
                    st.success("✅ Cloud Online")
                else:
                    st.error(f"❌ {result.get('error', 'Offline')}")
    
    with col1:
        status = st.session_state.cloud_status
        if status and status.get("online"):
            st.success(f"☁️ Cloud AI Online | Gemini: {'✅' if status.get('gemini') else '❌'}")
        else:
            st.warning("☁️ Cloud status unknown - click Check Status")
    
    st.divider()
    
    # Research Tabs
    research_tab, sentiment_tab, chat_tab, batch_tab = st.tabs([
        "🔍 Stock Research",
        "📊 Sentiment Analysis", 
        "💬 AI Chat",
        "📋 Batch Analysis"
    ])
    
    with research_tab:
        display_stock_research(client)
    
    with sentiment_tab:
        display_sentiment_analysis(client)
    
    with chat_tab:
        display_ai_chat(client)
    
    with batch_tab:
        display_batch_analysis(client)


def display_stock_research(client: CloudAPIClient):
    """Display stock research section"""
    st.subheader("🔍 Stock Research")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        query = st.text_input(
            "Research Query",
            placeholder="e.g., HDFCBANK stock analysis, IT sector outlook, Nifty technical levels",
            key="research_query"
        )
    
    with col2:
        num_results = st.number_input("Results", 5, 20, 10, key="research_num")
    
    if st.button("🔍 Research", type="primary", use_container_width=True, key="run_research"):
        if query:
            with st.spinner(f"Researching: {query}..."):
                result = client.research(query, num_results)
                
                if result.get("status") == "success":
                    st.success("Research complete!")
                    add_log(f"Cloud research: {query}", "success")
                    
                    data = result.get("result", {})
                    
                    # Display search results
                    if data.get("status") == "success":
                        results_list = data.get("results", [])
                        st.write(f"**Found {len(results_list)} results:**")
                        
                        for i, r in enumerate(results_list[:10], 1):
                            with st.expander(f"{i}. {r.get('title', 'No title')[:80]}..."):
                                st.write(f"**Source:** {r.get('link', 'N/A')}")
                                st.write(f"**Snippet:** {r.get('snippet', 'No snippet')}")
                    else:
                        st.warning(f"Research returned: {data.get('message', 'No data')}")
                else:
                    st.error(f"Research failed: {result.get('error', 'Unknown error')}")
                    add_log(f"Cloud research failed: {result.get('error')}", "error")
        else:
            st.warning("Enter a research query")


def display_sentiment_analysis(client: CloudAPIClient):
    """Display sentiment analysis section"""
    st.subheader("📊 AI Sentiment Analysis")
    
    symbol = st.text_input(
        "Stock Symbol",
        placeholder="e.g., HDFCBANK, TCS, RELIANCE",
        key="sentiment_symbol"
    ).upper()
    
    if st.button("🎯 Analyze Sentiment", type="primary", use_container_width=True, key="run_sentiment"):
        if symbol:
            with st.spinner(f"Analyzing {symbol}... (this may take 30-60 seconds)"):
                result = client.get_stock_sentiment(symbol)
                
                if result.get("status") == "success":
                    st.success(f"Sentiment analysis complete for {symbol}!")
                    add_log(f"Cloud sentiment: {symbol}", "success")
                    
                    ai_response = result.get("result", {}).get("response", "No response")
                    
                    st.markdown(f'<div class="ai-response">{ai_response}</div>', unsafe_allow_html=True)
                    
                    # Cache result
                    st.session_state.ai_research_cache[f"sentiment_{symbol}"] = {
                        "response": ai_response,
                        "timestamp": datetime.now()
                    }
                else:
                    st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
        else:
            st.warning("Enter a stock symbol")
    
    # Show cached results
    cached = [k for k in st.session_state.ai_research_cache.keys() if k.startswith("sentiment_")]
    if cached:
        with st.expander(f"📚 Cached Analyses ({len(cached)})"):
            for key in cached[-5:]:  # Last 5
                data = st.session_state.ai_research_cache[key]
                symbol = key.replace("sentiment_", "")
                st.write(f"**{symbol}** ({data['timestamp'].strftime('%H:%M')})")
                st.caption(data['response'][:200] + "...")


def display_ai_chat(client: CloudAPIClient):
    """Display AI chat section"""
    st.subheader("💬 Chat with Gemini AI")
    
    # System prompt
    system_prompt = st.text_area(
        "System Prompt (optional)",
        value="You are a helpful Indian stock market analyst. Provide concise, actionable insights.",
        height=80,
        key="chat_system"
    )
    
    # User message
    message = st.text_area(
        "Your Question",
        placeholder="e.g., What are the best sectors to invest in during monsoon season?",
        height=100,
        key="chat_message"
    )
    
    col1, col2 = st.columns([2, 2])
    with col1:
        # Model options with descriptions
        model_options = {
            "gemini-2.5-flash-lite": "💰 Cheapest - Ultra-fast",
            "gemini-2.5-flash": "⚡ Fast - Best balance (Recommended)",
            "gemini-2.5-pro": "🎯 Production - High quality",
            "gemini-3-flash-preview": "🔄 Preview - Balanced",
            "gemini-3.1-flash-lite-preview": "💰 Preview - Cheap & fast",
            "gemini-3.1-pro-preview": "🧠 Preview - Advanced reasoning",
        }
        selected_display = st.selectbox(
            "Model",
            list(model_options.values()),
            index=1,  # Default to gemini-2.5-flash
            key="chat_model_display"
        )
        # Get actual model ID from display name
        model = [k for k, v in model_options.items() if v == selected_display][0]
    
    with col2:
        st.caption("**Model Guide:**")
        st.caption("💰 = Cheapest | ⚡ = Fast | 🎯 = Quality | 🧠 = Smart")
    
    if st.button("💬 Send", type="primary", use_container_width=True, key="send_chat"):
        if message:
            with st.spinner("Thinking..."):
                result = client.chat(message, system_prompt, model)
                
                if result.get("status") == "success":
                    ai_response = result.get("result", {}).get("response", "No response")
                    st.markdown(f'<div class="ai-response"><strong>🤖 Gemini:</strong><br>{ai_response}</div>', unsafe_allow_html=True)
                    add_log("Cloud chat complete", "success")
                else:
                    st.error(f"Chat failed: {result.get('error', 'Unknown error')}")
        else:
            st.warning("Enter a message")


def display_batch_analysis(client: CloudAPIClient):
    """Display batch analysis for tips research stocks"""
    st.subheader("📋 Batch AI Analysis")
    st.caption("Analyze all stocks in tips_research_data.csv using Cloud AI")
    
    tips_path = REPO_ROOT / "data" / "tips_research_data.csv"
    
    if not tips_path.exists():
        st.warning("No tips_research_data.csv found. Generate one in Tips Research tab first.")
        return
    
    try:
        tips_df = pd.read_csv(tips_path)
        st.info(f"📊 Found {len(tips_df)} stocks in tips research data")
    except Exception as e:
        st.error(f"Error reading tips CSV: {e}")
        return
    
    # Show preview
    with st.expander("Preview Tips Data"):
        st.dataframe(tips_df.head(10), hide_index=True, use_container_width=True)
    
    # Analysis options
    col1, col2 = st.columns(2)
    with col1:
        top_n = st.slider("Analyze Top N stocks", 5, 40, 15, key="batch_top_n")
    with col2:
        analysis_type = st.selectbox(
            "Analysis Focus",
            ["Full Analysis", "Quick Sentiment", "Sector Overview"],
            key="batch_type"
        )
    
    if st.button("🚀 Run Batch AI Analysis", type="primary", use_container_width=True, key="run_batch"):
        stocks_to_analyze = tips_df.head(top_n).to_dict('records')
        
        with st.spinner(f"Analyzing {len(stocks_to_analyze)} stocks with Cloud AI..."):
            result = client.analyze_tips_stocks(stocks_to_analyze)
            
            if result.get("status") == "success":
                st.success("Batch analysis complete!")
                add_log(f"Cloud batch analysis: {len(stocks_to_analyze)} stocks", "success")
                
                ai_response = result.get("result", {}).get("response", "No response")
                
                st.markdown("### 🤖 AI Analysis Results")
                st.markdown(f'<div class="ai-response">{ai_response}</div>', unsafe_allow_html=True)
                
                # Save to file
                report_path = REPO_ROOT / "data" / "cloud_ai_analysis.md"
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Cloud AI Analysis Report\n\n")
                    f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write(f"**Stocks Analyzed:** {len(stocks_to_analyze)}\n\n")
                    f.write("---\n\n")
                    f.write(ai_response)
                
                st.success(f"📄 Report saved to {report_path}")
            else:
                st.error(f"Batch analysis failed: {result.get('error', 'Unknown error')}")


# ==================== ENHANCED TIPS RESEARCH ====================

def display_tips_research_v3():
    """Display enhanced tips research with Cloud AI integration"""
    trader = st.session_state.trader
    client = st.session_state.cloud_client
    
    st.header("📰 Tips Research Manager V3")
    st.caption("Enhanced with Cloud AI analysis")
    
    tips_path = REPO_ROOT / "data" / "tips_research_data.csv"
    research_path = REPO_ROOT / "data" / "research_data.csv"
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Current tips data
        st.subheader("📊 Current Tips Universe")
        
        if tips_path.exists():
            try:
                tips_df = pd.read_csv(tips_path)
                modified_time = datetime.fromtimestamp(tips_path.stat().st_mtime)
                st.info(f"📅 Last updated: {modified_time.strftime('%Y-%m-%d %H:%M:%S')} | 📈 {len(tips_df)} stocks")
                
                # Column config for better display
                column_config = {
                    "Symbol": st.column_config.TextColumn("Symbol", width="small"),
                    "Quantity": st.column_config.NumberColumn("Qty", width="small"),
                    "Price": st.column_config.NumberColumn("Price", format="₹%.2f", width="small"),
                    "Rank": st.column_config.TextColumn("Rank", width="small"),
                    "Recommendation": st.column_config.TextColumn("Reco", width="small"),
                    "DMA50": st.column_config.NumberColumn("DMA50", format="%.2f", width="small"),
                    "RSI14": st.column_config.NumberColumn("RSI", format="%.1f", width="small"),
                    "Momentum_Score": st.column_config.NumberColumn("Mom", width="small"),
                }
                
                st.dataframe(tips_df, hide_index=True, use_container_width=True, height=400, column_config=column_config)
            except Exception as e:
                st.error(f"Error reading tips CSV: {e}")
        else:
            st.warning("No tips_research_data.csv found. Generate one below.")
    
    with col2:
        st.subheader("🔄 Generate Tips")
        
        # Budget settings
        daily_budget = st.number_input(
            "Daily Budget (₹)", 10000, 10000000, int(trader.config.daily_budget), 10000,
            key="tips_budget"
        )
        per_stock_budget = st.number_input(
            "Per-Stock Budget (₹)", 1000, 100000, int(trader.config.per_stock_daily_budget), 1000,
            key="tips_per_stock"
        )
        max_qty = st.number_input(
            "Max Qty/Stock", 1, 1000, trader.config.max_qty_per_stock, 50,
            key="tips_max_qty"
        )
        
        st.divider()
        
        # Generate button
        if TIPS_AGENT_AVAILABLE:
            if st.button("🚀 Generate Tips CSV", type="primary", use_container_width=True, key="gen_tips"):
                if st.session_state.access_token:
                    os.environ["ACCESS_TOKEN"] = st.session_state.access_token
                if API_KEY:
                    os.environ["API_KEY"] = API_KEY
                
                with st.spinner("Generating tips_research_data.csv..."):
                    try:
                        result = generate_tips_research_data_csv(
                            top_n_rank=None,
                            daily_budget=daily_budget,
                            per_stock_budget=per_stock_budget,
                            max_qty_per_stock=max_qty,
                        )
                        
                        if result.get("status") == "success":
                            st.success(f"✅ Generated {result.get('count')} stocks")
                            add_log(f"Tips CSV generated: {result.get('count')} stocks", "success")
                        else:
                            st.error(f"Failed: {result.get('message')}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                
                st.rerun()
        else:
            st.warning("tips_research_agent not available - Use Cloud AI Research below")
        
        st.divider()
        
        # Cloud AI Research with Web Search
        st.subheader("🤖 Cloud AI Research (with Web Search)")
        st.caption("Searches financial sources + AI analysis for each stock")
        
        if client and tips_path.exists():
            col1, col2 = st.columns(2)
            with col1:
                max_stocks = st.slider("Max Stocks to Research", 3, 20, 10, key="tips_max_stocks")
            with col2:
                search_per_stock = st.slider("Search Results/Stock", 3, 10, 5, key="tips_search_per")
            
            if st.button("🔍 Research Stocks from Tips CSV", type="primary", use_container_width=True, key="cloud_tips_research"):
                with st.spinner(f"Researching {max_stocks} stocks from financial sources..."):
                    try:
                        tips_df = pd.read_csv(tips_path)
                        stocks = tips_df.head(max_stocks).to_dict('records')
                        
                        st.info(f"📊 Researching {len(stocks)} stocks using: moneycontrol, screener.in, tickertape, economictimes...")
                        
                        # Call the new tips-research endpoint
                        result = client.tips_research(stocks, max_stocks=max_stocks, search_per_stock=search_per_stock)
                        
                        if result.get("status") == "success":
                            st.success(f"✅ Research complete for {result.get('result', {}).get('stocks_analyzed', 0)} stocks!")
                            
                            # Show AI Recommendations
                            ai_recommendations = result.get("result", {}).get("ai_recommendations", "")
                            st.markdown("### 🎯 AI Recommendations")
                            st.markdown(ai_recommendations)
                            
                            # Show research data in expander
                            with st.expander("📚 Raw Research Data"):
                                research_data = result.get("result", {}).get("research_data", [])
                                for r in research_data:
                                    st.markdown(f"**{r['symbol']}** (₹{r['price']}, Rank: {r['rank']})")
                                    st.caption(r['research_context'][:500] + "..." if len(r['research_context']) > 500 else r['research_context'])
                                    st.divider()
                            
                            # Save analysis report
                            report_path = APP_ROOT / "data" / "cloud_ai_tips_analysis.md"
                            with open(report_path, 'w', encoding='utf-8') as f:
                                f.write(f"# Cloud AI Tips Research Report\n\n")
                                f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"**Stocks Analyzed:** {len(stocks)}\n")
                                f.write(f"**Sources:** moneycontrol, screener.in, tickertape, economictimes, trendlyne\n\n")
                                f.write("---\n\n")
                                f.write("## AI Recommendations\n\n")
                                f.write(ai_recommendations)
                                f.write("\n\n---\n\n## Raw Research Data\n\n")
                                for r in research_data:
                                    f.write(f"### {r['symbol']} (₹{r['price']}, Rank: {r['rank']})\n")
                                    f.write(f"{r['research_context']}\n\n")
                            
                            st.success(f"📄 Report saved to {report_path.name}")
                        else:
                            st.error(f"Failed: {result.get('error')}")
                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback
                        st.code(traceback.format_exc())
            
            st.divider()
            
            # Quick AI Analysis (no web search - faster)
            st.subheader("⚡ Quick AI Analysis (No Web Search)")
            if st.button("🧠 Quick Analysis", use_container_width=True, key="cloud_quick"):
                with st.spinner("Running quick AI analysis..."):
                    try:
                        tips_df = pd.read_csv(tips_path)
                        stocks = tips_df.head(20).to_dict('records')
                        
                        result = client.analyze_tips_stocks(stocks)
                        
                        if result.get("status") == "success":
                            st.success("Quick analysis complete!")
                            ai_response = result.get("result", {}).get("response", "")
                            st.markdown(ai_response)
                        else:
                            st.error(f"Failed: {result.get('error')}")
                    except Exception as e:
                        st.error(f"Error: {e}")
        else:
            st.info("Upload or generate tips_research_data.csv first")
        
        st.divider()
        
        # Reports
        st.subheader("📄 Reports")
        
        report_files = [
            ("tips_research_report.md", "📊 Research Report"),
            ("advisor_report.md", "🎯 Advisor Report"),
            ("cloud_ai_tips_analysis.md", "🤖 Cloud AI Analysis"),
        ]
        
        for filename, label in report_files:
            path = APP_ROOT / "data" / filename
            if path.exists():
                with st.expander(label):
                    st.markdown(path.read_text(encoding='utf-8')[:3000] + "...")


# ==================== RISK DASHBOARD ====================

def display_risk_dashboard():
    """Display portfolio risk dashboard"""
    trader = st.session_state.trader
    
    st.header("🛡️ Risk Dashboard")
    
    if not trader.connected:
        st.warning("Connect to Kite to view risk metrics")
        return
    
    summary = trader.get_portfolio_summary()
    
    # Top metrics
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
        st.metric("Drawdown", f"{drawdown_pct:.1f}%")
    
    st.divider()
    
    # Sector exposure
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🏢 Sector Exposure")
        if summary['sector_exposure']:
            sector_df = pd.DataFrame([
                {'Sector': sector, 'Exposure': f"{exp:.1%}", 'Stocks': summary['sector_counts'].get(sector, 0)}
                for sector, exp in sorted(summary['sector_exposure'].items(), key=lambda x: -x[1])
            ])
            st.dataframe(sector_df, hide_index=True, use_container_width=True)
    
    with col2:
        st.subheader("📊 Risk Status")
        drawdown_ok = summary['current_drawdown'] < trader.config.risk.max_drawdown_limit
        st.markdown(f"**Drawdown:** {'✅' if drawdown_ok else '❌'} {summary['current_drawdown']:.1%}")
        
        max_sector = summary.get('max_sector', 0)
        sector_ok = max_sector <= trader.config.risk.max_sector_exposure
        st.markdown(f"**Sector Concentration:** {'✅' if sector_ok else '⚠️'} {max_sector:.1%}")


# ==================== HOLDINGS ANALYSIS ====================

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
            'Avg': f"₹{avg_price:,.2f}",
            'LTP': f"₹{ltp:,.2f}",
            'P&L': f"₹{h.get('pnl', 0):,.0f}",
            'Gain%': f"{gain_pct:+.1f}%",
            '50DMA': '✅' if analysis.above_50dma else '❌',
        })
    
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ==================== TRADE ACTIONS ====================

def display_action_buttons(options: Dict):
    """Display trading action buttons"""
    trader = st.session_state.trader
    
    st.header("🎯 Trading Operations")
    
    if not trader.config.dry_run:
        st.error("⚠️ LIVE MODE - Real orders will be executed!")
    else:
        st.info("🔒 DRY RUN MODE - No real orders")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("📈 Smart Invest")
        
        top_n_options = {"Top 5": 5, "Top 10": 10, "Top 15": 15, "Top 25": 25, "All": 0}
        selected = st.selectbox("Rank Filter", list(top_n_options.keys()), index=2, key="smart_top_n")
        top_n = top_n_options[selected]
        
        if st.button("🚀 Run Smart Investment", type="primary", use_container_width=True, key="smart_invest"):
            if not trader.connected:
                st.error("Connect first!")
            else:
                with st.spinner(f"Running smart investment (Top{top_n if top_n > 0 else 'All'})..."):
                    results = trader.run_simple_investment(top_n=top_n)
                    
                    if 'error' in results:
                        st.error(results['error'])
                    else:
                        st.success(f"Analyzed: {results['analyzed']}, Bought: {results['bought']}")
                        
                        if results.get('details'):
                            st.dataframe(pd.DataFrame(results['details']), hide_index=True)
    
    with col2:
        st.subheader("🛡️ Protection")
        
        if st.button("🛡️ Protect Holdings", use_container_width=True, key="protect"):
            if trader.connected:
                with st.spinner("Protecting..."):
                    count = trader.protect_holdings_smart(refresh=options.get('refresh', False))
                    st.success(f"Protected {count} holdings")
    
    with col3:
        st.subheader("📉 Selling")
        
        if st.button("🔴 Sell Negative P&L", use_container_width=True, key="sell_neg"):
            if trader.connected:
                negative = trader.get_negative_holdings()
                if negative:
                    with st.spinner("Selling..."):
                        count = trader.sell_negative_holdings()
                        st.success(f"Sold {count} stocks")
                else:
                    st.info("No negative holdings")


# ==================== LOGS ====================

def display_logs():
    """Display activity logs"""
    st.subheader("📜 Activity Log")
    
    if not st.session_state.logs:
        st.info("No activity yet")
        return
    
    for log in reversed(st.session_state.logs[-20:]):
        level = log['level']
        icon = {'error': '❌', 'warning': '⚠️', 'success': '✅'}.get(level, 'ℹ️')
        st.write(f"{icon} [{log['time']}] {log['message']}")


# ==================== MAIN ====================

def main():
    """Main application entry point"""
    
    # Check authentication
    if check_auth_enabled():
        if not check_session_valid():
            login_page()
            return
    
    # Page configuration (only after auth check)
    st.set_page_config(
        page_title="Kite Trading V3 - Cloud AI",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Apply custom CSS
    apply_custom_css()
    
    init_session_state()
    setup_trader_logging()
    
    # Check cloud status on startup
    if st.session_state.cloud_status is None and CLOUD_API_AVAILABLE:
        check_cloud_status()
    
    # Title with user info
    col_title, col_user = st.columns([4, 1])
    with col_title:
        st.title("🤖 Kite Trading V3 - Cloud AI Enhanced")
        st.caption("Risk management + Cloud AI research via Gemini ADK Agents")
    with col_user:
        if check_auth_enabled() and st.session_state.get('username'):
            st.markdown(f"👤 **{st.session_state.username}**")
            if st.button("🚪 Logout", key="logout_main"):
                logout()
    
    # Sidebar
    options = display_sidebar()
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🤖 Cloud AI Research",
        "🛡️ Risk Dashboard",
        "📊 Holdings",
        "🎯 Trade",
        "📰 Tips Research",
        "📜 Logs"
    ])
    
    with tab1:
        display_cloud_ai_research()
    
    with tab2:
        display_risk_dashboard()
    
    with tab3:
        display_holdings_analysis()
    
    with tab4:
        display_action_buttons(options)
    
    with tab5:
        display_tips_research_v3()
    
    with tab6:
        display_logs()


if __name__ == "__main__":
    main()
