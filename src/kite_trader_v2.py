"""
KiteTrader V2 - Enhanced Risk Management Edition

Key Improvements over V1:
1. Portfolio-Level Risk Control (sector exposure, drawdown limit)
2. ATR-Based Dynamic Stop Loss (volatility-adjusted)
3. Momentum/Trend Filter (DMA check before buying)
4. Exit Strategy for Winners (trailing stop, partial profit booking)
5. Simplified Long-Term Investing (less over-trading)
"""

import os
import csv
import time
import math
import random
import shutil
import logging
import re
import json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Set, Tuple
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== SECTOR MAPPING ====================
# Common Indian stocks to sector mapping (extend as needed)
SECTOR_MAPPING = {
    # Banking & Finance
    'HDFCBANK': 'Banking', 'ICICIBANK': 'Banking', 'SBIN': 'Banking',
    'KOTAKBANK': 'Banking', 'AXISBANK': 'Banking', 'INDUSINDBK': 'Banking',
    'BANKBARODA': 'Banking', 'PNB': 'Banking', 'FEDERALBNK': 'Banking',
    'IDFCFIRSTB': 'Banking', 'BANDHANBNK': 'Banking', 'AUBANK': 'Banking',
    'BAJFINANCE': 'NBFC', 'BAJAJFINSV': 'NBFC',
    'CHOLAFIN': 'NBFC', 'SHRIRAMFIN': 'NBFC', 'MUTHOOTFIN': 'NBFC',
    
    # IT
    'TCS': 'IT', 'INFY': 'IT', 'WIPRO': 'IT', 'HCLTECH': 'IT',
    'TECHM': 'IT', 'LTIM': 'IT', 'PERSISTENT': 'IT', 'COFORGE': 'IT',
    'MPHASIS': 'IT', 'LTTS': 'IT', 'MINDTREE': 'IT', 'NIITTECH': 'IT',
    
    # Pharma/Healthcare
    'SUNPHARMA': 'Pharma', 'DRREDDY': 'Pharma', 'CIPLA': 'Pharma',
    'DIVISLAB': 'Pharma', 'BIOCON': 'Pharma', 'LUPIN': 'Pharma',
    'AUROPHARMA': 'Pharma', 'TORNTPHARM': 'Pharma', 'ALKEM': 'Pharma',
    'APOLLOHOSP': 'Healthcare', 'MAXHEALTH': 'Healthcare', 'FORTIS': 'Healthcare',
    
    # Auto
    'MARUTI': 'Auto', 'TATAMOTORS': 'Auto', 'M&M': 'Auto',
    'BAJAJ-AUTO': 'Auto', 'HEROMOTOCO': 'Auto', 'EICHERMOT': 'Auto',
    'ASHOKLEY': 'Auto', 'TVSMOTOR': 'Auto', 'BHARATFORG': 'Auto',
    
    # Energy/Oil & Gas
    'RELIANCE': 'Energy', 'ONGC': 'Energy', 'IOC': 'Energy',
    'BPCL': 'Energy', 'HPCL': 'Energy', 'GAIL': 'Energy',
    'NTPC': 'Power', 'POWERGRID': 'Power', 'ADANIGREEN': 'Power',
    'TATAPOWER': 'Power', 'ADANIPOWER': 'Power', 'TORNTPOWER': 'Power',
    
    # Metals
    'TATASTEEL': 'Metals', 'JSWSTEEL': 'Metals', 'HINDALCO': 'Metals',
    'VEDL': 'Metals', 'COALINDIA': 'Metals', 'NMDC': 'Metals',
    'SAIL': 'Metals', 'NATIONALUM': 'Metals', 'JINDALSTEL': 'Metals',
    
    # FMCG
    'HINDUNILVR': 'FMCG', 'ITC': 'FMCG', 'NESTLEIND': 'FMCG',
    'BRITANNIA': 'FMCG', 'DABUR': 'FMCG', 'MARICO': 'FMCG',
    'COLPAL': 'FMCG', 'GODREJCP': 'FMCG', 'TATACONSUM': 'FMCG',
    
    # Cement/Construction
    'ULTRACEMCO': 'Cement', 'SHREECEM': 'Cement', 'AMBUJACEM': 'Cement',
    'ACC': 'Cement', 'DALMIACEM': 'Cement', 'RAMCOCEM': 'Cement',
    'LARSEN': 'Infrastructure', 'LT': 'Infrastructure', 'DLF': 'Realty',
    'GODREJPROP': 'Realty', 'OBEROIRLTY': 'Realty', 'PRESTIGE': 'Realty',
    
    # Telecom
    'BHARTIARTL': 'Telecom', 'INDIAMART': 'Telecom', 'ZOMATO': 'Internet',
    'NAUKRI': 'Internet', 'PAYTM': 'Internet', 'POLICYBZR': 'Internet',
    
    # Consumer Durables
    'TITAN': 'Consumer', 'HAVELLS': 'Consumer', 'VOLTAS': 'Consumer',
    'WHIRLPOOL': 'Consumer', 'BLUESTAR': 'Consumer', 'CROMPTON': 'Consumer',
}


@dataclass
class RiskConfig:
    """Portfolio-level risk configuration"""
    # Sector concentration limits
    max_sector_exposure: float = 0.30  # Max 30% in any single sector
    
    # Portfolio drawdown protection
    max_drawdown_limit: float = 0.10  # Stop buying when portfolio down 10%
    
    # Correlation protection (simplified: limit similar sector stocks)
    max_stocks_per_sector: int = 3
    
    # Momentum filter
    require_above_50dma: bool = True
    require_above_200dma: bool = False  # More aggressive filter
    
    # ATR-based stop loss (multiples of ATR)
    use_atr_stop_loss: bool = True
    atr_sl_multiple: float = 2.0  # SL at 2x ATR below entry
    atr_period: int = 14  # Days for ATR calculation
    min_stop_loss: float = 0.05  # Floor at 5%
    max_stop_loss: float = 0.15  # Cap at 15%
    
    # Trailing stop settings
    enable_trailing_stop: bool = True
    trailing_activation_pct: float = 0.08  # Activate after +8% gain
    trailing_stop_pct: float = 0.05  # Trail 5% below peak
    
    # Partial profit booking
    enable_partial_exit: bool = True
    partial_exit_trigger_pct: float = 0.10  # Book partial at +10%
    partial_exit_qty_pct: float = 0.50  # Sell 50% at target


