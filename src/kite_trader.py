"""
KiteTrader - Class-based wrapper for Zerodha Kite trading operations.
Encapsulates all trading functionality from buy_stocks.py into a reusable class.
"""

import os
import csv
import time
import math
import random
import shutil
import logging
import re
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable, Set, Tuple
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TraderConfig:
    """Configuration for KiteTrader"""
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
    per_stock_daily_budget: float = 100000.0
    max_qty_per_stock: int = 500
    max_budget: float = 0.0
    base_budget_actual: float = 0.0
    
    # Tranche Strategy Settings
    tranche_size: float = 0.20
    tranche_count: int = 5
    ltp_discount: float = 0.998
    tranche_interval: int = 3600
    base_order_qty: int = 5  # Phase 1 base order quantity per stock
    
    # Stop Loss Settings
    stop_loss_enabled: bool = False
    stop_loss_percent: float = 0.08
    target_percent: float = 0.16
    use_gtt: bool = True
    use_oco: bool = True
    sl_execution_buffer: float = 0.05
    
    # GTT Buy Settings
    gtt_buy_lower_percent: float = 0.02
    gtt_buy_upper_percent: float = 0.04
    gtt_buy_qty_lower: float = 0.60
    gtt_buy_qty_upper: float = 0.40
    gtt_buy_budget_per_stock: float = 10000.0  # Min ₹10k per GTT buy (makes ₹15.34 brokerage worthwhile)
    
    # Sliced GTT OCO Settings
    gtt_slices: List[Tuple[float, float, float]] = field(default_factory=lambda: [
        (0.30, 0.05, 0.10),
        (0.40, 0.08, 0.15),
        (0.30, 0.10, 0.20),
    ])
    
    # Risk Controls
    max_ltp_drift: float = 0.03
    default_tick: Decimal = Decimal("0.05")
    
    # Market Hours (IST)
    market_open_hour: int = 9
    market_open_minute: int = 15
    market_close_hour: int = 15
    market_close_minute: int = 29

    @classmethod
    def from_env(cls) -> 'TraderConfig':
        """Create config from environment variables"""
        return cls(
            api_key=os.getenv("API_KEY", ""),
            api_secret=os.getenv("API_SECRET", ""),
            access_token=os.getenv("ACCESS_TOKEN", ""),
            daily_budget=float(os.getenv("DAILY_BUDGET", "100000")),
            per_stock_daily_budget=float(os.getenv("PER_STOCK_DAILY_BUDGET", "100000")),
            max_qty_per_stock=int(os.getenv("MAX_QTY_PER_STOCK", "500")),
            max_budget=float(os.getenv("MAX_BUDGET", "0")),
            stop_loss_percent=float(os.getenv("STOP_LOSS_PERCENT", "0.10")),
            target_percent=float(os.getenv("TARGET_PERCENT", "0.06")),
            gtt_buy_budget_per_stock=float(os.getenv("GTT_BUY_BUDGET_PER_STOCK", "10000")),
            base_order_qty=int(os.getenv("BASE_ORDER_QTY", "5")),
        )


@dataclass
class OrderResult:
    """Structured result from order placement"""
    success: bool
    dry_run: bool
    order_id: Optional[str] = None
    error: Optional[str] = None