@dataclass
class TraderConfigV2:
    """Configuration for KiteTrader V2"""
    # API Credentials
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    
    # Mode Settings
    dry_run: bool = True
    use_budget_mode: bool = True
    
    # File Settings
    order_book_file: str = "data/order_book.csv"
    research_file: str = "data/research_data.csv"
    
    # Budget Settings
    daily_budget: float = 100000.0
    per_stock_daily_budget: float = 10000.0
    max_qty_per_stock: int = 500  # Handle cheap stocks (₹20-50)
    
    # Simplified buying (long-term mode)
    buy_frequency: str = "weekly"  # daily, weekly, monthly
    min_days_between_buys: int = 7  # For same stock
    
    # Stop Loss Settings (base - adjusted by ATR)
    stop_loss_percent: float = 0.08
    target_percent: float = 0.16
    
    # GTT Settings
    gtt_buy_lower_percent: float = 0.05  # 5% dip buy
    gtt_buy_budget_per_stock: float = 10000.0
    
    # Risk configuration
    risk: RiskConfig = field(default_factory=RiskConfig)
    
    # Market Hours (IST)
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 29
    
    # Tick size
    default_tick: Decimal = Decimal("0.05")

    @classmethod
    def from_env(cls) -> 'TraderConfigV2':
        """Create config from environment variables"""
        risk = RiskConfig(
            max_sector_exposure=float(os.getenv("MAX_SECTOR_EXPOSURE", "0.30")),
            max_drawdown_limit=float(os.getenv("MAX_DRAWDOWN_LIMIT", "0.10")),
            max_stocks_per_sector=int(os.getenv("MAX_STOCKS_PER_SECTOR", "3")),
            require_above_50dma=os.getenv("REQUIRE_50DMA", "true").lower() == "true",
            require_above_200dma=os.getenv("REQUIRE_200DMA", "false").lower() == "true",
            use_atr_stop_loss=os.getenv("USE_ATR_SL", "true").lower() == "true",
            atr_sl_multiple=float(os.getenv("ATR_SL_MULTIPLE", "2.0")),
            trailing_activation_pct=float(os.getenv("TRAILING_ACTIVATION_PCT", "0.08")),
            trailing_stop_pct=float(os.getenv("TRAILING_STOP_PCT", "0.05")),
            partial_exit_trigger_pct=float(os.getenv("PARTIAL_EXIT_PCT", "0.10")),
        )
        
        return cls(
            api_key=os.getenv("API_KEY", ""),
            api_secret=os.getenv("API_SECRET", ""),
            access_token=os.getenv("ACCESS_TOKEN", ""),
            daily_budget=float(os.getenv("DAILY_BUDGET", "100000")),
            per_stock_daily_budget=float(os.getenv("PER_STOCK_DAILY_BUDGET", "10000")),
            max_qty_per_stock=int(os.getenv("MAX_QTY_PER_STOCK", "500")),
            stop_loss_percent=float(os.getenv("STOP_LOSS_PERCENT", "0.08")),
            target_percent=float(os.getenv("TARGET_PERCENT", "0.16")),
            gtt_buy_budget_per_stock=float(os.getenv("GTT_BUY_BUDGET_PER_STOCK", "10000")),
            buy_frequency=os.getenv("BUY_FREQUENCY", "weekly"),
            risk=risk,
        )


@dataclass
class OrderResult:
    """Structured result from order placement"""
    success: bool
    dry_run: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[str] = None  # Why order was blocked


@dataclass
class StockAnalysis:
    """Analysis result for a stock"""
    symbol: str
    ltp: float
    dma_50: Optional[float] = None
    dma_200: Optional[float] = None
    atr: Optional[float] = None
    sector: str = "Unknown"
    above_50dma: bool = False
    above_200dma: bool = False
    suggested_sl_pct: float = 0.08
    passes_momentum: bool = True
    reason: str = ""


class KiteTraderV2:
    """
    KiteTrader V2 - Enhanced Risk Management
    
    Key Features:
    - Portfolio risk limits (sector, drawdown)
    - ATR-based dynamic stop loss
    - Momentum filters (DMA)
    - Trailing stops & partial exits
    - Long-term investing mode
    """
    
    def __init__(self, config: TraderConfigV2 = None):
        """Initialize KiteTrader V2"""
        self.config = config or TraderConfigV2.from_env()
        self.kite: Optional[KiteConnect] = None
        self.connected: bool = False
        self.user_name: str = ""
        self.user_id: str = ""
        
        # Tracking
        self.bought_tracker: Dict[str, int] = {}
        
        # Historical data cache
        self._historical_cache: Dict[str, List[Dict]] = {}
        
        # Instruments cache (to avoid repeated full list fetches)
        self._instruments_cache: Dict[str, List[Dict]] = {}
        self._instruments_cache_time: Dict[str, datetime] = {}
        
        # Rate limiting for historical API calls
        self._last_historical_call: Optional[datetime] = None
        self._historical_call_delay: float = 0.35  # 350ms between calls (Kite allows ~3/sec)
        
        # Tick size cache
        self._tick_size_map: Dict[str, Dict[str, Decimal]] = {}
        
        # Portfolio state
        self._portfolio_peak: float = 0.0
        self._last_buy_dates: Dict[str, datetime] = {}
        self._last_buy_dates_file = Path(__file__).resolve().parents[1] / "data" / "last_buy_dates.json"
        self._load_last_buy_dates()
        
        # Trailing stop tracking (symbol -> peak price after +8%)
        self._trailing_peaks: Dict[str, float] = {}
        self._trailing_peaks_file = Path(__file__).resolve().parents[1] / "data" / "trailing_peaks.json"
        self._load_trailing_peaks()
        
        # Audit log file (JSON lines)
        self._audit_log_file = Path(__file__).resolve().parents[1] / "data" / "audit_log.jsonl"
        
        # Analysis cache (cleared each session, avoids repeated API calls)
        self._analysis_cache: Dict[str, StockAnalysis] = {}
        
        # Holdings cache (refreshed explicitly)
        self._holdings_cache: Optional[List[Dict]] = None
        self._holdings_cache_time: Optional[datetime] = None
        
        # Callbacks
        self.on_log: Optional[Callable[[str, str], None]] = None
    
    def _load_last_buy_dates(self):
        """Load last buy dates from JSON file"""
        try:
            if self._last_buy_dates_file.exists():
                with open(self._last_buy_dates_file, 'r') as f:
                    data = json.load(f)
                    # Convert ISO strings back to datetime
                    self._last_buy_dates = {
                        symbol: datetime.fromisoformat(dt_str)
                        for symbol, dt_str in data.items()
                    }
        except Exception:
            self._last_buy_dates = {}
    
    def _save_last_buy_dates(self):
        """Save last buy dates to JSON file"""
        try:
            self._last_buy_dates_file.parent.mkdir(parents=True, exist_ok=True)
            # Convert datetime to ISO strings for JSON
            data = {
                symbol: dt.isoformat()
                for symbol, dt in self._last_buy_dates.items()
            }
            with open(self._last_buy_dates_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.log(f"Could not save last buy dates: {e}", "warning")
    
    def _load_trailing_peaks(self):
        """Load trailing peaks from JSON file"""
        try:
            if self._trailing_peaks_file.exists():
                with open(self._trailing_peaks_file, 'r') as f:
                    self._trailing_peaks = json.load(f)
        except Exception:
            self._trailing_peaks = {}
    
    def _save_trailing_peaks(self):
        """Save trailing peaks to JSON file"""
        try:
            self._trailing_peaks_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._trailing_peaks_file, 'w') as f:
                json.dump(self._trailing_peaks, f, indent=2)
        except Exception as e:
            self.log(f"Could not save trailing peaks: {e}", "warning")
    
    def _audit_log(self, event: str, data: Dict):
        """Append structured audit log entry (JSON lines format)"""
        try:
            self._audit_log_file.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": datetime.now().isoformat(),
                "event": event,
                **data
            }
            with open(self._audit_log_file, 'a') as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Silent fail for audit logging
    
    def clear_analysis_cache(self):
        """Clear the analysis cache (call when you want fresh data)"""
        self._analysis_cache.clear()
        self._holdings_cache = None
        self._holdings_cache_time = None
    
    def log(self, message: str, level: str = "info"):
        """Log a message"""
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)
        
        if self.on_log:
            self.on_log(message, level)
    
    # ==================== CONNECTION ====================
    
    def connect(self, access_token: str = None) -> bool:
        """Connect to Kite API"""
        try:
            token = access_token or self.config.access_token
            if not self.config.api_key:
                self.log("API_KEY not found", "error")
                return False
            if not token:
                self.log("Access token required", "error")
                return False
            
            self.kite = KiteConnect(api_key=self.config.api_key)
            self.kite.set_access_token(token)
            self.config.access_token = token
            
            profile = self.kite.profile()
            self.user_name = profile.get('user_name', 'User')
            self.user_id = profile.get('user_id', '')
            self.connected = True
            
            self.log(f"Connected as {self.user_name}", "success")
            return True
        except Exception as e:
            self.log(f"Connection failed: {str(e)}", "error")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from Kite API"""
        self.kite = None
        self.connected = False
        self.log("Disconnected", "info")
    
    def validate_connection(self) -> bool:
        """Check if connected"""
        if not self.connected or not self.kite:
            self.log("Not connected to Kite", "error")
            return False
        return True
    
    # ==================== UTILITIES ====================
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now()
        market_open = now.replace(hour=self.config.market_open_hour, minute=self.config.market_open_minute, second=0)
        market_close = now.replace(hour=self.config.market_close_hour, minute=self.config.market_close_minute, second=0)
        return market_open <= now <= market_close
    
    def with_backoff(self, fn, *args, retries: int = 3, base: float = 0.5, **kwargs):
        """Execute function with exponential backoff (rate-limit aware)"""
        last_error = None
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                
                # Detect rate limiting and use longer delays
                if 'too many requests' in error_msg or 'rate limit' in error_msg:
                    wait = 2.0 * (2 ** attempt) + random.uniform(0.5, 1.5)  # 2s, 4s, 8s...
                    self.log(f"Rate limited, waiting {wait:.1f}s before retry...", "warning")
                else:
                    wait = base * (2 ** attempt) + random.uniform(0, 0.1)
                
                if attempt < retries - 1:
                    time.sleep(wait)
        raise last_error
    
    def get_tick_size(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Return tick size for a symbol"""
        exchange = (exchange or "NSE").upper()
        symbol = (symbol or "").strip().upper()
        if not symbol:
            return self.config.default_tick

        if exchange not in self._tick_size_map:
            self._tick_size_map[exchange] = {}

        cached = self._tick_size_map[exchange].get(symbol)
        if cached is not None:
            return cached

        if not self.connected or not self.kite:
            return self.config.default_tick

        try:
            if not self._tick_size_map[exchange]:
                instruments = self.with_backoff(self.kite.instruments, exchange)
                for inst in instruments:
                    ts = (inst.get('tradingsymbol') or '').strip().upper()
                    tick = inst.get('tick_size', None)
                    if ts:
                        self._tick_size_map[exchange][ts] = Decimal(str(tick)) if tick is not None else self.config.default_tick

            return self._tick_size_map[exchange].get(symbol, self.config.default_tick)
        except Exception as e:
            self.log(f"Tick size lookup failed for {symbol}: {e}", "warning")
            return self.config.default_tick
    
    def round_to_tick(self, price: float, *, symbol: Optional[str] = None, exchange: str = "NSE") -> float:
        """Round price to nearest valid tick"""
        d = Decimal(str(price))
        tick = self.get_tick_size(symbol, exchange) if symbol else self.config.default_tick
        return float((d / tick).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick)
    
    @staticmethod
    def safe_float(value, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_sector(self, symbol: str) -> str:
        """Get sector for a symbol"""
        return SECTOR_MAPPING.get(symbol.upper(), "Unknown")
    
    # ==================== DATA FETCHING ====================
    
    def get_holdings(self, use_cache: bool = True) -> List[Dict]:
        """Get all holdings with quantity > 0
        
        Args:
            use_cache: If True, return cached holdings if available (< 60s old)
        """
        # Check cache first
        if use_cache and self._holdings_cache is not None and self._holdings_cache_time:
            age = (datetime.now() - self._holdings_cache_time).total_seconds()
            if age < 60:  # Cache valid for 60 seconds
                return self._holdings_cache
        
        if not self.validate_connection():
            return self._holdings_cache or []
        try:
            holdings = self.with_backoff(self.kite.holdings)
            self._holdings_cache = [h for h in holdings if h.get('quantity', 0) > 0]
            self._holdings_cache_time = datetime.now()
            return self._holdings_cache
        except Exception as e:
            self.log(f"Error fetching holdings: {e}", "error")
            return self._holdings_cache or []
    
    def get_positions(self) -> Dict:
        """Get all positions"""
        if not self.validate_connection():
            return {'net': [], 'day': []}
        try:
            return self.with_backoff(self.kite.positions)
        except Exception as e:
            self.log(f"Error fetching positions: {e}", "error")
            return {'net': [], 'day': []}
    
    def get_orders(self) -> List[Dict]:
        """Get all orders for today"""
        if not self.validate_connection():
            return []
        try:
            return self.with_backoff(self.kite.orders)
        except Exception as e:
            self.log(f"Error fetching orders: {e}", "error")
            return []
    
    def get_gtts(self) -> List[Dict]:
        """Get all active GTT orders"""
        if not self.validate_connection():
            return []
        try:
            return self.with_backoff(self.kite.get_gtts)
        except Exception as e:
            self.log(f"Error fetching GTTs: {e}", "error")
            return []
    
    def get_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """Get last traded price for symbols"""
        if not self.validate_connection():
            return {}
        try:
            instruments = [f"NSE:{s}" for s in symbols]
            ltp_data = self.with_backoff(self.kite.ltp, instruments)
            return {
                s: ltp_data.get(f"NSE:{s}", {}).get('last_price', 0)
                for s in symbols
            }
        except Exception as e:
            self.log(f"Error fetching LTP: {e}", "error")
            return {}
    
    def _get_instruments_cached(self, exchange: str = "NSE") -> List[Dict]:
        """Get instruments list with caching (refreshed every 24h)"""
        exchange = exchange.upper()
        
        # Check if cache is valid (< 24 hours old)
        cache_time = self._instruments_cache_time.get(exchange)
        if exchange in self._instruments_cache and cache_time:
            age = (datetime.now() - cache_time).total_seconds()
            if age < 86400:  # 24 hours
                return self._instruments_cache[exchange]
        
        if not self.validate_connection():
            return self._instruments_cache.get(exchange, [])
        
        try:
            instruments = self.with_backoff(self.kite.instruments, exchange)
            self._instruments_cache[exchange] = instruments
            self._instruments_cache_time[exchange] = datetime.now()
            return instruments
        except Exception as e:
            self.log(f"Error fetching instruments: {e}", "warning")
            return self._instruments_cache.get(exchange, [])
    
    def _throttle_historical_call(self):
        """Enforce minimum delay between historical API calls"""
        if self._last_historical_call is not None:
            elapsed = (datetime.now() - self._last_historical_call).total_seconds()
            if elapsed < self._historical_call_delay:
                time.sleep(self._historical_call_delay - elapsed)
        self._last_historical_call = datetime.now()
    
    def get_historical_data(self, symbol: str, days: int = 200) -> List[Dict]:
        """Get historical OHLC data for a symbol (with rate limiting)"""
        if not self.validate_connection():
            return []
        
        cache_key = f"{symbol}_{days}"
        if cache_key in self._historical_cache:
            return self._historical_cache[cache_key]
        
        try:
            # Get instrument token from cached instruments list
            instruments = self._get_instruments_cached("NSE")
            token = None
            for inst in instruments:
                if inst.get('tradingsymbol', '').upper() == symbol.upper():
                    token = inst.get('instrument_token')
                    break
            
            if not token:
                self.log(f"Instrument token not found for {symbol}", "warning")
                return []
            
            # Throttle to avoid rate limiting
            self._throttle_historical_call()
            
            # Fetch historical data
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days)
            
            data = self.with_backoff(
                self.kite.historical_data,
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day",
                retries=4,  # More retries for historical data
                base=1.0    # Longer base delay
            )
            
            self._historical_cache[cache_key] = data
            return data
        except Exception as e:
            self.log(f"Error fetching historical data for {symbol}: {e}", "warning")
            return []
    
    # ==================== TECHNICAL ANALYSIS ====================
    
    def calculate_dma(self, symbol: str, period: int) -> Optional[float]:
        """Calculate Daily Moving Average"""
        data = self.get_historical_data(symbol, max(period + 10, 60))
        if len(data) < period:
            return None
        
        closes = [d['close'] for d in data[-period:]]
        return sum(closes) / len(closes)
    
    def calculate_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calculate Average True Range (volatility measure)"""
        data = self.get_historical_data(symbol, period + 10)
        if len(data) < period + 1:
            return None
        
        true_ranges = []
        for i in range(1, len(data)):
            high = data[i]['high']
            low = data[i]['low']
            prev_close = data[i-1]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Take last 'period' values
        recent_tr = true_ranges[-period:]
        return sum(recent_tr) / len(recent_tr)
    
    def analyze_stock(self, symbol: str, ltp: float = None, use_cache: bool = True) -> StockAnalysis:
        """Perform comprehensive analysis of a stock
        
        Args:
            symbol: Stock symbol
            ltp: Last traded price (fetched if not provided)
            use_cache: If True, return cached analysis if available
        """
        cache_key = f"{symbol}_{ltp or 'auto'}"
        if use_cache and cache_key in self._analysis_cache:
            return self._analysis_cache[cache_key]
        
        if ltp is None:
            ltp_map = self.get_ltp([symbol])
            ltp = ltp_map.get(symbol, 0)
        
        analysis = StockAnalysis(
            symbol=symbol,
            ltp=ltp,
            sector=self.get_sector(symbol)
        )
        
        if ltp <= 0:
            analysis.passes_momentum = False
            analysis.reason = "Invalid LTP"
            return analysis
        
        # Calculate technical indicators
        analysis.dma_50 = self.calculate_dma(symbol, 50)
        analysis.dma_200 = self.calculate_dma(symbol, 200)
        analysis.atr = self.calculate_atr(symbol, self.config.risk.atr_period)
        
        # Check momentum conditions
        if analysis.dma_50:
            analysis.above_50dma = ltp > analysis.dma_50
        if analysis.dma_200:
            analysis.above_200dma = ltp > analysis.dma_200
        
        # Momentum filter
        passes = True
        reasons = []
        
        if self.config.risk.require_above_50dma and not analysis.above_50dma:
            passes = False
            reasons.append("Below 50 DMA")
        
        if self.config.risk.require_above_200dma and not analysis.above_200dma:
            passes = False
            reasons.append("Below 200 DMA")
        
        analysis.passes_momentum = passes
        analysis.reason = "; ".join(reasons) if reasons else "OK"
        
        # Cache the analysis
        self._analysis_cache[cache_key] = analysis
        
        # Calculate ATR-based stop loss
        if self.config.risk.use_atr_stop_loss and analysis.atr and analysis.atr > 0:
            sl_distance = analysis.atr * self.config.risk.atr_sl_multiple
            sl_pct = sl_distance / ltp
            
            # Clamp to min/max
            sl_pct = max(self.config.risk.min_stop_loss, min(sl_pct, self.config.risk.max_stop_loss))
            analysis.suggested_sl_pct = sl_pct
        else:
            analysis.suggested_sl_pct = self.config.stop_loss_percent
        
        return analysis
    
    # ==================== PORTFOLIO RISK ====================
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary with risk metrics"""
        holdings = self.get_holdings()
        
        total_value = sum(
            h['quantity'] * h.get('last_price', h['average_price']) 
            for h in holdings
        )
        total_invested = sum(
            h['quantity'] * h['average_price'] 
            for h in holdings
        )
        total_pnl = sum(h.get('pnl', 0) for h in holdings)
        
        # Track portfolio peak for drawdown
        if total_value > self._portfolio_peak:
            self._portfolio_peak = total_value
        
        drawdown = 0
        if self._portfolio_peak > 0:
            drawdown = (self._portfolio_peak - total_value) / self._portfolio_peak
        
        # Sector exposure
        sector_values = {}
        for h in holdings:
            sector = self.get_sector(h['tradingsymbol'])
            value = h['quantity'] * h.get('last_price', h['average_price'])
            sector_values[sector] = sector_values.get(sector, 0) + value
        
        sector_exposure = {}
        if total_value > 0:
            for sector, value in sector_values.items():
                sector_exposure[sector] = value / total_value
        
        # Stocks per sector
        sector_counts = {}
        for h in holdings:
            sector = self.get_sector(h['tradingsymbol'])
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        
        return {
            'total_stocks': len(holdings),
            'total_value': total_value,
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'pnl_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
            'portfolio_peak': self._portfolio_peak,
            'current_drawdown': drawdown,
            'sector_exposure': sector_exposure,
            'sector_counts': sector_counts,
            'max_sector': max(sector_exposure.values()) if sector_exposure else 0,
        }
    
    def check_risk_limits(self, symbol: str, buy_value: float, holdings: List[Dict] = None, summary: Dict = None) -> Tuple[bool, str]:
        """Check if buying a stock would violate risk limits
        
        Args:
            symbol: Stock symbol to check
            buy_value: Value of proposed purchase
            holdings: Pre-fetched holdings (avoids duplicate API call)
            summary: Pre-fetched portfolio summary (avoids duplicate API call)
        """
        # Use provided data or fetch
        if holdings is None:
            holdings = self.get_holdings()
        if summary is None:
            summary = self.get_portfolio_summary()
        
        sector = self.get_sector(symbol)
        
        # Check drawdown limit
        if summary['current_drawdown'] >= self.config.risk.max_drawdown_limit:
            return False, f"Portfolio drawdown ({summary['current_drawdown']:.1%}) exceeds limit ({self.config.risk.max_drawdown_limit:.1%})"
        
        # Check sector exposure
        current_sector_value = sum(
            h['quantity'] * h.get('last_price', h['average_price'])
            for h in holdings
            if self.get_sector(h['tradingsymbol']) == sector
        )
        new_sector_value = current_sector_value + buy_value
        new_total = summary['total_value'] + buy_value
        
        if new_total > 0:
            new_sector_exposure = new_sector_value / new_total
            if new_sector_exposure > self.config.risk.max_sector_exposure:
                return False, f"Sector '{sector}' exposure ({new_sector_exposure:.1%}) would exceed limit ({self.config.risk.max_sector_exposure:.1%})"
        
        # Check stocks per sector
        sector_count = summary['sector_counts'].get(sector, 0)
        # Check if already holding this stock
        already_holds = any(h['tradingsymbol'] == symbol for h in holdings)
        
        if not already_holds and sector_count >= self.config.risk.max_stocks_per_sector:
            return False, f"Already holding {sector_count} stocks in '{sector}' (limit: {self.config.risk.max_stocks_per_sector})"
        
        # Check buy frequency
        last_buy = self._last_buy_dates.get(symbol)
        if last_buy:
            days_since = (datetime.now() - last_buy).days
            if days_since < self.config.min_days_between_buys:
                return False, f"Bought {symbol} {days_since} days ago (min: {self.config.min_days_between_buys} days)"
        
        return True, "OK"
    
    # ==================== ORDER BOOK ====================
    
    @staticmethod
    def _row_get_ci(row: Dict, key: str, default: Any = "") -> Any:
        """Case-insensitive dict access"""
        if key in row:
            return row.get(key, default)
        lower_map = {str(k).strip().lower(): v for k, v in row.items()}
        return lower_map.get(str(key).strip().lower(), default)
    
    def read_order_book(self, filepath: str = None, prefer_tips: bool = True) -> List[Dict]:
        """Read orders from CSV file
        
        Args:
            filepath: Path to CSV file (uses tips_research_data.csv by default if exists)
            prefer_tips: If True, prefer data/tips_research_data.csv over order_book_file
        """
        # Prefer tips_research_data.csv if it exists
        if filepath is None and prefer_tips:
            tips_path = Path(__file__).resolve().parents[1] / "data" / "tips_research_data.csv"
            if tips_path.exists():
                filepath = str(tips_path)
                self.log(f"Using tips universe: {tips_path.name}", "info")
        
        filepath = filepath or self.config.order_book_file
        orders = []
        
        try:
            with open(filepath, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = str(self._row_get_ci(row, 'symbol', '')).strip().upper()
                    if not symbol:
                        continue
                    
                    orders.append({
                        'symbol': symbol,
                        'quantity': int(self.safe_float(self._row_get_ci(row, 'quantity', 1))),
                        'price': self.safe_float(self._row_get_ci(row, 'price', 0)),
                        'product': str(self._row_get_ci(row, 'product', 'CNC')).upper(),
                        'order_type': str(self._row_get_ci(row, 'order_type', 'MARKET')).upper(),
                        'exchange': str(self._row_get_ci(row, 'exchange', 'NSE')).upper(),
                        'allocation': self.safe_float(self._row_get_ci(row, 'allocation', 0)),
                        'rank': str(self._row_get_ci(row, 'rank', '')),
                        'sector': self.get_sector(symbol),
                    })
        except FileNotFoundError:
            self.log(f"Order book not found: {filepath}", "error")
        except Exception as e:
            self.log(f"Error reading order book: {e}", "error")
        
        return orders
    
    @staticmethod
    def is_top15_rank(rank: str) -> bool:
        """Return True if rank is within Top15 (legacy method)"""
        return KiteTraderV2.is_within_top_n_rank(rank, 15)
    
    @staticmethod
    def is_within_top_n_rank(rank: str, top_n: int = 15) -> bool:
        """Return True if rank is within TopN
        
        Args:
            rank: Rank string (e.g., 'Top5', 'Next5', 'Top15', 'HOLDING')
            top_n: Maximum rank to include (default 15)
        """
        if not rank:
            return False
        s = str(rank).strip()
        if not s:
            return False
        # Include HOLDING stocks always
        if s.upper() == 'HOLDING':
            return True
        if s.isdigit():
            return int(s) <= top_n
        m = re.match(r"^top\s*(\d+)$", s, flags=re.I)
        if m:
            return int(m.group(1)) <= top_n
        m = re.match(r"^next\s*(\d+)$", s, flags=re.I)
        if m:
            return (5 + int(m.group(1))) <= top_n
        return s.upper().startswith(("A", "B")) and len(s) <= 3
    
    # ==================== BUY OPERATIONS ====================
    
    def place_buy_order(self, symbol: str, quantity: int, price: float = None,
                        exchange: str = "NSE", product: str = "CNC",
                        order_type: str = "MARKET", skip_risk_check: bool = False) -> OrderResult:
        """Place a buy order with risk checks"""
        if not self.validate_connection():
            return OrderResult(success=False, dry_run=False, error="Not connected")
        
        # Fetch LTP for risk calculations
        ltp_map = self.get_ltp([symbol])
        ltp = ltp_map.get(symbol, price or 0)
        buy_value = quantity * ltp
        
        # Risk checks (unless skipped)
        if not skip_risk_check:
            # Check portfolio risk limits
            can_buy, reason = self.check_risk_limits(symbol, buy_value)
            if not can_buy:
                self.log(f"BLOCKED {symbol}: {reason}", "warning")
                return OrderResult(success=False, dry_run=False, reason=reason)
            
            # Check momentum filter
            analysis = self.analyze_stock(symbol, ltp)
            if not analysis.passes_momentum:
                self.log(f"BLOCKED {symbol}: {analysis.reason}", "warning")
                return OrderResult(success=False, dry_run=False, reason=analysis.reason)
        
        try:
            kite_product = getattr(self.kite, f'PRODUCT_{product}', self.kite.PRODUCT_CNC)
            kite_order_type = getattr(self.kite, f'ORDER_TYPE_{order_type}', self.kite.ORDER_TYPE_MARKET)
            
            order_params = {
                'tradingsymbol': symbol,
                'exchange': exchange,
                'transaction_type': self.kite.TRANSACTION_TYPE_BUY,
                'quantity': quantity,
                'order_type': kite_order_type,
                'product': kite_product,
                'variety': self.kite.VARIETY_REGULAR,
            }
            
            if order_type == "LIMIT" and price:
                order_params['price'] = self.round_to_tick(price, symbol=symbol, exchange=exchange)
            
            if self.config.dry_run:
                self.log(f"[DRY RUN] Would buy: {symbol} x {quantity} @ {price or 'MARKET'}", "info")
                self._audit_log("buy_dry_run", {"symbol": symbol, "qty": quantity, "price": price or "MARKET"})
                return OrderResult(success=True, dry_run=True)
            else:
                order_id = self.kite.place_order(**order_params)
                self._last_buy_dates[symbol] = datetime.now()
                self._save_last_buy_dates()  # Persist to disk
                self.log(f"Bought: {symbol} x {quantity} - Order ID: {order_id}", "success")
                self._audit_log("buy_executed", {"symbol": symbol, "qty": quantity, "order_id": order_id})
                return OrderResult(success=True, dry_run=False, order_id=order_id)
        except Exception as e:
            self.log(f"Error buying {symbol}: {e}", "error")
            self._audit_log("buy_error", {"symbol": symbol, "error": str(e)})
            return OrderResult(success=False, dry_run=False, error=str(e))
    
    def smart_buy(self, symbol: str, budget: float = None) -> OrderResult:
        """Smart buy with all risk checks and optimal sizing"""
        if not self.validate_connection():
            return OrderResult(success=False, dry_run=False, error="Not connected")
        
        budget = budget or self.config.per_stock_daily_budget
        
        # Analyze first
        analysis = self.analyze_stock(symbol)
        
        if not analysis.passes_momentum:
            self.log(f"SKIPPED {symbol}: {analysis.reason}", "warning")
            return OrderResult(success=False, dry_run=False, reason=analysis.reason)
        
        if analysis.ltp <= 0:
            return OrderResult(success=False, dry_run=False, error="Invalid LTP")
        
        # Calculate quantity from budget
        qty = max(1, int(budget / analysis.ltp))
        qty = min(qty, self.config.max_qty_per_stock)
        
        self.log(f"SMART BUY {symbol}: LTP=₹{analysis.ltp:.2f}, "
                 f"50DMA={'✓' if analysis.above_50dma else '✗'}, "
                 f"ATR-SL={analysis.suggested_sl_pct:.1%}, "
                 f"Sector={analysis.sector}", "info")
        
        return self.place_buy_order(symbol, qty, order_type="MARKET")
    
    # ==================== SELL OPERATIONS ====================
    
    def sell_stock(self, symbol: str, quantity: int, exchange: str = "NSE",
                   product: str = "CNC") -> Optional[str]:
        """Place sell order"""
        if not self.validate_connection():
            return None
        
        try:
            order_params = {
                'tradingsymbol': symbol,
                'exchange': exchange,
                'transaction_type': self.kite.TRANSACTION_TYPE_SELL,
                'quantity': quantity,
                'order_type': self.kite.ORDER_TYPE_MARKET,
                'product': getattr(self.kite, f'PRODUCT_{product}', self.kite.PRODUCT_CNC),
                'variety': self.kite.VARIETY_REGULAR,
            }
            
            if self.config.dry_run:
                self.log(f"[DRY RUN] Would sell: {symbol} x {quantity}", "info")
                return "DRY_RUN"
            else:
                order_id = self.kite.place_order(**order_params)
                self.log(f"Sold: {symbol} x {quantity} - Order ID: {order_id}", "success")
                return order_id
        except Exception as e:
            self.log(f"Error selling {symbol}: {e}", "error")
            return None
    
    def get_negative_holdings(self) -> List[Dict]:
        """Get holdings with negative P&L"""
        holdings = self.get_holdings()
        return [
            {
                'tradingsymbol': h['tradingsymbol'],
                'exchange': h['exchange'],
                'quantity': h['quantity'],
                'pnl': h.get('pnl', 0),
                'average_price': h.get('average_price', 0),
                'last_price': h.get('last_price', 0),
            }
            for h in holdings
            if h.get('pnl', 0) < 0 and h.get('quantity', 0) > 0
        ]
    
    def sell_negative_holdings(self) -> int:
        """Sell all stocks with negative P&L"""
        negative = self.get_negative_holdings()
        if not negative:
            self.log("No stocks with negative P&L", "info")
            return 0
        
        sold = 0
        for stock in negative:
            if self.sell_stock(stock['tradingsymbol'], stock['quantity'], stock['exchange']):
                sold += 1
        
        return sold
    
    def sell_stock_limit(self, symbol: str, quantity: int, price: float,
                         exchange: str = "NSE", product: str = "CNC") -> Optional[str]:
        """Place LIMIT sell order at specified price"""
        if not self.validate_connection():
            return None
        
        try:
            # Round price to tick size
            rounded_price = self.round_to_tick(price, symbol=symbol, exchange=exchange)
            
            order_params = {
                'tradingsymbol': symbol,
                'exchange': exchange,
                'transaction_type': self.kite.TRANSACTION_TYPE_SELL,
                'quantity': quantity,
                'order_type': self.kite.ORDER_TYPE_LIMIT,
                'price': rounded_price,
                'product': getattr(self.kite, f'PRODUCT_{product}', self.kite.PRODUCT_CNC),
                'variety': self.kite.VARIETY_REGULAR,
            }
            
            if self.config.dry_run:
                self.log(f"[DRY RUN] Would sell LIMIT: {symbol} x {quantity} @ ₹{rounded_price:.2f}", "info")
                return "DRY_RUN"
            else:
                order_id = self.kite.place_order(**order_params)
                self.log(f"Sell LIMIT: {symbol} x {quantity} @ ₹{rounded_price:.2f} - Order ID: {order_id}", "success")
                return order_id
        except Exception as e:
            self.log(f"Error selling {symbol} limit: {e}", "error")
            return None
    
    def sell_all_holdings_above_ltp(self, premium_pct: float = 0.0005) -> Dict:
        """Sell all holdings at a price above current LTP
        
        Args:
            premium_pct: Premium % above LTP (0.0005 = 0.05%)
            
        Returns:
            Dict with results: {'success': count, 'failed': count, 'details': [...]}
        """
        holdings = self.get_holdings()
        
        results = {
            'success': 0,
            'failed': 0,
            'details': [],
            'total_value': 0
        }
        
        if not holdings:
            self.log("No holdings to sell", "info")
            return results
        
        for h in holdings:
            symbol = h['tradingsymbol']
            qty = h.get('quantity', 0)
            ltp = h.get('last_price', 0)
            exchange = h.get('exchange', 'NSE')
            
            if qty <= 0 or ltp <= 0:
                continue
            
            # Calculate sell price: LTP + premium
            sell_price = ltp * (1 + premium_pct)
            sell_price_rounded = self.round_to_tick(sell_price, symbol=symbol, exchange=exchange)
            est_value = qty * sell_price_rounded
            
            order_id = self.sell_stock_limit(symbol, qty, sell_price_rounded, exchange)
            
            detail = {
                'symbol': symbol,
                'qty': qty,
                'ltp': ltp,
                'sell_price': sell_price_rounded,
                'est_value': est_value,
                'premium_pct': premium_pct * 100,
                'status': 'Success' if order_id else 'Failed',
                'order_id': order_id
            }
            
            if order_id:
                results['success'] += 1
                results['total_value'] += est_value
            else:
                results['failed'] += 1
            
            results['details'].append(detail)
        
        self.log(f"Sell all: {results['success']} success, {results['failed']} failed, Total: ₹{results['total_value']:,.0f}", 
                 "success" if results['failed'] == 0 else "warning")
        
        return results
    
    # ==================== GTT OPERATIONS ====================
    
    def get_existing_gtt_symbols(self, transaction_type: str = 'SELL') -> Set[str]:
        """Get symbols with existing active GTT orders"""
        gtts = self.get_gtts()
        symbols = set()
        for gtt in gtts:
            if gtt.get('status') == 'active':
                orders = gtt.get('orders', [])
                if orders and orders[0].get('transaction_type') == transaction_type:
                    symbols.add(gtt.get('tradingsymbol'))
        return symbols
    
    def delete_gtt(self, gtt_id: int) -> bool:
        """Delete a GTT order"""
        if not self.validate_connection():
            return False
        try:
            if self.config.dry_run:
                self.log(f"[DRY RUN] Would delete GTT {gtt_id}", "info")
                return True
            self.with_backoff(self.kite.delete_gtt, gtt_id)
            return True
        except Exception as e:
            self.log(f"Error deleting GTT {gtt_id}: {e}", "error")
            return False
    
    def place_gtt_oco_atr(self, symbol: str, quantity: int, buy_price: float,
                          product: str = 'CNC') -> Optional[int]:
        """Place GTT OCO with ATR-based stop loss"""
        if not self.validate_connection():
            return None
        
        # Get ATR-based SL
        analysis = self.analyze_stock(symbol, buy_price)
        sl_pct = analysis.suggested_sl_pct
        target_pct = self.config.target_percent
        
        sl_trigger = self.round_to_tick(buy_price * (1 - sl_pct), symbol=symbol, exchange='NSE')
        target_trigger = self.round_to_tick(buy_price * (1 + target_pct), symbol=symbol, exchange='NSE')
        sl_price = self.round_to_tick(sl_trigger * 0.95, symbol=symbol, exchange='NSE')
        
        try:
            if self.config.dry_run:
                self.log(f"[DRY RUN] GTT OCO {symbol}: SL={sl_trigger} ({sl_pct:.1%}), Target={target_trigger}", "info")
                return 0
            
            kite_product = getattr(self.kite, f'PRODUCT_{product}', self.kite.PRODUCT_CNC)
            
            gtt_id = self.kite.place_gtt(
                trigger_type=self.kite.GTT_TYPE_OCO,
                tradingsymbol=symbol,
                exchange='NSE',
                trigger_values=[sl_trigger, target_trigger],
                last_price=buy_price,
                orders=[
                    {
                        'transaction_type': self.kite.TRANSACTION_TYPE_SELL,
                        'quantity': quantity,
                        'order_type': self.kite.ORDER_TYPE_LIMIT,
                        'product': kite_product,
                        'price': sl_price,
                    },
                    {
                        'transaction_type': self.kite.TRANSACTION_TYPE_SELL,
                        'quantity': quantity,
                        'order_type': self.kite.ORDER_TYPE_LIMIT,
                        'product': kite_product,
                        'price': target_trigger,
                    }
                ]
            )
            self.log(f"GTT OCO placed for {symbol}: ATR-SL={sl_pct:.1%}", "success")
            return gtt_id
        except Exception as e:
            self.log(f"Error placing GTT OCO for {symbol}: {e}", "error")
            return None
    
    def place_gtt_buy_dip(self, symbol: str, budget: float = None, skip_risk_check: bool = False,
                          skip_momentum_check: bool = False, max_dip_pct: float = 0.10) -> Optional[int]:
        """Place GTT buy order for dip accumulation with risk controls
        
        Args:
            symbol: Stock symbol
            budget: Budget for the GTT order
            skip_risk_check: If True, skip sector/drawdown checks (not recommended)
            skip_momentum_check: If True, skip DMA momentum filter
            max_dip_pct: Maximum dip % allowed (default 10%, guards against fat-finger)
        """
        if not self.validate_connection():
            return None
        
        budget = budget or self.config.gtt_buy_budget_per_stock
        
        ltp_map = self.get_ltp([symbol])
        ltp = ltp_map.get(symbol, 0)
        if ltp <= 0:
            return None
        
        # Check momentum filter to avoid averaging down losers
        if not skip_momentum_check:
            analysis = self.analyze_stock(symbol, ltp)
            if not analysis.passes_momentum:
                self.log(f"GTT BUY blocked for {symbol}: {analysis.reason} (use skip_momentum_check=True to override)", "warning")
                self._audit_log("gtt_buy_blocked", {"symbol": symbol, "reason": analysis.reason, "type": "momentum"})
                return None
        
        # Guard against excessive dip (fat-finger protection)
        dip_pct = self.config.gtt_buy_lower_percent
        if dip_pct > max_dip_pct:
            self.log(f"GTT BUY blocked for {symbol}: dip {dip_pct:.1%} exceeds max {max_dip_pct:.1%}", "warning")
            self._audit_log("gtt_buy_blocked", {"symbol": symbol, "reason": f"dip {dip_pct:.1%} > max {max_dip_pct:.1%}", "type": "fat_finger"})
            return None
        
        trigger_price = self.round_to_tick(ltp * (1 - dip_pct), symbol=symbol)
        limit_price = self.round_to_tick(trigger_price * 1.001, symbol=symbol)
        qty = max(1, int(budget / trigger_price))
        
        # Apply max_qty_per_stock cap
        qty = min(qty, self.config.max_qty_per_stock)
        
        # Check risk limits before placing GTT
        if not skip_risk_check:
            buy_value = qty * trigger_price
            can_buy, reason = self.check_risk_limits(symbol, buy_value)
            if not can_buy:
                self.log(f"GTT BUY blocked for {symbol}: {reason}", "warning")
                self._audit_log("gtt_buy_blocked", {"symbol": symbol, "reason": reason, "type": "risk_limit"})
                return None
        
        try:
            if self.config.dry_run:
                self.log(f"[DRY RUN] GTT BUY {symbol} x {qty} @ {trigger_price}", "info")
                self._audit_log("gtt_buy_dry_run", {"symbol": symbol, "qty": qty, "trigger": trigger_price})
                return 0
            
            gtt_id = self.kite.place_gtt(
                trigger_type=self.kite.GTT_TYPE_SINGLE,
                tradingsymbol=symbol,
                exchange='NSE',
                trigger_values=[trigger_price],
                last_price=ltp,
                orders=[{
                    'transaction_type': self.kite.TRANSACTION_TYPE_BUY,
                    'quantity': qty,
                    'order_type': self.kite.ORDER_TYPE_LIMIT,
                    'product': self.kite.PRODUCT_CNC,
                    'price': limit_price,
                }]
            )
            self.log(f"GTT BUY placed for {symbol} x {qty} @ {trigger_price}", "success")
            self._audit_log("gtt_buy_placed", {"symbol": symbol, "qty": qty, "trigger": trigger_price, "gtt_id": gtt_id})
            return gtt_id
        except Exception as e:
            self.log(f"Error placing GTT BUY for {symbol}: {e}", "error")
            self._audit_log("gtt_buy_error", {"symbol": symbol, "error": str(e)})
            return None
    
    # ==================== TRAILING STOP ====================
    
    def check_trailing_stops(self) -> List[Dict]:
        """Check holdings for trailing stop triggers"""
        if not self.config.risk.enable_trailing_stop:
            return []
        
        holdings = self.get_holdings()
        triggers = []
        
        for h in holdings:
            symbol = h['tradingsymbol']
            avg_price = h['average_price']
            ltp = h.get('last_price', 0)
            qty = h['quantity']
            
            if avg_price <= 0 or ltp <= 0:
                continue
            
            gain_pct = (ltp - avg_price) / avg_price
            
            # Check if trailing stop should be activated
            if gain_pct >= self.config.risk.trailing_activation_pct:
                # Track peak price
                if symbol not in self._trailing_peaks:
                    self._trailing_peaks[symbol] = ltp
                    self._save_trailing_peaks()  # Persist
                    self.log(f"TRAILING activated for {symbol} at +{gain_pct:.1%}", "info")
                elif ltp > self._trailing_peaks[symbol]:
                    self._trailing_peaks[symbol] = ltp
                    self._save_trailing_peaks()  # Persist new peak
                
                # Check if trailing stop hit
                peak = self._trailing_peaks[symbol]
                trail_trigger = peak * (1 - self.config.risk.trailing_stop_pct)
                
                if ltp <= trail_trigger:
                    triggers.append({
                        'symbol': symbol,
                        'quantity': qty,
                        'reason': f"Trailing stop hit (peak: ₹{peak:.2f}, trigger: ₹{trail_trigger:.2f})",
                        'gain_pct': gain_pct,
                    })
        
        return triggers
    
    def execute_trailing_stops(self) -> int:
        """Execute trailing stop sells"""
        triggers = self.check_trailing_stops()
        
        if not triggers:
            self.log("No trailing stops triggered", "info")
            return 0
        
        sold = 0
        for t in triggers:
            self.log(f"TRAILING STOP: {t['symbol']} - {t['reason']}", "warning")
            if self.sell_stock(t['symbol'], t['quantity']):
                # Clear tracking and persist
                self._trailing_peaks.pop(t['symbol'], None)
                self._save_trailing_peaks()
                sold += 1
        
        return sold
    
    # ==================== PARTIAL PROFIT BOOKING ====================
    
    def check_partial_exits(self) -> List[Dict]:
        """Check holdings for partial profit booking"""
        if not self.config.risk.enable_partial_exit:
            return []
        
        holdings = self.get_holdings()
        exits = []
        
        for h in holdings:
            symbol = h['tradingsymbol']
            avg_price = h['average_price']
            ltp = h.get('last_price', 0)
            qty = h['quantity']
            
            if avg_price <= 0 or ltp <= 0 or qty <= 1:
                continue
            
            gain_pct = (ltp - avg_price) / avg_price
            
            if gain_pct >= self.config.risk.partial_exit_trigger_pct:
                exit_qty = max(1, int(qty * self.config.risk.partial_exit_qty_pct))
                exits.append({
                    'symbol': symbol,
                    'quantity': exit_qty,
                    'remaining': qty - exit_qty,
                    'gain_pct': gain_pct,
                })
        
        return exits
    
    def execute_partial_exits(self) -> int:
        """Execute partial profit booking"""
        exits = self.check_partial_exits()
        
        if not exits:
            self.log("No partial exits needed", "info")
            return 0
        
        sold = 0
        for e in exits:
            self.log(f"PARTIAL EXIT: {e['symbol']} x {e['quantity']} at +{e['gain_pct']:.1%}", "info")
            if self.sell_stock(e['symbol'], e['quantity']):
                sold += 1
        
        return sold
    
    # ==================== PROTECTION ====================
    
    def protect_holdings_smart(self, refresh: bool = False) -> int:
        """Protect all holdings with ATR-based GTT OCO"""
        if not self.validate_connection():
            return 0
        
        existing = self.get_existing_gtt_symbols('SELL')
        
        if existing and refresh:
            gtts = self.get_gtts()
            for gtt in gtts:
                if gtt.get('status') == 'active':
                    orders = gtt.get('orders', [])
                    if orders and orders[0].get('transaction_type') == 'SELL':
                        self.delete_gtt(gtt.get('id'))
            existing = set()
        
        holdings = self.get_holdings()
        if not holdings:
            self.log("No holdings to protect", "info")
            return 0
        
        protected = 0
        for h in holdings:
            symbol = h['tradingsymbol']
            
            if symbol in existing:
                continue
            
            qty = h['quantity']
            avg_price = h['average_price']
            
            if qty <= 0 or avg_price <= 0:
                continue
            
            if self.place_gtt_oco_atr(symbol, qty, avg_price):
                protected += 1
        
        self.log(f"Protected {protected}/{len(holdings)} holdings with ATR-based SL", "success")
        return protected
    
    # ==================== SIMPLE INVESTMENT MODE ====================
    
    def run_simple_investment(self, top_n: int = 15) -> Dict:
        """
        Simple long-term investment mode.
        
        Args:
            top_n: Maximum rank to include (e.g., 5=Top5, 10=Top10, 15=Top15, 25=Top25, 0=All)
        
        Rules:
        1. Only buy stocks passing momentum filter (above DMA)
        2. Respect sector limits and drawdown limits
        3. Wait min_days_between_buys before re-buying same stock
        4. Place ATR-based protection immediately
        5. Honor daily_budget cap across all buys
        """
        if not self.validate_connection():
            return {'success': False, 'error': 'Not connected'}
        
        if not self.config.dry_run and not self.is_market_hours():
            return {'success': False, 'error': 'Market closed'}
        
        results = {
            'analyzed': 0,
            'passed_momentum': 0,
            'blocked_risk': 0,
            'blocked_budget': 0,
            'bought': 0,
            'protected': 0,
            'total_spent': 0.0,
            'top_n_filter': top_n,
            'details': [],
        }
        
        # Read order book
        orders = self.read_order_book()
        
        # Get current holdings to include holding stocks
        current_holdings = {h['tradingsymbol'].upper(): h for h in self.get_holdings(use_cache=False) if h.get('quantity', 0) > 0}
        
        # Filter: TopN OR has existing holding (top_n=0 means include all)
        def should_analyze(order):
            symbol = order.get('symbol', '').upper()
            rank = order.get('rank', '')
            # Include if within TopN rank OR has existing holding
            if top_n == 0:  # 0 means all stocks
                return True
            return self.is_within_top_n_rank(rank, top_n) or symbol in current_holdings
        
        orders = [o for o in orders if should_analyze(o)]
        
        if not orders:
            self.log(f"No stocks to process (no Top{top_n} or holdings)", "warning")
            return results
        
        filter_desc = f"Top{top_n}" if top_n > 0 else "All"
        self.log(f"Analyzing {len(orders)} stocks for investment ({filter_desc} + Holdings)...", "info")
        
        # Track remaining daily budget
        remaining_budget = self.config.daily_budget
        
        # Fetch fresh holdings and summary (will be refreshed after each buy)
        holdings = self.get_holdings(use_cache=False)
        summary = self.get_portfolio_summary()
        
        if summary['current_drawdown'] >= self.config.risk.max_drawdown_limit:
            self.log(f"PAUSED: Portfolio drawdown at {summary['current_drawdown']:.1%}", "error")
            return {'success': False, 'error': 'Drawdown limit reached'}
        
        for order in orders:
            symbol = order['symbol']
            results['analyzed'] += 1
            
            # Check if daily budget exhausted
            if remaining_budget < self.config.per_stock_daily_budget * 0.5:
                self.log(f"Daily budget exhausted (remaining: ₹{remaining_budget:,.0f})", "info")
                break
            
            # Analyze stock
            analysis = self.analyze_stock(symbol)
            
            detail = {
                'symbol': symbol,
                'sector': analysis.sector,
                'ltp': analysis.ltp,
                'above_50dma': analysis.above_50dma,
                'above_200dma': analysis.above_200dma,
                'atr_sl': f"{analysis.suggested_sl_pct:.1%}",
                'status': 'pending',
            }
            
            # Check momentum
            if not analysis.passes_momentum:
                detail['status'] = f'SKIP: {analysis.reason}'
                results['details'].append(detail)
                continue
            
            results['passed_momentum'] += 1
            
            # Calculate buy value (capped by remaining budget)
            stock_budget = min(self.config.per_stock_daily_budget, remaining_budget)
            buy_value = stock_budget
            
            # Check risk limits with fresh holdings/summary
            can_buy, reason = self.check_risk_limits(symbol, buy_value, holdings=holdings, summary=summary)
            
            if not can_buy:
                detail['status'] = f'BLOCKED: {reason}'
                results['blocked_risk'] += 1
                results['details'].append(detail)
                self._audit_log("investment_blocked", {"symbol": symbol, "reason": reason, "type": "risk_limit"})
                continue
            
            # Execute buy
            qty = max(1, int(stock_budget / analysis.ltp))
            qty = min(qty, self.config.max_qty_per_stock)
            actual_buy_value = qty * analysis.ltp
            
            result = self.place_buy_order(symbol, qty, skip_risk_check=True)
            
            if result.success:
                detail['status'] = 'BOUGHT'
                detail['quantity'] = qty
                detail['value'] = f"₹{actual_buy_value:,.0f}"
                results['bought'] += 1
                results['total_spent'] += actual_buy_value
                remaining_budget -= actual_buy_value
                
                # Refresh holdings/summary for accurate risk checks on next iteration
                self._holdings_cache = None  # Force refresh
                holdings = self.get_holdings(use_cache=False)
                summary = self.get_portfolio_summary()
                
                # Place protection
                if self.place_gtt_oco_atr(symbol, qty, analysis.ltp):
                    results['protected'] += 1
            else:
                detail['status'] = f'FAILED: {result.error or result.reason}'
            
            results['details'].append(detail)
        
        self.log(f"Investment complete: {results['bought']} bought (₹{results['total_spent']:,.0f}), "
                 f"{results['blocked_risk']} blocked by risk, "
                 f"{results['protected']} protected", "success")
        
        # Audit summary
        self._audit_log("investment_run_complete", {
            "analyzed": results['analyzed'],
            "passed_momentum": results['passed_momentum'],
            "blocked_risk": results['blocked_risk'],
            "bought": results['bought'],
            "total_spent": results['total_spent'],
            "protected": results['protected'],
            "remaining_budget": remaining_budget,
        })
        
        # Include remaining budget in results for UI
        results['remaining_budget'] = remaining_budget
        results['daily_budget'] = self.config.daily_budget
        
        return results
    
    # ==================== RISK REPORT ====================
    
    def generate_risk_report(self) -> str:
        """Generate a comprehensive risk report"""
        if not self.validate_connection():
            return "Not connected"
        
        summary = self.get_portfolio_summary()
        holdings = self.get_holdings()
        
        lines = [
            "=" * 60,
            "PORTFOLIO RISK REPORT",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "📊 PORTFOLIO OVERVIEW",
            "-" * 40,
            f"Total Stocks: {summary['total_stocks']}",
            f"Portfolio Value: ₹{summary['total_value']:,.2f}",
            f"Total P&L: ₹{summary['total_pnl']:,.2f} ({summary['pnl_percent']:.2f}%)",
            "",
            "⚠️ RISK METRICS",
            "-" * 40,
            f"Current Drawdown: {summary['current_drawdown']:.2%}",
            f"Max Drawdown Limit: {self.config.risk.max_drawdown_limit:.2%}",
            f"Status: {'⚠️ NEAR LIMIT' if summary['current_drawdown'] > 0.07 else '✅ OK'}",
            "",
            "🏢 SECTOR EXPOSURE",
            "-" * 40,
        ]
        
        for sector, exposure in sorted(summary['sector_exposure'].items(), key=lambda x: -x[1]):
            count = summary['sector_counts'].get(sector, 0)
            status = "⚠️" if exposure > self.config.risk.max_sector_exposure else "✅"
            lines.append(f"{status} {sector}: {exposure:.1%} ({count} stocks)")
        
        lines.extend([
            "",
            "📉 HIGH-RISK HOLDINGS (Below 50 DMA)",
            "-" * 40,
        ])
        
        risk_stocks = []
        for h in holdings:
            analysis = self.analyze_stock(h['tradingsymbol'], h.get('last_price', 0))
            if not analysis.above_50dma:
                risk_stocks.append({
                    'symbol': h['tradingsymbol'],
                    'pnl': h.get('pnl', 0),
                    'reason': analysis.reason,
                })
        
        if risk_stocks:
            for s in risk_stocks:
                lines.append(f"⚠️ {s['symbol']}: P&L ₹{s['pnl']:,.2f} - {s['reason']}")
        else:
            lines.append("✅ All holdings above 50 DMA")
        
        lines.extend([
            "",
            "🎯 TRAILING STOP CANDIDATES (>8% gain)",
            "-" * 40,
        ])
        
        winners = []
        for h in holdings:
            avg = h['average_price']
            ltp = h.get('last_price', 0)
            if avg > 0 and ltp > 0:
                gain = (ltp - avg) / avg
                if gain >= self.config.risk.trailing_activation_pct:
                    winners.append({
                        'symbol': h['tradingsymbol'],
                        'gain': gain,
                        'tracked': h['tradingsymbol'] in self._trailing_peaks,
                    })
        
        if winners:
            for w in sorted(winners, key=lambda x: -x['gain']):
                status = "🔒 Trailing" if w['tracked'] else "💰 New"
                lines.append(f"{status} {w['symbol']}: +{w['gain']:.1%}")
        else:
            lines.append("No stocks with >8% gain")
        
        lines.extend([
            "",
            "=" * 60,
        ])
        
        return "\n".join(lines)