class KiteTrader:
    """
    Main trading class that encapsulates all Kite trading operations.
    
    Usage:
        trader = KiteTrader()
        trader.connect(access_token)
        
        # Get holdings
        holdings = trader.get_holdings()
        
        # Place orders
        trader.run_tranche_strategy()
        trader.protect_holdings()
    """
    
    def __init__(self, config: TraderConfig = None):
        """Initialize KiteTrader with optional config"""
        self.config = config or TraderConfig.from_env()
        self.kite: Optional[KiteConnect] = None
        self.connected: bool = False
        self.user_name: str = ""
        self.user_id: str = ""
        
        # Tracking
        self.bought_tracker: Dict[str, int] = {}
        self.actual_spent: Dict[str, float] = {'total': 0.0}

        # Tick size cache (per exchange -> symbol -> tick size)
        self._tick_size_map: Dict[str, Dict[str, Decimal]] = {}
        
        # Callbacks for logging (can be overridden by UI)
        self.on_log: Optional[Callable[[str, str], None]] = None
    
    def log(self, message: str, level: str = "info"):
        """Log a message, optionally calling UI callback"""
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
            
            # Validate by fetching profile
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
        self.log("Disconnected from Kite", "info")
    
    def validate_connection(self) -> bool:
        """Check if connected"""
        if not self.connected or not self.kite:
            self.log("Not connected to Kite", "error")
            return False
        return True
    
    # ==================== UTILITIES ====================

    def get_tick_size(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Return the instrument tick size for a symbol.

        Kite rejects LIMIT prices that are not a multiple of the instrument's
        tick size (some symbols use 0.10, others 0.05, etc.). We lazily fetch
        instrument metadata once per exchange and cache it.
        """
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
            # Load all instruments for the exchange once.
            if not self._tick_size_map[exchange]:
                instruments = self.with_backoff(self.kite.instruments, exchange)
                for inst in instruments:
                    ts = (inst.get('tradingsymbol') or '').strip().upper()
                    tick = inst.get('tick_size', None)
                    if ts:
                        self._tick_size_map[exchange][ts] = Decimal(str(tick)) if tick is not None else self.config.default_tick

            return self._tick_size_map[exchange].get(symbol, self.config.default_tick)
        except Exception as e:
            # Fall back to default tick if instruments lookup fails.
            self.log(f"Tick size lookup failed for {exchange}:{symbol}: {e}", "warning")
            return self.config.default_tick
    
    def round_to_tick(self, price: float, *, symbol: Optional[str] = None, exchange: str = "NSE") -> float:
        """Round price to nearest valid tick for the given symbol."""
        d = Decimal(str(price))
        tick = self.get_tick_size(symbol, exchange) if symbol else self.config.default_tick
        return float((d / tick).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick)
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now()
        market_open = now.replace(hour=self.config.market_open_hour, minute=self.config.market_open_minute, second=0)
        market_close = now.replace(hour=self.config.market_close_hour, minute=self.config.market_close_minute, second=0)
        return market_open <= now <= market_close
    
    def with_backoff(self, fn, *args, retries: int = 3, base: float = 0.5, **kwargs):
        """Execute function with exponential backoff retry"""
        last_error = None
        for attempt in range(retries):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    wait = base * (2 ** attempt) + random.uniform(0, 0.1)
                    time.sleep(wait)
        raise last_error
    
    @staticmethod
    def safe_float(value, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def is_top15_rank(rank: str) -> bool:
        """Return True if a CSV Rank value should be included in the Top15 universe.

        Supports common rank formats used in our CSVs:
        - Labels: Top5/Top10/Top15
        - Labels: Next5 (treated as ranks 6-10)
        - Numeric: 1..15
        - Legacy: A1/B1 style buckets

        Any unknown format is treated as NOT Top15 (fail-closed).
        """
        if not rank:
            return False

        s = str(rank).strip()
        if not s:
            return False

        if s.isdigit():
            try:
                return int(s) <= 15
            except Exception:
                return False

        m = re.match(r"^top\s*(\d+)$", s, flags=re.I)
        if m:
            try:
                return int(m.group(1)) <= 15
            except Exception:
                return False

        m = re.match(r"^next\s*(\d+)$", s, flags=re.I)
        if m:
            try:
                k = int(m.group(1))
                upper = 5 + k  # Next5 => 6-10
                return upper <= 15
            except Exception:
                return False

        # Legacy bucket ranks
        return s.upper().startswith(("A", "B")) and len(s) <= 3
    
    def compute_qty_from_budget(self, ltp: float, budget: float, max_qty: int = None) -> int:
        """Calculate quantity from budget"""
        max_qty = max_qty or self.config.max_qty_per_stock
        if ltp <= 0 or budget <= 0:
            return 0
        qty = int(budget / ltp)
        return min(qty, max_qty) if max_qty > 0 else qty
    
    # ==================== DATA FETCHING ====================
    
    def get_holdings(self) -> List[Dict]:
        """Get all holdings with quantity > 0"""
        if not self.validate_connection():
            return []
        try:
            holdings = self.with_backoff(self.kite.holdings)
            return [h for h in holdings if h.get('quantity', 0) > 0]
        except Exception as e:
            self.log(f"Error fetching holdings: {e}", "error")
            return []
    
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
    
    def batch_fetch_ltp(self, symbols: List[str]) -> Dict[str, float]:
        """Batch fetch LTP with rate limiting"""
        if not self.validate_connection():
            return {}
        
        result = {}
        batch_size = 50
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            try:
                instruments = [f"NSE:{s}" for s in batch]
                ltp_data = self.with_backoff(self.kite.ltp, instruments)
                for s in batch:
                    key = f"NSE:{s}"
                    if key in ltp_data:
                        result[s] = ltp_data[key]['last_price']
            except Exception as e:
                self.log(f"Error fetching batch LTP: {e}", "error")
            
            if i + batch_size < len(symbols):
                time.sleep(0.5)
        
        return result
    
    # ==================== ORDER BOOK ====================

    @staticmethod
    def _row_get_ci(row: Dict, key: str, default: Any = "") -> Any:
        """Case-insensitive dict access for CSV rows.

        `csv.DictReader` preserves header casing; many of our CSVs use TitleCase
        headers (e.g. `Symbol`, `Quantity`, `Order_Type`). This helper lets the
        trader accept both styles.
        """
        if key in row:
            return row.get(key, default)
        lower_map = {str(k).strip().lower(): v for k, v in row.items()}
        return lower_map.get(str(key).strip().lower(), default)
    
    def read_order_book(self, filepath: str = None) -> List[Dict]:
        """Read orders from CSV file"""
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
                        'transaction': str(self._row_get_ci(row, 'transaction', 'BUY')).upper(),
                        'variety': str(self._row_get_ci(row, 'variety', 'regular')).lower(),
                    })
        except FileNotFoundError:
            self.log(f"Order book not found: {filepath}", "error")
        except Exception as e:
            self.log(f"Error reading order book: {e}", "error")
        
        return orders

    @staticmethod
    def _order_is_within_top_n(order_rank: str, top_n: int) -> bool:
        """Return True if an order's rank falls within Top-N.

        Supports:
        - Numeric ranks: "1", "15" (<= top_n)
        - Labels: "Top5", "Top10", "Top15", "Top25" (included if that label's N <= top_n)
        - Labels: "Next5" (treated as ranks 6-10, included if top_n >= 10)

        If rank is missing/unrecognized, we include it (fail-open) to avoid
        surprising exclusions.
        """
        if not top_n or top_n <= 0:
            return True

        if not order_rank:
            return True

        s = str(order_rank).strip()
        if not s:
            return True

        if s.isdigit():
            try:
                return int(s) <= top_n
            except Exception:
                return True

        m = re.match(r"^top\s*(\d+)$", s, flags=re.I)
        if m:
            return int(m.group(1)) <= top_n

        m = re.match(r"^next\s*(\d+)$", s, flags=re.I)
        if m:
            k = int(m.group(1))
            upper = 5 + k  # Next5 => 6-10
            return upper <= top_n

        return True
    
    def update_order_book_prices(self, filepath: str = None):
        """Update order book CSV with current LTP"""
        filepath = filepath or self.config.order_book_file
        if not self.validate_connection():
            return
        
        orders = self.read_order_book(filepath)
        if not orders:
            self.log("No orders to update", "warning")
            return
        
        symbols = [o['symbol'] for o in orders]
        ltp_map = self.batch_fetch_ltp(symbols)
        
        # Backup original file
        backup_path = filepath.replace('.csv', '_backup.csv')
        shutil.copy(filepath, backup_path)
        
        # Update prices
        updated = 0
        with open(filepath, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        for row in rows:
            symbol = str(self._row_get_ci(row, 'symbol', '')).strip().upper()
            if symbol in ltp_map:
                # Preserve the original header casing if possible.
                if 'Price' in row:
                    row['Price'] = str(ltp_map[symbol])
                else:
                    row['price'] = str(ltp_map[symbol])
                updated += 1
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        self.log(f"Updated {updated} prices in {filepath}", "success")
    
    # ==================== NEGATIVE P&L OPERATIONS ====================
    
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
    
    def sell_stock(self, symbol: str, quantity: int, exchange: str = "NSE", 
                   product: str = "CNC") -> Optional[str]:
        """Place sell order for a stock"""
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
    
    def sell_negative_holdings(self) -> int:
        """Sell all stocks with negative P&L"""
        if not self.validate_connection():
            return 0
        
        negative = self.get_negative_holdings()
        if not negative:
            self.log("No stocks with negative P&L found", "info")
            return 0
        
        total_loss = sum(h['pnl'] for h in negative)
        self.log(f"Found {len(negative)} stocks with total loss: ₹{total_loss:.2f}", "warning")
        
        sold = 0
        for stock in negative:
            result = self.sell_stock(
                stock['tradingsymbol'],
                stock['quantity'],
                stock['exchange']
            )
            if result:
                sold += 1
        
        self.log(f"Processed {sold}/{len(negative)} sell orders", "success")
        return sold
    
    def sell_all_holdings(self) -> int:
        """Sell all holdings"""
        if not self.validate_connection():
            return 0
        
        holdings = self.get_holdings()
        if not holdings:
            self.log("No holdings to sell", "info")
            return 0
        
        total_value = sum(h['quantity'] * h.get('last_price', h['average_price']) for h in holdings)
        self.log(f"Selling {len(holdings)} stocks worth ₹{total_value:.2f}", "warning")
        
        sold = 0
        for h in holdings:
            result = self.sell_stock(
                h['tradingsymbol'],
                h['quantity'],
                h['exchange']
            )
            if result:
                sold += 1
        
        self.log(f"Processed {sold}/{len(holdings)} sell orders", "success")
        return sold
    
    # ==================== BUY OPERATIONS ====================
    
    def place_buy_order(self, symbol: str, quantity: int, price: float = None,
                        exchange: str = "NSE", product: str = "CNC",
                        order_type: str = "MARKET") -> OrderResult:
        """Place a buy order"""
        if not self.validate_connection():
            return OrderResult(success=False, dry_run=False, error="Not connected")
        
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
                return OrderResult(success=True, dry_run=True)
            else:
                order_id = self.kite.place_order(**order_params)
                self.log(f"Bought: {symbol} x {quantity} - Order ID: {order_id}", "success")
                return OrderResult(success=True, dry_run=False, order_id=order_id)
        except Exception as e:
            self.log(f"Error buying {symbol}: {e}", "error")
            return OrderResult(success=False, dry_run=False, error=str(e))
    
    # ==================== GTT OPERATIONS ====================
    
    def get_existing_gtts(self) -> Set[str]:
        """Get symbols with existing active GTT orders (sell side)"""
        gtts = self.get_gtts()
        symbols = set()
        for gtt in gtts:
            if gtt.get('status') == 'active':
                orders = gtt.get('orders', [])
                if orders and orders[0].get('transaction_type') == 'SELL':
                    symbols.add(gtt.get('tradingsymbol'))
        return symbols
    
    def get_existing_gtt_buy_symbols(self) -> Set[str]:
        """Get symbols with existing active GTT BUY orders"""
        gtts = self.get_gtts()
        symbols = set()
        for gtt in gtts:
            if gtt.get('status') == 'active':
                orders = gtt.get('orders', [])
                if orders and orders[0].get('transaction_type') == 'BUY':
                    symbols.add(gtt.get('tradingsymbol'))
        return symbols
    
    def delete_gtt(self, gtt_id: int) -> bool:
        """Delete a single GTT order"""
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
    
    def delete_existing_gtts(self, symbols_to_refresh: Set[str] = None) -> int:
        """Delete existing GTT orders (sell side)"""
        gtts = self.get_gtts()
        deleted = 0
        
        for gtt in gtts:
            if gtt.get('status') != 'active':
                continue
            
            orders = gtt.get('orders', [])
            if not orders or orders[0].get('transaction_type') != 'SELL':
                continue
            
            symbol = gtt.get('tradingsymbol')
            if symbols_to_refresh and symbol not in symbols_to_refresh:
                continue
            
            if self.delete_gtt(gtt.get('id')):
                deleted += 1
        
        self.log(f"Deleted {deleted} sell GTT(s)", "info")
        return deleted
    
    def delete_existing_gtt_buys(self, symbols_to_refresh: Set[str] = None) -> int:
        """Delete existing GTT BUY orders"""
        gtts = self.get_gtts()
        deleted = 0
        
        for gtt in gtts:
            if gtt.get('status') != 'active':
                continue
            
            orders = gtt.get('orders', [])
            if not orders or orders[0].get('transaction_type') != 'BUY':
                continue
            
            symbol = gtt.get('tradingsymbol')
            if symbols_to_refresh and symbol not in symbols_to_refresh:
                continue
            
            if self.delete_gtt(gtt.get('id')):
                deleted += 1
        
        self.log(f"Deleted {deleted} buy GTT(s)", "info")
        return deleted
    
    def place_gtt_oco(self, symbol: str, quantity: int, buy_price: float,
                      product: str = 'CNC', sl_pct: float = None, 
                      target_pct: float = None) -> Optional[int]:
        """Place GTT OCO (One-Cancels-Other) order"""
        if not self.validate_connection():
            return None
        
        sl_pct = sl_pct or self.config.stop_loss_percent
        target_pct = target_pct or self.config.target_percent
        
        sl_trigger = self.round_to_tick(buy_price * (1 - sl_pct), symbol=symbol, exchange='NSE')
        target_trigger = self.round_to_tick(buy_price * (1 + target_pct), symbol=symbol, exchange='NSE')
        sl_price = self.round_to_tick(sl_trigger * (1 - self.config.sl_execution_buffer), symbol=symbol, exchange='NSE')
        
        try:
            if self.config.dry_run:
                self.log(f"[DRY RUN] Would place GTT OCO for {symbol}: SL={sl_trigger}, Target={target_trigger}", "info")
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
            self.log(f"GTT OCO placed for {symbol}: ID={gtt_id}", "success")
            return gtt_id
        except Exception as e:
            self.log(f"Error placing GTT OCO for {symbol}: {e}", "error")
            return None
    
    def place_gtt_buy_order(self, symbol: str, quantity: int, current_price: float,
                            trigger_percent: float, product: str = 'CNC') -> Optional[int]:
        """Place GTT single-leg BUY order for dip accumulation"""
        if not self.validate_connection():
            return None
        
        trigger_price = self.round_to_tick(current_price * (1 - trigger_percent), symbol=symbol, exchange='NSE')
        limit_price = self.round_to_tick(trigger_price * 1.001, symbol=symbol, exchange='NSE')  # Slight buffer
        
        try:
            if self.config.dry_run:
                self.log(f"[DRY RUN] Would place GTT BUY for {symbol} x {quantity} @ {trigger_price}", "info")
                return 0
            
            kite_product = getattr(self.kite, f'PRODUCT_{product}', self.kite.PRODUCT_CNC)
            
            gtt_id = self.kite.place_gtt(
                trigger_type=self.kite.GTT_TYPE_SINGLE,
                tradingsymbol=symbol,
                exchange='NSE',
                trigger_values=[trigger_price],
                last_price=current_price,
                orders=[
                    {
                        'transaction_type': self.kite.TRANSACTION_TYPE_BUY,
                        'quantity': quantity,
                        'order_type': self.kite.ORDER_TYPE_LIMIT,
                        'product': kite_product,
                        'price': limit_price,
                    }
                ]
            )
            self.log(f"GTT BUY placed for {symbol}: ID={gtt_id}, trigger={trigger_price}", "success")
            return gtt_id
        except Exception as e:
            self.log(f"Error placing GTT BUY for {symbol}: {e}", "error")
            return None
    
    # ==================== PROTECTION OPERATIONS ====================
    
    def protect_holdings(self, refresh: bool = False, sl_pct: float = None, 
                        target_pct: float = None) -> int:
        """Protect all holdings with GTT OCO orders"""
        if not self.validate_connection():
            return 0
        
        # Get existing GTTs for idempotency
        existing_gtts = self.get_existing_gtts()
        
        if existing_gtts and refresh:
            self.log("Refresh mode: Deleting existing GTTs...", "info")
            self.delete_existing_gtts()
            existing_gtts = set()
        
        holdings = self.get_holdings()
        if not holdings:
            self.log("No holdings to protect", "info")
            return 0
        
        protected = 0
        for h in holdings:
            symbol = h['tradingsymbol']
            
            if symbol in existing_gtts:
                self.log(f"Skipping {symbol} - already has GTT protection", "info")
                continue
            
            quantity = h['quantity']
            avg_price = h['average_price']
            
            if quantity <= 0 or avg_price <= 0:
                continue
            
            result = self.place_gtt_oco(symbol, quantity, avg_price, 'CNC', sl_pct, target_pct)
            if result is not None:
                protected += 1
        
        self.log(f"Protected {protected}/{len(holdings)} holdings", "success")
        return protected
    
    def protect_holdings_sliced(self, refresh: bool = False) -> int:
        """Protect holdings with sliced GTT OCO (multiple levels)"""
        if not self.validate_connection():
            return 0
        
        if refresh:
            self.delete_existing_gtts()
        
        existing_gtts = self.get_existing_gtts()
        holdings = self.get_holdings()
        
        if not holdings:
            self.log("No holdings to protect", "info")
            return 0
        
        protected = 0
        for h in holdings:
            symbol = h['tradingsymbol']
            
            if symbol in existing_gtts:
                self.log(f"Skipping {symbol} - already has GTT protection", "info")
                continue
            
            total_qty = h['quantity']
            avg_price = h['average_price']
            
            if total_qty <= 0 or avg_price <= 0:
                continue
            
            # Place GTT for each slice
            for qty_pct, sl_pct, target_pct in self.config.gtt_slices:
                slice_qty = max(1, int(total_qty * qty_pct))
                result = self.place_gtt_oco(symbol, slice_qty, avg_price, 'CNC', sl_pct, target_pct)
                if result is not None:
                    protected += 1
        
        self.log(f"Created {protected} sliced GTT OCOs", "success")
        return protected
    
    # ==================== GTT BUY OPERATIONS ====================
    
    def place_gtt_buy_orders(self, refresh: bool = False) -> int:
        """Place GTT buy orders for dip accumulation.

        Prefers `data/tips_research_data.csv` (generated tips universe) when it
        exists; otherwise falls back to the configured order book file.
        """
        if not self.validate_connection():
            return 0

        repo_root = Path(__file__).resolve().parents[1]
        tips_path = repo_root / "data" / "tips_research_data.csv"
        if tips_path.exists():
            self.log(f"Using tips universe for GTT buys: {tips_path}", "info")
            orders = self.read_order_book(str(tips_path))
        else:
            orders = self.read_order_book()
        if not orders:
            self.log("No orders in order book", "error")
            return 0
        
        # Filter for Top15 only
        orders = [o for o in orders if self.is_top15_rank(o.get('rank', ''))]
        if not orders:
            self.log("No Top15 stocks found", "warning")
            return 0
        
        symbols_in_book = {o['symbol'] for o in orders}
        
        if refresh:
            self.log("Refresh mode: Deleting existing BUY GTTs...", "info")
            self.delete_existing_gtt_buys(symbols_in_book)
            existing = set()
        else:
            existing = self.get_existing_gtt_buy_symbols()
            orders = [o for o in orders if o['symbol'] not in existing]
            
            if not orders:
                self.log("All stocks already have GTT BUY orders", "info")
                return 0
        
        # Fetch LTPs
        symbols = [o['symbol'] for o in orders]
        ltp_map = self.batch_fetch_ltp(symbols)
        
        placed = 0
        budget = self.config.gtt_buy_budget_per_stock  # e.g., ₹10,000 per GTT buy order

        for order in orders:
            symbol = order['symbol']
            ltp = ltp_map.get(symbol, 0)
            
            if ltp <= 0:
                continue
            
            # Compute qty from budget so each GTT order is ~₹10k (makes ₹15.34 brokerage worthwhile)
            # Split budget: 60% for lower trigger, 40% for upper trigger
            lower_budget = budget * self.config.gtt_buy_qty_lower
            upper_budget = budget * self.config.gtt_buy_qty_upper

            # Trigger prices
            lower_trigger_price = ltp * (1 - self.config.gtt_buy_lower_percent)
            upper_trigger_price = ltp * (1 - self.config.gtt_buy_upper_percent)

            lower_qty = max(1, int(lower_budget / lower_trigger_price))
            upper_qty = max(1, int(upper_budget / upper_trigger_price))

            # Cap at max_qty_per_stock
            lower_qty = min(lower_qty, self.config.max_qty_per_stock)
            upper_qty = min(upper_qty, self.config.max_qty_per_stock)

            # Place at lower trigger (2% below)
            result1 = self.place_gtt_buy_order(symbol, lower_qty, ltp, 
                                               self.config.gtt_buy_lower_percent, 
                                               order.get('product', 'CNC'))
            
            # Place at upper trigger (4% below)
            result2 = self.place_gtt_buy_order(symbol, upper_qty, ltp,
                                               self.config.gtt_buy_upper_percent,
                                               order.get('product', 'CNC'))
            
            if result1 is not None or result2 is not None:
                placed += 1
        
        self.log(f"Placed GTT BUY orders for {placed} stocks", "success")
        return placed
    
    # ==================== REPRICE OPERATIONS ====================
    
    def get_pending_limit_buy_orders(self) -> List[Dict]:
        """Get pending LIMIT BUY orders"""
        orders = self.get_orders()
        return [
            o for o in orders
            if o.get('status') == 'OPEN'
            and o.get('transaction_type') == 'BUY'
            and o.get('order_type') == 'LIMIT'
        ]
    
    def reprice_pending_limit_buys(self, discount: float = 0.99) -> int:
        """Reprice pending LIMIT BUY orders"""
        if not self.validate_connection():
            return 0
        
        pending = self.get_pending_limit_buy_orders()
        if not pending:
            self.log("No pending LIMIT BUY orders", "info")
            return 0
        
        symbols = list(set(o['tradingsymbol'] for o in pending))
        ltp_map = self.batch_fetch_ltp(symbols)
        
        repriced = 0
        for order in pending:
            symbol = order['tradingsymbol']
            ltp = ltp_map.get(symbol, 0)
            
            if ltp <= 0:
                continue
            
            new_price = self.round_to_tick(ltp * discount, symbol=symbol, exchange=order.get('exchange', 'NSE'))
            
            try:
                if self.config.dry_run:
                    self.log(f"[DRY RUN] Would reprice {symbol} to {new_price}", "info")
                    repriced += 1
                else:
                    self.kite.modify_order(
                        variety=order['variety'],
                        order_id=order['order_id'],
                        price=new_price
                    )
                    self.log(f"Repriced {symbol} to {new_price}", "success")
                    repriced += 1
            except Exception as e:
                self.log(f"Error repricing {symbol}: {e}", "error")
        
        self.log(f"Repriced {repriced}/{len(pending)} orders", "success")
        return repriced
    
    # ==================== NEW STOCKS OPERATIONS ====================
    
    def find_new_stocks(self) -> List[Dict]:
        """Find new stocks from research file not in current holdings"""
        if not self.validate_connection():
            return []
        
        holdings = self.get_holdings()
        holding_symbols = {h['tradingsymbol'] for h in holdings}
        
        research_orders = self.read_order_book(self.config.research_file)
        
        new_stocks = [
            o for o in research_orders
            if o['symbol'] not in holding_symbols
        ]
        
        return new_stocks
    
    def buy_new_stocks(self) -> int:
        """Buy 1 share of each new stock from research file"""
        if not self.validate_connection():
            return 0
        
        new_stocks = self.find_new_stocks()
        if not new_stocks:
            self.log("No new stocks to buy", "info")
            return 0
        
        self.log(f"Found {len(new_stocks)} new stocks to buy", "info")
        
        bought = 0
        for stock in new_stocks:
            result = self.place_buy_order(
                stock['symbol'],
                quantity=1,
                exchange=stock.get('exchange', 'NSE'),
                product=stock.get('product', 'CNC'),
                order_type='MARKET'
            )
            if result.success:
                bought += 1
        
        self.log(f"Bought {bought}/{len(new_stocks)} new stocks", "success")
        return bought
    
    # ==================== TRANCHE STRATEGY ====================
    
    def initialize_tracker(self, symbols: List[str]) -> Tuple[Dict[str, int], Dict[str, float]]:
        """Initialize bought tracker from today's orders"""
        bought_tracker = {}
        actual_spent = {'total': 0.0}
        
        if not self.validate_connection():
            return bought_tracker, actual_spent
        
        orders = self.get_orders()
        
        for order in orders:
            if order.get('status') not in ('COMPLETE', 'TRADED'):
                continue
            if order.get('transaction_type') != 'BUY':
                continue
            
            symbol = order.get('tradingsymbol')
            if symbol not in symbols:
                continue
            
            qty = order.get('filled_quantity', 0)
            avg_price = order.get('average_price', 0)
            
            bought_tracker[symbol] = bought_tracker.get(symbol, 0) + qty
            actual_spent['total'] += qty * avg_price
        
        return bought_tracker, actual_spent
    
    def run_tranche_strategy(self, *, top_n_rank: Optional[int] = None) -> bool:
        """Execute the main tranche buying strategy.

        Args:
            top_n_rank: If set (e.g., 15), only execute orders whose `rank` is
                within Top-N (supports numeric rank and labels like Top15/Next5).
        """
        if not self.validate_connection():
            return False
        
        if not self.config.dry_run and not self.is_market_hours():
            self.log("Market is closed. Cannot execute live orders.", "error")
            return False
        
        orders = self.read_order_book()
        if top_n_rank:
            orders = [o for o in orders if self._order_is_within_top_n(o.get('rank', ''), top_n_rank)]
        if not orders:
            self.log("No orders found in order book", "error")
            return False
        
        if top_n_rank:
            self.log(f"Starting tranche strategy with {len(orders)} stocks (Top{top_n_rank} filter)", "info")
        else:
            self.log(f"Starting tranche strategy with {len(orders)} stocks", "info")
        
        # Initialize tracker
        symbols = [o['symbol'] for o in orders]
        self.bought_tracker, self.actual_spent = self.initialize_tracker(symbols)
        
        # Check if already complete
        all_complete = all(
            self.bought_tracker.get(o['symbol'], 0) >= o['quantity']
            for o in orders
        )
        
        if all_complete:
            self.log("All orders already complete from previous run!", "success")
            return True
        
        # Phase 1: Base orders (base_order_qty shares each, default 5)
        base_qty = self.config.base_order_qty
        stocks_needing_base = [
            o for o in orders 
            if self.bought_tracker.get(o['symbol'], 0) < base_qty
        ]
        
        if stocks_needing_base:
            self.log(f"Phase 1: Placing base orders ({base_qty} qty each) for {len(stocks_needing_base)} stocks", "info")
            for stock in stocks_needing_base:
                already_bought = self.bought_tracker.get(stock['symbol'], 0)
                qty_needed = base_qty - already_bought
                if qty_needed <= 0:
                    continue
                result = self.place_buy_order(
                    stock['symbol'],
                    quantity=qty_needed,
                    price=stock.get('price'),
                    exchange=stock.get('exchange', 'NSE'),
                    product=stock.get('product', 'CNC'),
                    order_type='MARKET'
                )
                if result.success:
                    self.bought_tracker[stock['symbol']] = already_bought + qty_needed
        else:
            self.log("Phase 1: All base orders already placed", "info")
        
        # Phase 2: Tranches
        for tranche in range(1, self.config.tranche_count + 1):
            self.log(f"Phase 2: Executing tranche {tranche}/{self.config.tranche_count}", "info")
            
            # Fetch current LTPs
            ltp_map = self.batch_fetch_ltp(symbols)
            
            for order in orders:
                symbol = order['symbol']
                target_qty = order['quantity']
                bought = self.bought_tracker.get(symbol, 0)
                remaining = target_qty - bought
                
                if remaining <= 0:
                    continue
                
                # Calculate tranche quantity
                tranche_qty = max(1, int(remaining * self.config.tranche_size))
                
                ltp = ltp_map.get(symbol, 0)
                if ltp <= 0:
                    continue
                
                limit_price = ltp * self.config.ltp_discount
                
                result = self.place_buy_order(
                    symbol,
                    quantity=tranche_qty,
                    price=limit_price,
                    exchange=order.get('exchange', 'NSE'),
                    product=order.get('product', 'CNC'),
                    order_type='LIMIT'
                )
                
                if result.success:
                    self.bought_tracker[symbol] = bought + tranche_qty
            
            # Wait between tranches
            if tranche < self.config.tranche_count:
                wait_time = 2 if self.config.dry_run else self.config.tranche_interval
                self.log(f"Waiting {wait_time}s until next tranche...", "info")
                time.sleep(wait_time)
        
        self.log(f"Tranche strategy complete. Total spent: ₹{self.actual_spent['total']:,.2f}", "success")
        return True
    
    # ==================== SUMMARY ====================
    
    def get_portfolio_summary(self) -> Dict:
        """Get portfolio summary"""
        holdings = self.get_holdings()
        
        total_value = sum(
            h['quantity'] * h.get('last_price', h['average_price']) 
            for h in holdings
        )
        total_pnl = sum(h.get('pnl', 0) for h in holdings)
        total_invested = sum(
            h['quantity'] * h['average_price'] 
            for h in holdings
        )
        
        return {
            'total_stocks': len(holdings),
            'total_value': total_value,
            'total_invested': total_invested,
            'total_pnl': total_pnl,
            'pnl_percent': (total_pnl / total_invested * 100) if total_invested > 0 else 0,
        }
