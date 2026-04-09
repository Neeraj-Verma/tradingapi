"""
Zerodha Kite - Buy stocks from order_book.csv using Tranche Strategy
Requires: pip install kiteconnect python-dotenv

Strategy:
1. 9:15 AM - Buy 1 share of each at MARKET price (base price run)
2. Hourly (4 tranches) - Buy 25% of remaining qty at LIMIT price (0.2% below LTP)
"""

import os
import csv
import sys
import time
import math
import random
import shutil
import argparse
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from kiteconnect import KiteConnect
import logging

# Load environment variables from .env
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== CONFIGURATION ==========
API_KEY = os.getenv("API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Set to False for actual execution, True for dry run
DRY_RUN = True
ORDER_BOOK_FILE = "data/order_book.csv"

# Tranche Strategy Settings
TRANCHE_SIZE = 0.20  # 20% of remaining quantity per hour
TRANCHE_COUNT = 5    # Number of hourly tranches
LTP_DISCOUNT = 0.998 # Buy at 0.2% below LTP for limit orders
TRANCHE_INTERVAL = 3600  # 1 hour between tranches (in seconds)

# Stop Loss Settings
# âš ï¸  RECOMMENDATION: Set STOP_LOSS_ENABLED = False during buying
#     Then run 'python buy_stocks.py --protect' at 3:20 PM
#     This creates 1 consolidated GTT per stock (saves GTT slots, max 100/account)
STOP_LOSS_ENABLED = False  # Set True for per-order SL (uses more GTT slots)
STOP_LOSS_PERCENT = 0.08  # 8% below buy price
TARGET_PERCENT = 0.16     # 16% above buy price (for OCO)
USE_GTT = True   # True = GTT, False = SL-M (session only)
USE_OCO = True   # True = OCO (SL + Target), False = Single SL only
SL_EXECUTION_BUFFER = 0.05  # 5% buffer below trigger for gap-down scenarios

# GTT Buy Settings (for --gtt-buy)
# Places GTT buy orders to accumulate stocks on dips
GTT_BUY_LOWER_PERCENT = 0.02  # 2% below current price (first dip buy)
GTT_BUY_UPPER_PERCENT = 0.04  # 4% below current price (deeper dip buy)
GTT_BUY_QTY_LOWER = 0.60      # 60% of quantity at lower trigger
GTT_BUY_QTY_UPPER = 0.40      # 40% of quantity at upper trigger

# Sliced GTT OCO Settings (for --protect --sliced)
# Creates multiple GTTs per stock with graduated SL/Target levels
# Format: [(qty_percent, sl_percent, target_percent), ...]
# Example: Sell 30% at -5%/+10%, 40% at -8%/+15%, 30% at -10%/+20%
GTT_SLICES = [
    (0.30, 0.05, 0.10),  # Slice 1: 30% qty, SL -5%, Target +10% (early profit booking)
    (0.40, 0.08, 0.15),  # Slice 2: 40% qty, SL -8%, Target +15% (moderate)
    (0.30, 0.10, 0.20),  # Slice 3: 30% qty, SL -10%, Target +20% (let winners run)
]
# âš ï¸  Each slice = 1 GTT. 40 stocks Ã— 3 slices = 120 GTTs (exceeds 100 limit!)
#     Use fewer slices or fewer stocks if hitting GTT limit.

# Risk Controls
MAX_BUDGET = float(os.getenv("MAX_BUDGET", "0"))  # 0 = no cap (legacy guard)
MAX_LTP_DRIFT = 0.03  # 3% - skip if limit price too far from LTP (stocks move >1% intraday)
DEFAULT_TICK = Decimal(os.getenv("DEFAULT_TICK", "0.05"))  # NSE tick size

# Budget-Based Tranche Strategy
# When USE_BUDGET_MODE = True, quantities are calculated from budget allocation
# Budget is split: BASE_BUDGET_PERCENT for Phase 1, rest distributed across tranches
USE_BUDGET_MODE = True  # True = budget-based qty, False = CSV quantity-based
DAILY_BUDGET = float(os.getenv("DAILY_BUDGET", "100000"))  # Total budget for the day (â‚¹1 lakh default)
BASE_BUDGET_PERCENT = 0.10  # 10% of budget for base orders (1 share each)
# Remaining 90% split across TRANCHE_COUNT tranches (22.5% each for 4 tranches)

# Per-Stock Limits (caps applied per stock)
PER_STOCK_DAILY_BUDGET = float(os.getenv("PER_STOCK_DAILY_BUDGET", "100000"))  # Max â‚¹1L per stock per day
MAX_QTY_PER_STOCK = int(os.getenv("MAX_QTY_PER_STOCK", "500"))  # Max 500 shares per stock

# Market Hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 29

# âš ï¸  IMPORTANT: CDSL TPIN AUTHORIZATION
# For CNC sell orders (including GTT), Zerodha requires TPIN authorization daily
# Unless you've submitted POA/DDPI, authorize holdings at 9:00 AM before market opens!
# Kite App â†’ Portfolio â†’ Holdings â†’ Authorize (CDSL TPIN)

# âš ï¸  GTT LIMIT: Zerodha allows max 100 active GTTs per account
# Recommendation: Set STOP_LOSS_ENABLED = False during buying, then run:
#   python buy_stocks.py --protect
# at end of day to create 1 consolidated GTT per stock (saves GTT slots)
# ===================================


@dataclass
class Config:
    """Runtime configuration - avoids global variable mutation"""
    dry_run: bool = True
    order_book_file: str = "data/order_book.csv"
    max_budget: float = 0.0
    daily_budget: float = 0.0
    use_budget_mode: bool = True
    base_budget_actual: float = 0.0  # Actual cost for Phase 1 (sum of LTPs)
    per_stock_daily_budget: float = 100000.0  # Max â‚¹1L per stock per day
    max_qty_per_stock: int = 500  # Max 500 shares per stock


# Global config instance
CONFIG = Config(
    dry_run=DRY_RUN,
    order_book_file=ORDER_BOOK_FILE,
    max_budget=MAX_BUDGET,
    daily_budget=DAILY_BUDGET,
    use_budget_mode=USE_BUDGET_MODE,
    per_stock_daily_budget=PER_STOCK_DAILY_BUDGET,
    max_qty_per_stock=MAX_QTY_PER_STOCK
)


@dataclass
class OrderResult:
    """Structured result from order placement"""
    success: bool
    dry_run: bool
    order_id: Optional[str] = None
    error: Optional[str] = None


def round_to_tick(price: float, tick: Decimal = DEFAULT_TICK) -> float:
    """
    Round price to nearest tick size (NSE default: 0.05).
    Prevents order rejections due to invalid price granularity.
    """
    p = Decimal(str(price))
    steps = (p / tick).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return float((steps * tick).quantize(tick, rounding=ROUND_HALF_UP))


def is_kill_switch_on() -> bool:
    """Check if kill switch is engaged (file or env var)"""
    return os.path.exists("KILL_SWITCH_ON") or os.getenv("KILL_SWITCH", "0") == "1"


def is_market_hours() -> bool:
    """Check if current time is within NSE market hours (9:15 AM - 3:29 PM IST)"""
    now = datetime.now()
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=59)
    return market_open <= now <= market_close


def with_backoff(fn, *args, retries: int = 3, base: float = 0.5, **kwargs):
    """
    Execute function with exponential backoff on failure.
    Helps with rate limiting and transient API errors.
    """
    for i in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if i == retries:
                raise
            wait = base * (2 ** i) + random.random() * 0.25
            logger.warning(f"Retry {i+1}/{retries} after {wait:.2f}s: {e}")
            time.sleep(wait)


def validate_credentials():
    """Validate required API credentials exist"""
    missing = []
    if not API_KEY:
        missing.append("API_KEY")
    if not ACCESS_TOKEN:
        missing.append("ACCESS_TOKEN")
    
    if missing:
        logger.error(f"âŒ Missing required credentials: {', '.join(missing)}")
        logger.error("   Set them in .env file or environment variables")
        return False
    return True


def get_kite_client():
    """Initialize and return Kite client"""
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    return kite


def wait_for_order_completion(kite, order_id, symbol, max_wait=10, poll_interval=3):
    """
    Poll order status until COMPLETE or timeout.
    Returns dict with filled_quantity and average_price, or None if failed.
    
    Note: Reduced polling frequency to avoid API rate limits.
    For LIMIT orders, fills may happen later - use get_actual_holdings() for accurate tracking.
    """
    if CONFIG.dry_run:
        return None
    
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            order_history = kite.order_history(order_id)
            latest = order_history[-1] if order_history else None
            
            if latest:
                status = latest.get('status', '')
                if status == 'COMPLETE':
                    return {
                        'filled_quantity': latest.get('filled_quantity', 0),
                        'average_price': latest.get('average_price', 0),
                        'status': 'COMPLETE'
                    }
                elif status in ['REJECTED', 'CANCELLED']:
                    logger.warning(f"Order {order_id} for {symbol} was {status}")
                    return {'filled_quantity': 0, 'average_price': 0, 'status': status}
            
            time.sleep(poll_interval)
        except Exception as e:
            logger.error(f"Error polling order {order_id}: {e}")
            time.sleep(poll_interval)
    
    # Check final status after timeout
    try:
        order_history = kite.order_history(order_id)
        if order_history:
            latest = order_history[-1]
            return {
                'filled_quantity': latest.get('filled_quantity', 0),
                'average_price': latest.get('average_price', 0),
                'status': latest.get('status', 'PENDING')
            }
    except:
        pass
    
    logger.warning(f"Order {order_id} for {symbol} still pending after {max_wait}s")
    return None


def get_actual_holdings(kite, symbols: list) -> dict:
    """
    Get actual holdings from broker for accurate position tracking.
    More reliable than local tracker for LIMIT orders that fill later.
    
    Returns: {symbol: quantity}
    """
    if CONFIG.dry_run:
        return {}
    
    try:
        holdings = with_backoff(kite.holdings)
        result = {}
        for h in holdings:
            sym = h.get('tradingsymbol', '')
            if sym in symbols:
                result[sym] = h.get('quantity', 0)
        return result
    except Exception as e:
        logger.error(f"Error fetching holdings: {e}")
        return {}


def get_todays_buy_orders(kite, symbols: list) -> dict:
    """
    Fetch today's BUY orders for given symbols to enable idempotent re-runs.
    Returns dict: {symbol: {'filled_qty': int, 'pending_qty': int, 'avg_price': float}}
    
    This allows the script to:
    1. Skip stocks that already have orders placed today
    2. Resume from where it left off after cancellation
    3. Avoid duplicate orders on re-run
    """
    if CONFIG.dry_run:
        return {}
    
    try:
        orders = with_backoff(kite.orders)
        today = datetime.now().date()
        
        result = {}
        for o in orders:
            sym = o.get('tradingsymbol', '')
            if sym not in symbols:
                continue
            
            # Only consider BUY orders
            if o.get('transaction_type') != 'BUY':
                continue
            
            # Check if order is from today
            order_time = o.get('order_timestamp')
            if order_time:
                if hasattr(order_time, 'date'):
                    order_date = order_time.date()
                else:
                    # Parse string timestamp
                    order_date = datetime.fromisoformat(str(order_time)[:10]).date()
                
                if order_date != today:
                    continue
            
            # Initialize if not exists
            if sym not in result:
                result[sym] = {'filled_qty': 0, 'pending_qty': 0, 'avg_price': 0.0, 'total_value': 0.0}
            
            status = o.get('status', '').upper()
            filled = o.get('filled_quantity', 0)
            pending = o.get('pending_quantity', 0)
            avg_price = o.get('average_price', 0)
            
            if status == 'COMPLETE':
                result[sym]['filled_qty'] += filled
                result[sym]['total_value'] += filled * avg_price
            elif status not in ('CANCELLED', 'REJECTED'):
                # OPEN, PENDING, etc.
                result[sym]['pending_qty'] += pending
                result[sym]['filled_qty'] += filled
                if filled > 0:
                    result[sym]['total_value'] += filled * avg_price
        
        # Calculate weighted average price
        for sym in result:
            if result[sym]['filled_qty'] > 0:
                result[sym]['avg_price'] = result[sym]['total_value'] / result[sym]['filled_qty']
        
        return result
    except Exception as e:
        logger.error(f"Error fetching today's orders: {e}")
        return {}


def initialize_tracker_from_orders(kite, symbols: list) -> tuple:
    """
    Initialize bought_tracker and actual_spent from today's existing orders.
    Enables idempotent re-runs - script resumes from where it left off.
    
    Returns: (bought_tracker dict, actual_spent dict)
    """
    bought_tracker = {}
    actual_spent = {'total': 0.0}
    
    if CONFIG.dry_run:
        return bought_tracker, actual_spent
    
    logger.info("ðŸ” Checking for existing orders from today...")
    
    todays_orders = get_todays_buy_orders(kite, symbols)
    
    if todays_orders:
        logger.info(f"ðŸ“‹ Found existing orders for {len(todays_orders)} symbols:")
        for sym, info in todays_orders.items():
            filled = info['filled_qty']
            pending = info['pending_qty']
            avg_price = info['avg_price']
            
            if filled > 0 or pending > 0:
                bought_tracker[sym] = filled
                actual_spent['total'] += info['total_value']
                status_str = f"filled={filled}"
                if pending > 0:
                    status_str += f", pending={pending}"
                logger.info(f"   {sym}: {status_str} @ â‚¹{avg_price:.2f}")
        
        logger.info(f"   Total already spent: â‚¹{actual_spent['total']:,.2f}")
    else:
        logger.info("   No existing orders found - starting fresh")
    
    return bought_tracker, actual_spent


def batch_fetch_ltp(kite, symbols):
    """
    Fetch LTP for multiple symbols in one API call to reduce rate limiting.
    Returns dict: {symbol: ltp}
    """
    if CONFIG.dry_run:
        return {}
    
    try:
        # Build instrument list
        instruments = [f"NSE:{sym}" for sym in symbols]
        ltp_data = with_backoff(kite.ltp, instruments)
        
        result = {}
        for sym in symbols:
            key = f"NSE:{sym}"
            if key in ltp_data:
                result[sym] = ltp_data[key]['last_price']
        return result
    except Exception as e:
        logger.error(f"Error fetching batch LTP: {e}")
        return {}


def update_order_book_prices(kite, filepath):
    """
    Fetch current LTP for all symbols in order book and update the CSV.
    Creates a backup before updating.
    """
    print("\n" + "=" * 60)
    print("ðŸ“Š UPDATING ORDER BOOK WITH CURRENT MARKET PRICES")
    print("=" * 60)
    
    try:
        # Read current CSV
        rows = []
        fieldnames = None
        with open(filepath, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        if not rows:
            print("âŒ No orders found in order book!")
            return
        
        # Get symbols
        symbols = [row['Symbol'].strip().upper() for row in rows]
        
        # Fetch LTP
        print(f"\nðŸ” Fetching LTP for {len(symbols)} symbols...")
        instruments = [f"NSE:{sym}" for sym in symbols]
        ltp_data = with_backoff(kite.ltp, instruments)
        
        # Update prices
        print(f"\n{'Symbol':<15} {'Old Price':>12} {'New Price':>12} {'Change':>10}")
        print("-" * 52)
        
        updated = 0
        for row in rows:
            symbol = row['Symbol'].strip().upper()
            key = f"NSE:{symbol}"
            old_price = float(row['Price'])
            
            if key in ltp_data:
                new_price = ltp_data[key]['last_price']
                change_pct = ((new_price - old_price) / old_price * 100) if old_price > 0 else 0
                change_str = f"{change_pct:+.1f}%"
                
                row['Price'] = f"{new_price:.2f}"
                print(f"{symbol:<15} {old_price:>12.2f} {new_price:>12.2f} {change_str:>10}")
                updated += 1
            else:
                print(f"{symbol:<15} {old_price:>12.2f} {'N/A':>12} {'SKIP':>10}")
        
        print("-" * 52)
        
        # Create backup
        backup_path = filepath.replace('.csv', '_backup.csv')
        shutil.copy(filepath, backup_path)
        print(f"\nðŸ’¾ Backup saved: {backup_path}")
        
        # Write updated CSV
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"âœ… Updated {updated}/{len(rows)} prices in {filepath}")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"âŒ Error updating prices: {e}")


def get_existing_gtts(kite):
    """
    Fetch all existing GTT orders for idempotency check.
    Returns set of (symbol, trigger_type) tuples that are already protected.
    """
    if CONFIG.dry_run:
        return set()
    
    try:
        gtts = with_backoff(kite.get_gtts)
        protected = set()
        for gtt in gtts:
            if gtt.get('status') == 'active':
                symbol = gtt.get('condition', {}).get('tradingsymbol', '')
                trigger_type = gtt.get('condition', {}).get('trigger_type', '')
                if symbol:
                    protected.add((symbol, trigger_type))
        return protected
    except Exception as e:
        logger.error(f"Error fetching GTTs: {e}")
        return set()


def get_existing_gtt_buy_symbols(kite) -> set:
    """Return symbols that already have an active GTT with a BUY leg."""
    if CONFIG.dry_run:
        return set()

    try:
        gtts = with_backoff(kite.get_gtts)
        symbols = set()
        for gtt in gtts:
            if gtt.get('status') != 'active':
                continue
            symbol = gtt.get('condition', {}).get('tradingsymbol', '')
            if not symbol:
                continue
            for order in gtt.get('orders', []) or []:
                if str(order.get('transaction_type', '')).upper() == 'BUY':
                    symbols.add(symbol)
                    break
        return symbols
    except Exception as e:
        logger.error(f"Error fetching GTT BUY symbols: {e}")
        return set()


def delete_existing_gtts(kite, symbols_to_refresh=None):
    """
    Delete existing GTT orders to allow recreation with updated SL/Target.
    
    Args:
        kite: KiteConnect client
        symbols_to_refresh: Set of symbols to refresh (None = all holdings)
    
    Returns:
        int: Number of GTTs deleted
    """
    try:
        gtts = with_backoff(kite.get_gtts)
        deleted_count = 0
        
        for gtt in gtts:
            if gtt.get('status') != 'active':
                continue
                
            symbol = gtt.get('condition', {}).get('tradingsymbol', '')
            trigger_id = gtt.get('id')
            
            if not symbol or not trigger_id:
                continue
            
            # If symbols specified, only delete those
            if symbols_to_refresh and symbol not in symbols_to_refresh:
                continue
            
            if CONFIG.dry_run:
                logger.info(f"[DRY RUN] Would delete GTT {trigger_id} for {symbol}")
                deleted_count += 1
            else:
                try:
                    with_backoff(kite.delete_gtt, trigger_id)
                    logger.info(f"Deleted GTT {trigger_id} for {symbol}")
                    deleted_count += 1
                    time.sleep(0.2)  # Rate limit
                except Exception as e:
                    logger.error(f"Failed to delete GTT {trigger_id} for {symbol}: {e}")
        
        return deleted_count
    except Exception as e:
        logger.error(f"Error fetching GTTs for deletion: {e}")
        return 0


def delete_existing_gtt_buys(kite, symbols_to_refresh=None) -> int:
    """
    Delete only BUY-side active GTT orders.

    This is safer than delete_existing_gtts() when used with --gtt-buy --refresh,
    because it will not delete SELL protection GTTs created via --protect.

    Args:
        kite: KiteConnect client
        symbols_to_refresh: optional set of symbols to limit deletion

    Returns:
        Number of BUY GTTs deleted.
    """
    try:
        gtts = with_backoff(kite.get_gtts)
        deleted_count = 0

        for gtt in gtts:
            if gtt.get('status') != 'active':
                continue

            symbol = gtt.get('condition', {}).get('tradingsymbol', '')
            trigger_id = gtt.get('id')

            if not symbol or not trigger_id:
                continue

            if symbols_to_refresh and symbol not in symbols_to_refresh:
                continue

            # Only delete if any leg is a BUY
            has_buy_leg = any(
                str(o.get('transaction_type', '')).upper() == 'BUY'
                for o in (gtt.get('orders', []) or [])
            )
            if not has_buy_leg:
                continue

            if CONFIG.dry_run:
                logger.info(f"[DRY RUN] Would delete BUY GTT {trigger_id} for {symbol}")
                deleted_count += 1
            else:
                try:
                    with_backoff(kite.delete_gtt, trigger_id)
                    logger.info(f"Deleted BUY GTT {trigger_id} for {symbol}")
                    deleted_count += 1
                    time.sleep(0.2)
                except Exception as e:
                    logger.error(f"Failed to delete BUY GTT {trigger_id} for {symbol}: {e}")

        return deleted_count
    except Exception as e:
        logger.error(f"Error fetching GTTs for BUY deletion: {e}")
        return 0


def cancel_open_limit_orders(kite, symbol: str):
    """
    Cancel any pending LIMIT BUY orders for a symbol.
    Prevents overbuy if previous tranche orders fill later.
    
    Uses negative status check to catch all pending states:
    OPEN, TRIGGER PENDING, PENDING, VALIDATION PENDING, PUT ORDER REQ RECEIVED, etc.
    """
    if CONFIG.dry_run:
        logger.info(f"[DRY RUN] Would cancel open LIMIT orders for {symbol}")
        return
    
    # Terminal states - orders in these states cannot be cancelled
    TERMINAL_STATES = {'COMPLETE', 'CANCELLED', 'REJECTED'}
    
    try:
        orders = with_backoff(kite.orders)
        for o in orders:
            status = o.get('status', '').upper()
            if (o.get('tradingsymbol') == symbol and
                status not in TERMINAL_STATES and
                o.get('order_type') == 'LIMIT' and
                o.get('transaction_type') == 'BUY'):
                try:
                    kite.cancel_order(
                        order_id=o['order_id'],
                        variety=o.get('variety', 'regular')
                    )
                    logger.info(f"Cancelled pending LIMIT order: {symbol} (ID: {o['order_id']}, status: {status})")
                except Exception as ce:
                    logger.warning(f"Failed to cancel {symbol} order {o.get('order_id')}: {ce}")
    except Exception as e:
        logger.error(f"Error iterating orders for {symbol}: {e}")


def get_pending_limit_buy_orders(kite) -> list:
    """Return currently open/pending LIMIT BUY orders with pending quantity."""
    # Terminal states - orders in these states cannot be modified/cancelled
    terminal_states = {'COMPLETE', 'CANCELLED', 'REJECTED'}

    try:
        orders = with_backoff(kite.orders)
        pending = []
        for o in orders:
            status = str(o.get('status', '')).upper()
            if status in terminal_states:
                continue
            if str(o.get('transaction_type', '')).upper() != 'BUY':
                continue
            if str(o.get('order_type', '')).upper() != 'LIMIT':
                continue

            pending_qty = int(o.get('pending_quantity', 0) or 0)
            filled_qty = int(o.get('filled_quantity', 0) or 0)
            total_qty = int(o.get('quantity', 0) or 0)
            if pending_qty <= 0:
                # Fallback
                pending_qty = max(0, total_qty - filled_qty)
            if pending_qty <= 0:
                continue

            pending.append(o)

        return pending
    except Exception as e:
        logger.error(f"Error fetching pending orders: {e}")
        return []


def reprice_pending_limit_buy_orders(kite, discount: float = 0.99) -> None:
    """
    Reprice all open/pending LIMIT BUY orders to (discount * current LTP).
    Tries modify_order; if that fails, cancels and recreates the order.
    """
    pending_orders = get_pending_limit_buy_orders(kite)
    if not pending_orders:
        print("\nNo pending LIMIT BUY orders found.")
        return

    # Fetch LTPs in batch
    instruments = []
    for o in pending_orders:
        exchange = str(o.get('exchange', 'NSE') or 'NSE').upper()
        symbol = str(o.get('tradingsymbol', '')).upper()
        if symbol:
            instruments.append(f"{exchange}:{symbol}")
    instruments = sorted(set(instruments))

    try:
        ltp_data = with_backoff(kite.ltp, instruments)
    except Exception as e:
        logger.error(f"Error fetching LTP for repricing: {e}")
        return

    print("\n" + "=" * 70)
    print(f"REPRICING PENDING LIMIT BUY ORDERS @ {discount:.2f}×LTP")
    print("=" * 70)
    print(f"\n{'Symbol':<15} {'Exch':<5} {'Pending':>7} {'OldPx':>10} {'LTP':>10} {'NewPx':>10} {'Action':>10}")
    print("-" * 75)

    for o in pending_orders:
        symbol = str(o.get('tradingsymbol', '')).upper()
        exchange = str(o.get('exchange', 'NSE') or 'NSE').upper()
        variety_str = str(o.get('variety', 'regular') or 'regular')
        order_id = o.get('order_id')
        old_price = float(o.get('price', 0) or 0)

        pending_qty = int(o.get('pending_quantity', 0) or 0)
        if pending_qty <= 0:
            pending_qty = max(0, int(o.get('quantity', 0) or 0) - int(o.get('filled_quantity', 0) or 0))

        key = f"{exchange}:{symbol}"
        ltp = float((ltp_data.get(key) or {}).get('last_price', 0) or 0)
        if ltp <= 0 or pending_qty <= 0 or not order_id:
            print(f"{symbol:<15} {exchange:<5} {pending_qty:>7} {old_price:>10.2f} {ltp:>10.2f} {'-':>10} {'SKIP':>10}")
            continue

        new_price = round_to_tick(ltp * float(discount))

        if CONFIG.dry_run:
            print(f"{symbol:<15} {exchange:<5} {pending_qty:>7} {old_price:>10.2f} {ltp:>10.2f} {new_price:>10.2f} {'DRY':>10}")
            continue

        # Live: try modify first
        try:
            with_backoff(
                kite.modify_order,
                variety=get_variety(kite, variety_str),
                order_id=order_id,
                quantity=pending_qty,
                price=new_price,
                order_type=kite.ORDER_TYPE_LIMIT,
            )
            print(f"{symbol:<15} {exchange:<5} {pending_qty:>7} {old_price:>10.2f} {ltp:>10.2f} {new_price:>10.2f} {'MODIFY':>10}")
            time.sleep(0.15)
            continue
        except Exception:
            pass

        # Fallback: cancel + recreate
        try:
            with_backoff(kite.cancel_order, order_id=order_id, variety=get_variety(kite, variety_str))
            time.sleep(0.15)
            new_order_id = with_backoff(
                kite.place_order,
                tradingsymbol=symbol,
                exchange=exchange,
                transaction_type=kite.TRANSACTION_TYPE_BUY,
                quantity=pending_qty,
                order_type=kite.ORDER_TYPE_LIMIT,
                product=get_product_type(kite, str(o.get('product', 'CNC') or 'CNC')),
                variety=get_variety(kite, variety_str),
                price=new_price,
            )
            print(f"{symbol:<15} {exchange:<5} {pending_qty:>7} {old_price:>10.2f} {ltp:>10.2f} {new_price:>10.2f} {'REPLACE':>10}")
            logger.info(f"Replaced order {order_id} -> {new_order_id} for {symbol}")
            time.sleep(0.2)
        except Exception as e:
            print(f"{symbol:<15} {exchange:<5} {pending_qty:>7} {old_price:>10.2f} {ltp:>10.2f} {new_price:>10.2f} {'FAIL':>10}")
            logger.error(f"Failed to reprice {symbol} ({order_id}): {e}")

    print("-" * 75)
    print("Done.")


REQUIRED_CSV_COLS = {'Symbol', 'Quantity', 'Price', 'Transaction', 'Variety', 'Product', 'Order_Type'}
VALID_PRODUCTS = {'CNC', 'MIS', 'NRML'}
VALID_ORDER_TYPES = {'MARKET', 'LIMIT', 'SL', 'SL-M'}


def read_order_book(filepath):
    """Read and validate orders from CSV file"""
    orders = []
    try:
        with open(filepath, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Validate required columns exist
            if not REQUIRED_CSV_COLS.issubset(reader.fieldnames or []):
                missing = REQUIRED_CSV_COLS - set(reader.fieldnames or [])
                logger.error(f"CSV missing required columns: {', '.join(missing)}")
                return []
            
            for i, row in enumerate(reader, start=2):  # header is line 1
                try:
                    # Validate transaction is BUY
                    transaction = str(row['Transaction']).strip().upper()
                    if transaction != 'BUY':
                        logger.warning(f"Skipping non-BUY row {i}: {row['Symbol']} ({transaction})")
                        continue
                    
                    # Parse and validate qty/price
                    qty = int(row['Quantity'])
                    price = float(row['Price'])
                    
                    if qty <= 0:
                        logger.warning(f"Skipping invalid quantity at row {i}: {row['Symbol']} (qty={qty})")
                        continue
                    if price <= 0:
                        logger.warning(f"Skipping invalid price at row {i}: {row['Symbol']} (price={price})")
                        continue
                    
                    # Validate variety (only supported ones)
                    variety = row['Variety'].strip().lower()
                    if variety not in ('regular', 'amo', 'iceberg'):
                        logger.warning(f"Row {i}: variety '{variety}' may not be supported, using 'regular'")
                        variety = 'regular'
                    
                    # Validate product type
                    product = row['Product'].strip().upper()
                    if product not in VALID_PRODUCTS:
                        logger.error(f"Row {i}: Invalid product '{product}'. Must be one of {VALID_PRODUCTS}")
                        continue
                    
                    # Validate order type
                    order_type = row['Order_Type'].strip().upper()
                    if order_type not in VALID_ORDER_TYPES:
                        logger.error(f"Row {i}: Invalid order_type '{order_type}'. Must be one of {VALID_ORDER_TYPES}")
                        continue
                    
                    orders.append({
                        'symbol': row['Symbol'].strip().upper(),
                        'quantity': qty,
                        'price': price,
                        'transaction': 'BUY',
                        'variety': variety,
                        'product': product,
                        'order_type': order_type,
                        'rank': row.get('Rank', '').strip() if 'Rank' in row else '',
                        'allocation': _safe_float(row.get('Allocation', ''), default=0.0),
                        'target_value': _safe_float(row.get('TargetValue', ''), default=0.0),
                    })
                except ValueError as ve:
                    logger.error(f"Parse error at row {i}: {ve} | {row}")
                except Exception as pe:
                    logger.error(f"Error at row {i}: {pe} | {row}")
        
        # Check for duplicate symbols
        symbols_seen = set()
        unique_orders = []
        for order in orders:
            if order['symbol'] in symbols_seen:
                logger.warning(f"Duplicate symbol '{order['symbol']}' found - keeping first occurrence")
            else:
                symbols_seen.add(order['symbol'])
                unique_orders.append(order)
        
        if len(unique_orders) < len(orders):
            logger.warning(f"Removed {len(orders) - len(unique_orders)} duplicate entries")
        
        return unique_orders
    except FileNotFoundError:
        logger.error(f"Order book file not found: {filepath}")
        return []
    except Exception as e:
        logger.error(f"Error reading order book: {e}")
        return []


def _safe_float(value, default: float = 0.0) -> float:
    """Parse float values from CSV fields (handles commas/empty)."""
    try:
        if value is None:
            return default
        s = str(value).strip().replace(',', '')
        if not s:
            return default
        return float(s)
    except Exception:
        return default


def _compute_qty_from_budget(ltp: float, budget: float, max_qty: int) -> int:
    """Compute quantity as floor(budget / ltp) with sensible guards."""
    if ltp <= 0 or budget <= 0:
        return 0
    qty = int(budget // ltp)
    qty = max(1, qty)
    if max_qty > 0:
        qty = min(qty, max_qty)
    return qty


def _is_top15_rank(rank: str) -> bool:
    """Return True if a CSV Rank value should be included in Top15 universe."""
    r = (rank or '').strip().upper()
    return r in {'TOP5', 'NEXT5', 'TOP10', 'TOP15'}


def get_product_type(kite, product_str):
    """Convert product string to Kite constant"""
    product_map = {
        'CNC': kite.PRODUCT_CNC,
        'MIS': kite.PRODUCT_MIS,
        'NRML': kite.PRODUCT_NRML
    }
    return product_map.get(product_str.upper(), kite.PRODUCT_CNC)


def get_order_type(kite, order_type_str):
    """Convert order type string to Kite constant"""
    order_type_map = {
        'MARKET': kite.ORDER_TYPE_MARKET,
        'LIMIT': kite.ORDER_TYPE_LIMIT,
        'SL': kite.ORDER_TYPE_SL,
        'SL-M': kite.ORDER_TYPE_SLM
    }
    return order_type_map.get(order_type_str.upper(), kite.ORDER_TYPE_LIMIT)


def get_variety(kite, variety_str):
    """Convert variety string to Kite constant"""
    variety_map = {
        'regular': kite.VARIETY_REGULAR,
        'amo': kite.VARIETY_AMO,
        'iceberg': kite.VARIETY_ICEBERG,
        'auction': kite.VARIETY_AUCTION
    }
    return variety_map.get(variety_str.lower(), kite.VARIETY_REGULAR)


def place_buy_order(kite, order) -> OrderResult:
    """Place buy order for a stock. Returns OrderResult with status."""
    try:
        order_params = {
            'tradingsymbol': order['symbol'],
            'exchange': 'NSE',
            'transaction_type': kite.TRANSACTION_TYPE_BUY,
            'quantity': order['quantity'],
            'order_type': get_order_type(kite, order['order_type']),
            'product': get_product_type(kite, order['product']),
            'variety': get_variety(kite, order['variety'])
        }
        
        # Add price for LIMIT orders (use tick-rounded price)
        if order['order_type'].upper() == 'LIMIT':
            order_params['price'] = round_to_tick(order['price'])
        
        total_value = order['quantity'] * order['price']
        
        if CONFIG.dry_run:
            logger.info(f"[DRY RUN] Would buy: {order['symbol']:15} x {order['quantity']:>4} @ â‚¹{order['price']:>8.2f} = â‚¹{total_value:>10.2f}")
            return OrderResult(success=True, dry_run=True)
        else:
            order_id = with_backoff(kite.place_order, **order_params)
            logger.info(f"Bought: {order['symbol']:15} x {order['quantity']:>4} @ â‚¹{order['price']:>8.2f} - Order ID: {order_id}")
            return OrderResult(success=True, dry_run=False, order_id=str(order_id))
            
    except Exception as e:
        logger.error(f"Error buying {order['symbol']}: {e}")
        return OrderResult(success=False, dry_run=CONFIG.dry_run, error=str(e))


def place_stop_loss_order(kite, symbol, quantity, buy_price, product='CNC'):
    """Place SL-M (Stop Loss Market) order"""
    try:
        trigger_price = round_to_tick(buy_price * (1 - STOP_LOSS_PERCENT))
        
        order_params = {
            'tradingsymbol': symbol,
            'exchange': 'NSE',
            'transaction_type': kite.TRANSACTION_TYPE_SELL,
            'quantity': quantity,
            'order_type': kite.ORDER_TYPE_SLM,  # Stop Loss Market
            'product': get_product_type(kite, product),
            'variety': kite.VARIETY_REGULAR,
            'trigger_price': trigger_price
        }
        
        if CONFIG.dry_run:
            logger.info(f"[DRY RUN] Would place SL-M: {symbol:15} x {quantity:>4} trigger @ â‚¹{trigger_price:>8.2f} ({STOP_LOSS_PERCENT*100:.1f}% below â‚¹{buy_price:.2f})")
            return True
        else:
            order_id = with_backoff(kite.place_order, **order_params)
            logger.info(f"SL-M placed: {symbol:15} x {quantity:>4} trigger @ â‚¹{trigger_price:.2f} - Order ID: {order_id}")
            return order_id
            
    except Exception as e:
        logger.error(f"Error placing SL for {symbol}: {e}")
        return None


def place_gtt_buy_order(kite, symbol, quantity, current_price, trigger_percent, product='CNC'):
    """
    Place GTT buy order - triggers when price drops to target level.
    Used for accumulating stocks on dips.
    
    Args:
        kite: Kite client
        symbol: Stock symbol (e.g., 'RELIANCE')
        quantity: Number of shares to buy
        current_price: Current market price (reference for trigger calculation)
        trigger_percent: Percentage below current price to trigger (e.g., 0.08 for 8%)
        product: 'CNC' for delivery, 'MIS' for intraday
    """
    try:
        if quantity <= 0:
            return True
        trigger_price = round_to_tick(current_price * (1 - trigger_percent))
        # Limit price slightly above trigger to ensure fill
        limit_price = round_to_tick(trigger_price * 1.005)  # 0.5% above trigger
        
        gtt_params = {
            'trigger_type': kite.GTT_TYPE_SINGLE,
            'tradingsymbol': symbol,
            'exchange': 'NSE',
            'trigger_values': [trigger_price],
            'last_price': round_to_tick(current_price),
            'orders': [{
                'transaction_type': kite.TRANSACTION_TYPE_BUY,
                'quantity': quantity,
                'order_type': kite.ORDER_TYPE_LIMIT,
                'product': get_product_type(kite, product),
                'price': limit_price
            }]
        }
        
        if CONFIG.dry_run:
            logger.info(f"[DRY RUN] Would place GTT BUY: {symbol:15} x {quantity:>4} trigger @ ₹{trigger_price:>8.2f} ({trigger_percent*100:.0f}% below ₹{current_price:.2f})")
            return True
        else:
            gtt_id = with_backoff(kite.place_gtt, **gtt_params)
            logger.info(f"✅ GTT BUY placed: {symbol:15} x {quantity:>4} trigger @ ₹{trigger_price:.2f} - GTT ID: {gtt_id}")
            return gtt_id
            
    except Exception as e:
        logger.error(f"❌ Error placing GTT BUY for {symbol}: {e}")
        return None


def place_gtt_buy_orders_for_stocks(kite, stocks_data):
    """
    Place GTT buy orders for multiple stocks at configured dip levels.
    
    Args:
        kite: Kite client
        stocks_data: List of dicts with 'symbol', 'quantity', 'ltp', 'product' keys.
                     If present, 'allocation' is used only for display.
    """
    print("\n" + "=" * 70)
    print("🛒 PLACING GTT BUY ORDERS (DIP ACCUMULATION)")
    print("=" * 70)
    print(f"\nStrategy: Buy on dips at -{GTT_BUY_LOWER_PERCENT*100:.0f}% and -{GTT_BUY_UPPER_PERCENT*100:.0f}% below current price")
    print(f"Quantity split: {GTT_BUY_QTY_LOWER*100:.0f}% at lower, {GTT_BUY_QTY_UPPER*100:.0f}% at upper trigger\n")
    
    show_alloc = any(('allocation' in s and (s.get('allocation') or 0) > 0) for s in stocks_data)
    if show_alloc:
        print(f"{'Symbol':<15} {'LTP':>10} {'Alloc':>10} {'Qty':>6} {'Product':>8} {'Lower Trig':>12} {'Lower Qty':>10} {'Upper Trig':>12} {'Upper Qty':>10}")
    else:
        print(f"{'Symbol':<15} {'LTP':>10} {'Qty':>6} {'Product':>8} {'Lower Trig':>12} {'Lower Qty':>10} {'Upper Trig':>12} {'Upper Qty':>10}")
    print("-" * 85)
    
    success_count = 0
    fail_count = 0
    
    for stock in stocks_data:
        symbol = stock['symbol']
        total_qty = stock['quantity']
        ltp = stock['ltp']
        product = stock.get('product', 'CNC')
        allocation = float(stock.get('allocation', 0.0) or 0.0)

        if total_qty <= 0:
            continue
        
        # Calculate quantities for each trigger level (sum must equal total_qty)
        qty_lower = int(total_qty * GTT_BUY_QTY_LOWER + 0.5)  # round-half-up
        qty_lower = max(1, min(qty_lower, total_qty))
        qty_upper = total_qty - qty_lower
        
        # Calculate trigger prices
        trigger_lower = round_to_tick(ltp * (1 - GTT_BUY_LOWER_PERCENT))
        trigger_upper = round_to_tick(ltp * (1 - GTT_BUY_UPPER_PERCENT))
        
        upper_qty_display = str(qty_upper) if qty_upper > 0 else "-"
        if show_alloc:
            alloc_display = f"₹{allocation:,.0f}" if allocation > 0 else "-"
            print(f"{symbol:<15} ₹{ltp:>9.2f} {alloc_display:>10} {total_qty:>6} {product:>8} ₹{trigger_lower:>11.2f} {qty_lower:>10} ₹{trigger_upper:>11.2f} {upper_qty_display:>10}")
        else:
            print(f"{symbol:<15} ₹{ltp:>9.2f} {total_qty:>6} {product:>8} ₹{trigger_lower:>11.2f} {qty_lower:>10} ₹{trigger_upper:>11.2f} {upper_qty_display:>10}")
        
        # Place GTT for lower trigger (first dip)
        result_lower = place_gtt_buy_order(kite, symbol, qty_lower, ltp, GTT_BUY_LOWER_PERCENT, product=product)
        
        # Place GTT for upper trigger (deeper dip)
        result_upper = True
        if qty_upper > 0:
            result_upper = place_gtt_buy_order(kite, symbol, qty_upper, ltp, GTT_BUY_UPPER_PERCENT, product=product)
        
        if result_lower and result_upper:
            success_count += 1
        else:
            fail_count += 1
        
        # Rate limiting
        if not CONFIG.dry_run:
            time.sleep(0.3)
    
    print("-" * 85)
    print(f"\n✅ GTT Buy orders placed for {success_count} stocks")
    if fail_count > 0:
        print(f"❌ Failed for {fail_count} stocks")
    print(f"\n⚠️  Note: Each stock uses 1-2 GTT slots (depending on quantity split)")
    print("   Zerodha limit: 100 active GTTs per account")


def place_gtt_stop_loss(kite, symbol, quantity, buy_price):
    """Place GTT (Good Till Triggered) stop loss - persists across sessions"""
    try:
        trigger_price = round_to_tick(buy_price * (1 - STOP_LOSS_PERCENT))
        
        # GTT single trigger for stop loss
        gtt_params = {
            'trigger_type': kite.GTT_TYPE_SINGLE,
            'tradingsymbol': symbol,
            'exchange': 'NSE',
            'trigger_values': [trigger_price],
            'last_price': round_to_tick(buy_price),
            'orders': [{
                'transaction_type': kite.TRANSACTION_TYPE_SELL,
                'quantity': quantity,
                'order_type': kite.ORDER_TYPE_MARKET,
                'product': kite.PRODUCT_CNC,
                'price': 0  # Market order
            }]
        }
        
        if CONFIG.dry_run:
            logger.info(f"[DRY RUN] Would place GTT: {symbol:15} x {quantity:>4} trigger @ â‚¹{trigger_price:>8.2f} ({STOP_LOSS_PERCENT*100:.1f}% below â‚¹{buy_price:.2f})")
            return True
        else:
            gtt_id = with_backoff(kite.place_gtt, **gtt_params)
            logger.info(f"GTT placed: {symbol:15} x {quantity:>4} trigger @ â‚¹{trigger_price:.2f} - GTT ID: {gtt_id}")
            return gtt_id
            
    except Exception as e:
        logger.error(f"Error placing GTT for {symbol}: {e}")
        return None


def place_gtt_oco(kite, symbol, quantity, buy_price, product='CNC'):
    """Sets both Stop Loss and Profit Target for CNC holdings (OCO - One Cancels Other)"""
    try:
        # 1. Calculate Prices with tick-aware rounding
        sl_trigger = round_to_tick(buy_price * (1 - STOP_LOSS_PERCENT))
        # EXECUTION GAP: In volatile/war scenarios prices can jump rapidly
        # Setting sl_limit below trigger ensures order fills even in fast-falling markets
        sl_limit = round_to_tick(sl_trigger * (1 - SL_EXECUTION_BUFFER))
        
        target_trigger = round_to_tick(buy_price * (1 + TARGET_PERCENT))
        target_limit = round_to_tick(target_trigger)
        
        # 2. Define the Two Legs
        oco_orders = [
            {  # Leg 1: Stop Loss
                "exchange": "NSE",
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                "quantity": quantity,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "product": kite.PRODUCT_CNC,
                "price": sl_limit
            },
            {  # Leg 2: Profit Target
                "exchange": "NSE",
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                "quantity": quantity,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "product": kite.PRODUCT_CNC,
                "price": target_limit
            }
        ]
        
        if CONFIG.dry_run:
            logger.info(f"[DRY RUN] OCO for {symbol:15} x {quantity:>4} | SL: â‚¹{sl_trigger:>8.2f} ({STOP_LOSS_PERCENT*100:.0f}% â†“) | Target: â‚¹{target_trigger:>8.2f} ({TARGET_PERCENT*100:.0f}% â†‘)")
            return True
        else:
            gtt_id = with_backoff(
                kite.place_gtt,
                trigger_type=kite.GTT_TYPE_OCO,
                tradingsymbol=symbol,
                exchange="NSE",
                trigger_values=[sl_trigger, target_trigger],
                last_price=round_to_tick(buy_price),
                orders=oco_orders
            )
            logger.info(f"âœ… GTT OCO Set for {symbol} (SL: â‚¹{sl_trigger}, Target: â‚¹{target_trigger}) - GTT ID: {gtt_id}")
            return gtt_id

    except Exception as e:
        logger.error(f"âŒ OCO Error for {symbol}: {e}")
        return None


def place_stop_loss(kite, symbol, quantity, buy_price, product='CNC'):
    """Place stop loss based on configuration (OCO, GTT, or SL-M)"""
    if not STOP_LOSS_ENABLED:
        return None
    
    if USE_GTT and USE_OCO:
        return place_gtt_oco(kite, symbol, quantity, buy_price, product)
    elif USE_GTT:
        return place_gtt_stop_loss(kite, symbol, quantity, buy_price)
    else:
        return place_stop_loss_order(kite, symbol, quantity, buy_price, product)


def protect_existing_holdings(kite, sl_pct=None, target_pct=None):
    """
    Sweeps all CNC holdings and sets GTT OCO (Target + SL) orders.
    Uses average_price as base for SL/Target calculations.
    Uses last_price (current market price) for GTT last_price parameter.
    
    Includes idempotency check - skips symbols that already have active GTTs.
    
    âš ï¸  Requires TPIN authorization at 9:00 AM to execute.
    
    Args:
        kite: Kite client
        sl_pct: Stop loss percentage (default: uses STOP_LOSS_PERCENT from config)
        target_pct: Target percentage (default: uses TARGET_PERCENT from config)
    """
    # Use config values if not specified
    sl_pct = sl_pct or STOP_LOSS_PERCENT
    target_pct = target_pct or TARGET_PERCENT
    
    print("\n" + "=" * 60)
    print("ðŸ›¡ï¸  SECURING ENTIRE PORTFOLIO WITH GTT OCO")
    print("=" * 60)
    
    try:
        # Idempotency check: fetch existing GTTs
        existing_gtts = get_existing_gtts(kite)
        already_protected = {sym for sym, _ in existing_gtts}
        
        holdings = kite.holdings()
        
        # Filter holdings with quantity > 0
        active_holdings = [h for h in holdings if h['quantity'] > 0]
        
        if not active_holdings:
            print("âŒ No holdings found to protect!")
            return
        
        logger.info(f"ðŸ›¡ï¸ Found {len(active_holdings)} holdings. Initializing OCO protection...")
        
        print(f"\n{'Symbol':<15} {'Qty':>6} {'Avg Price':>10} {'LTP':>10} {'SL':>10} {'Target':>10} {'Status':<10}")
        print("-" * 80)
        
        protected = 0
        skipped = 0
        trailing_count = 0
        hit_sl = 0
        
        for stock in active_holdings:
            symbol = stock['tradingsymbol']
            qty = stock['quantity']
            avg_price = stock['average_price']
            current_price = stock.get('last_price', avg_price)  # Fallback if last_price missing
            
            # Check if already protected (idempotency)
            if symbol in already_protected:
                print(f"{symbol:<15} {qty:>6} {avg_price:>10.2f} {current_price:>10.2f} {'-':>10} {'-':>10} {'SKIP':>10}")
                skipped += 1
                continue
            
            # Calculate base price - use LTP if already above original target (trailing stop)
            original_target = avg_price * (1 + target_pct)
            if current_price >= original_target:
                base_price = current_price
                is_trailing = True
                gain_pct = ((current_price - avg_price) / avg_price) * 100
            else:
                base_price = avg_price
                is_trailing = False
            
            # Calculate SL and Target from base price
            sl_trigger = round_to_tick(base_price * (1 - sl_pct))
            sl_limit = round_to_tick(sl_trigger * (1 - SL_EXECUTION_BUFFER))
            target_trigger = round_to_tick(base_price * (1 + target_pct))
            target_limit = round_to_tick(target_trigger)
            
            # GTT OCO requires: sl_trigger < current_price < target_trigger
            if current_price <= sl_trigger:
                loss_pct = ((avg_price - current_price) / avg_price) * 100
                print(f"{symbol:<15} {qty:>6} {avg_price:>10.2f} {current_price:>10.2f} {sl_trigger:>10.2f} {target_trigger:>10.2f} {'HIT-':>10}")
                logger.info(f"   {symbol}: LTP â‚¹{current_price:.2f} already below SL â‚¹{sl_trigger:.2f} (-{loss_pct:.1f}% loss)")
                hit_sl += 1
                continue
            
            print(f"{symbol:<15} {qty:>6} {avg_price:>10.2f} {current_price:>10.2f} {sl_trigger:>10.2f} {target_trigger:>10.2f}", end="")
            
            # Define OCO legs
            oco_orders = [
                {  # Leg 1: Stop Loss
                    "exchange": "NSE",
                    "tradingsymbol": symbol,
                    "transaction_type": kite.TRANSACTION_TYPE_SELL,
                    "quantity": qty,
                    "order_type": kite.ORDER_TYPE_LIMIT,
                    "product": kite.PRODUCT_CNC,
                    "price": sl_limit
                },
                {  # Leg 2: Profit Target
                    "exchange": "NSE",
                    "tradingsymbol": symbol,
                    "transaction_type": kite.TRANSACTION_TYPE_SELL,
                    "quantity": qty,
                    "order_type": kite.ORDER_TYPE_LIMIT,
                    "product": kite.PRODUCT_CNC,
                    "price": target_limit
                }
            ]
            
            if CONFIG.dry_run:
                trail_mark = " T" if is_trailing else ""
                print(f" {'DRY'+trail_mark:>10}")
                if is_trailing:
                    logger.info(f"ðŸ” [DRY RUN] TRAILING OCO for {symbol:10} | Base: â‚¹{base_price:.2f} (LTP) | SL: â‚¹{sl_trigger} | Tgt: â‚¹{target_trigger} | +{gain_pct:.1f}% locked")
                    trailing_count += 1
                else:
                    logger.info(f"ðŸ” [DRY RUN] OCO for {symbol:10} | SL: â‚¹{sl_trigger} | Tgt: â‚¹{target_trigger}")
                protected += 1
            else:
                try:
                    gtt_id = with_backoff(
                        kite.place_gtt,
                        trigger_type=kite.GTT_TYPE_OCO,
                        tradingsymbol=symbol,
                        exchange="NSE",
                        trigger_values=[sl_trigger, target_trigger],
                        last_price=round_to_tick(current_price),  # Use current market price
                        orders=oco_orders
                    )
                    trail_mark = " T" if is_trailing else ""
                    print(f" {'âœ“'+trail_mark:>10}")
                    if is_trailing:
                        logger.info(f"âœ… TRAILING GTT: {symbol:10} | Base: â‚¹{base_price:.2f} (LTP) | SL: {sl_trigger} | Tgt: {target_trigger} | ID: {gtt_id}")
                        trailing_count += 1
                    else:
                        logger.info(f"âœ… GTT OCO Active: {symbol:10} | SL: {sl_trigger} | Tgt: {target_trigger} | ID: {gtt_id}")
                    protected += 1
                except Exception as e:
                    print(f" {'FAIL':>10}")
                    logger.error(f"âŒ OCO failed for {symbol}: {e}")
        
        print("-" * 80)
        print(f"\nâœ… Protected {protected}/{len(active_holdings)} holdings with GTT OCO")
        if skipped > 0:
            print(f"â­ï¸  Skipped {skipped} symbols (already have active GTT)")
        if trailing_count > 0:
            print(f"ðŸ“ˆ {trailing_count} stocks using TRAILING SL (based on LTP, locking profits)")
        if hit_sl > 0:
            print(f"âš ï¸  {hit_sl} stocks already below SL (HIT-) - consider exiting")
        print(f"   Stop Loss: {sl_pct*100:.0f}% below base price (with {SL_EXECUTION_BUFFER*100:.0f}% execution buffer)")
        print(f"   Target: {target_pct*100:.0f}% above base price")
        print("   T = Trailing (SL/Target based on LTP, not avg price)")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"âŒ Failed to secure portfolio: {e}")


def protect_existing_holdings_sliced(kite, slices=None):
    """
    Sliced GTT OCO - Creates multiple GTTs per stock with graduated SL/Target levels.
    
    This allows partial profit booking before target and partial SL exits.
    
    Example with default slices:
    - Slice 1 (30%): SL -5%, Target +10%  â†’ Book early profits, tight stop
    - Slice 2 (40%): SL -8%, Target +15%  â†’ Moderate risk/reward
    - Slice 3 (30%): SL -10%, Target +20% â†’ Let winners run
    
    If stock rises 10%: 30% is sold, remaining 70% continues
    If stock falls 5%: Only 30% is sold at -5%, rest has wider stop
    
    âš ï¸  Each slice = 1 GTT. Zerodha limit = 100 GTTs per account.
    """
    slices = slices or GTT_SLICES
    
    print("\n" + "=" * 70)
    print("ðŸŽšï¸  SLICED GTT OCO - GRADUATED SL/TARGET PROTECTION")
    print("=" * 70)
    
    # Display slice configuration
    print("\nðŸ“Š Slice Configuration:")
    for i, (qty_pct, sl_pct, target_pct) in enumerate(slices, 1):
        print(f"   Slice {i}: {qty_pct*100:.0f}% qty | SL -{sl_pct*100:.0f}% | Target +{target_pct*100:.0f}%")
    print()
    
    try:
        # Fetch existing GTTs for idempotency
        existing_gtts = get_existing_gtts(kite)
        existing_symbols = {sym for sym, _ in existing_gtts}
        
        holdings = kite.holdings()
        active_holdings = [h for h in holdings if h['quantity'] > 0]
        
        if not active_holdings:
            print("âŒ No holdings found to protect!")
            return
        
        # Calculate total GTTs needed
        total_gtts_needed = len(active_holdings) * len(slices)
        print(f"ðŸ“ˆ Holdings: {len(active_holdings)} stocks")
        print(f"ðŸ“Š GTTs needed: {total_gtts_needed} ({len(active_holdings)} Ã— {len(slices)} slices)")
        print(f"âš ï¸  Zerodha limit: 100 GTTs/account")
        
        if total_gtts_needed > 100:
            print(f"\nâš ï¸  WARNING: {total_gtts_needed} GTTs exceeds limit!")
            print("   Consider reducing slices or stocks.")
        
        print(f"\n{'Symbol':<12} {'Qty':>5} {'Slice':>6} {'SliceQty':>8} {'SL%':>5} {'SLâ‚¹':>8} {'Tgt%':>5} {'Tgtâ‚¹':>8} {'Status':>8}")
        print("-" * 85)
        
        total_created = 0
        total_skipped = 0
        
        for stock in active_holdings:
            symbol = stock['tradingsymbol']
            total_qty = stock['quantity']
            avg_price = stock['average_price']
            current_price = stock.get('last_price', avg_price)
            
            # Skip if already has GTTs (avoid duplicates)
            if symbol in existing_symbols:
                print(f"{symbol:<12} {total_qty:>5} {'ALL':>6} {'-':>8} {'-':>5} {'-':>8} {'-':>5} {'-':>8} {'SKIP':>8}")
                total_skipped += 1
                continue
            
            qty_remaining = total_qty
            
            for slice_num, (qty_pct, sl_pct, target_pct) in enumerate(slices, 1):
                # Calculate quantity for this slice
                if slice_num == len(slices):
                    # Last slice gets remaining qty (handles rounding)
                    slice_qty = qty_remaining
                else:
                    slice_qty = max(1, int(total_qty * qty_pct))
                    slice_qty = min(slice_qty, qty_remaining)
                
                if slice_qty <= 0:
                    continue
                
                qty_remaining -= slice_qty
                
                # Calculate base price for SL/Target
                # If stock already moved past original target, use LTP as new base (trailing stop)
                original_target = avg_price * (1 + target_pct)
                
                if current_price >= original_target:
                    # Stock in significant profit - use LTP as base to lock in gains
                    base_price = current_price
                    is_trailing = True
                    gain_pct = ((current_price - avg_price) / avg_price) * 100
                else:
                    # Stock within normal range - use avg_price
                    base_price = avg_price
                    is_trailing = False
                
                # Calculate SL and Target from base price
                sl_trigger = round_to_tick(base_price * (1 - sl_pct))
                sl_limit = round_to_tick(sl_trigger * (1 - SL_EXECUTION_BUFFER))
                target_trigger = round_to_tick(base_price * (1 + target_pct))
                target_limit = round_to_tick(target_trigger)
                
                # GTT OCO requires: sl_trigger < current_price < target_trigger
                # After rebasing on LTP, this should always be valid
                if current_price >= target_trigger:
                    # Edge case: shouldn't happen after rebasing, but handle it
                    print(f"{symbol:<12} {total_qty:>5} {slice_num:>6} {slice_qty:>8} {-sl_pct*100:>5.0f}% {sl_trigger:>8.2f} {target_pct*100:>5.0f}% {target_trigger:>8.2f} {'EDGE':>8}")
                    continue
                
                if current_price <= sl_trigger:
                    loss_pct = ((avg_price - current_price) / avg_price) * 100
                    print(f"{symbol:<12} {total_qty:>5} {slice_num:>6} {slice_qty:>8} {-sl_pct*100:>5.0f}% {sl_trigger:>8.2f} {target_pct*100:>5.0f}% {target_trigger:>8.2f} {'HIT-':>8}")
                    logger.info(f"   {symbol} slice {slice_num}: LTP â‚¹{current_price:.2f} already below SL â‚¹{sl_trigger:.2f} (-{loss_pct:.1f}% loss)")
                    continue
                
                # Show trailing indicator
                status_suffix = "T" if is_trailing else ""
                print(f"{symbol:<12} {total_qty:>5} {slice_num:>6} {slice_qty:>8} {-sl_pct*100:>5.0f}% {sl_trigger:>8.2f} {target_pct*100:>5.0f}% {target_trigger:>8.2f}", end="")
                
                # Define OCO legs for this slice
                oco_orders = [
                    {  # Stop Loss leg
                        "exchange": "NSE",
                        "tradingsymbol": symbol,
                        "transaction_type": kite.TRANSACTION_TYPE_SELL,
                        "quantity": slice_qty,
                        "order_type": kite.ORDER_TYPE_LIMIT,
                        "product": kite.PRODUCT_CNC,
                        "price": sl_limit
                    },
                    {  # Target leg
                        "exchange": "NSE",
                        "tradingsymbol": symbol,
                        "transaction_type": kite.TRANSACTION_TYPE_SELL,
                        "quantity": slice_qty,
                        "order_type": kite.ORDER_TYPE_LIMIT,
                        "product": kite.PRODUCT_CNC,
                        "price": target_limit
                    }
                ]
                
                if CONFIG.dry_run:
                    trail_mark = " T" if is_trailing else ""
                    print(f" {'DRY'+trail_mark:>8}")
                    if is_trailing:
                        logger.info(f"   {symbol} slice {slice_num}: TRAILING from LTP â‚¹{current_price:.2f} (+{gain_pct:.1f}% profit locked)")
                    total_created += 1
                else:
                    try:
                        gtt_id = with_backoff(
                            kite.place_gtt,
                            trigger_type=kite.GTT_TYPE_OCO,
                            tradingsymbol=symbol,
                            exchange="NSE",
                            trigger_values=[sl_trigger, target_trigger],
                            last_price=round_to_tick(current_price),
                            orders=oco_orders
                        )
                        trail_mark = " T" if is_trailing else ""
                        print(f" {'âœ“'+trail_mark:>8}")
                        total_created += 1
                        if is_trailing:
                            logger.info(f"GTT {gtt_id}: {symbol} slice {slice_num} TRAILING from â‚¹{current_price:.2f} SL={sl_trigger} Tgt={target_trigger}")
                        else:
                            logger.info(f"GTT {gtt_id}: {symbol} slice {slice_num} ({slice_qty} qty) SL={sl_trigger} Tgt={target_trigger}")
                    except Exception as e:
                        print(f" {'FAIL':>8}")
                        logger.error(f"GTT failed for {symbol} slice {slice_num}: {e}")
        
        print("-" * 85)
        print(f"\nâœ… Created {total_created} sliced GTT OCOs")
        if total_skipped > 0:
            print(f"â­ï¸  Skipped {total_skipped} stocks (already have GTTs)")
        print("\nï¿½ Status Legend:")
        print("   HIT+ = Stock already above target (consider booking profits)")
        print("   HIT- = Stock already below SL (consider exiting)")
        print("   SKIP = Already has GTT protection")
        print("\nï¿½ðŸ’¡ How slicing works:")
        print("   â€¢ If price hits Slice 1 target (+10%), only 30% is sold")
        print("   â€¢ Remaining 70% continues to run for higher targets")
        print("   â€¢ If price drops to Slice 1 SL (-5%), only 30% exits")
        print("   â€¢ Remaining 70% has wider stop loss buffer")
        print("=" * 70)
        
    except Exception as e:
        logger.error(f"âŒ Failed to create sliced GTTs: {e}")




def find_new_stocks(kite, research_file="data/research_data.csv"):
    """
    Compare research_data.csv with current holdings to find NEW stocks.
    
    Returns:
        tuple: (new_stocks list, existing_symbols set)
        - new_stocks: List of stock dicts from research file not in holdings
        - existing_symbols: Set of symbols already in holdings
    """
    print("\n" + "=" * 70)
    print("SCANNING FOR NEW STOCKS IN RESEARCH DATA")
    print("=" * 70)
    
    try:
        # Get current holdings
        holdings = with_backoff(kite.holdings)
        existing_symbols = {h['tradingsymbol'] for h in holdings if h['quantity'] > 0}
        print(f"\nCurrent Holdings: {len(existing_symbols)} stocks")
        
        # Read research data
        research_stocks = read_order_book(research_file)
        if not research_stocks:
            print(f"No stocks found in {research_file}")
            return [], existing_symbols
        
        research_symbols = {s['symbol'] for s in research_stocks}
        print(f"Research Data: {len(research_symbols)} stocks")
        
        # Find new stocks (in research but not in holdings)
        new_symbols = research_symbols - existing_symbols
        new_stocks = [s for s in research_stocks if s['symbol'] in new_symbols]
        
        # Find overlapping stocks
        overlap_symbols = research_symbols & existing_symbols
        
        print(f"\nAlready Own: {len(overlap_symbols)} stocks")
        print(f"New Stocks: {len(new_symbols)} stocks")
        
        if new_stocks:
            print(f"\n{'Symbol':<15} {'Price':>10} {'Rank':<10}")
            print("-" * 40)
            for stock in new_stocks:
                rank = stock.get('rank', 'N/A')
                print(f"{stock['symbol']:<15} {stock['price']:>10.2f} {rank:<10}")
            print("-" * 40)
        
        return new_stocks, existing_symbols
        
    except Exception as e:
        logger.error(f"Error finding new stocks: {e}")
        return [], set()


def buy_new_stocks(kite, research_file="data/research_data.csv"):
    """
    Buy 1 share each of NEW stocks from research_data.csv (Phase 1 only).
    
    Compares research_data.csv with current holdings and places MARKET orders
    for stocks not already owned.
    
    Includes idempotency check - skips stocks with orders already placed today.
    
    Returns:
        int: Number of orders placed
    """
    # Find new stocks
    new_stocks, existing_symbols = find_new_stocks(kite, research_file)
    
    if not new_stocks:
        print("\nNo new stocks to buy - portfolio already contains all research stocks!")
        return 0
    
    # Check for today's existing orders (idempotency)
    symbols = [s['symbol'] for s in new_stocks]
    todays_orders = get_todays_buy_orders(kite, symbols)
    
    if todays_orders:
        print(f"\nFound {len(todays_orders)} stocks with orders already placed today:")
        for sym in todays_orders:
            print(f"   {sym}: {todays_orders[sym]['filled_qty']} filled, {todays_orders[sym]['pending_qty']} pending")
    
    # Filter out stocks that already have orders today
    stocks_to_buy = [s for s in new_stocks if s['symbol'] not in todays_orders]
    skipped_count = len(new_stocks) - len(stocks_to_buy)
    
    if not stocks_to_buy:
        print("\nAll new stocks already have orders placed today - nothing to do!")
        return 0
    
    print("\n" + "=" * 70)
    print("PHASE 1: BUYING NEW STOCKS (1 share each @ MARKET)")
    print("=" * 70)
    
    if skipped_count > 0:
        print(f"\nSkipping {skipped_count} stocks (orders already placed today)")
    
    # Fetch current LTP for stocks to buy
    buy_symbols = [s['symbol'] for s in stocks_to_buy]
    ltp_cache = batch_fetch_ltp(kite, buy_symbols)
    
    print(f"\n{'Symbol':<15} {'LTP':>10} {'Status':>10}")
    print("-" * 40)
    
    orders_placed = 0
    total_cost = 0.0
    
    for stock in stocks_to_buy:
        symbol = stock['symbol']
        
        # Get current LTP
        ltp = ltp_cache.get(symbol, stock['price'])
        
        base_order = {
            'symbol': symbol,
            'quantity': 1,
            'order_type': 'MARKET',
            'product': stock['product'],
            'variety': stock['variety'],
            'price': ltp
        }
        
        result = place_buy_order(kite, base_order)
        
        if result.success:
            status = "DRY" if result.dry_run else "OK"
            print(f"{symbol:<15} {ltp:>10.2f} {status:>10}")
            orders_placed += 1
            total_cost += ltp
        else:
            print(f"{symbol:<15} {ltp:>10.2f} {'FAIL':>10}")
            logger.error(f"Failed to buy {symbol}: {result.error}")
    
    print("-" * 40)
    print(f"\nPlaced {orders_placed}/{len(stocks_to_buy)} orders")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} stocks (already ordered today)")
    print(f"Estimated cost: Rs.{total_cost:,.2f}")
    
    if orders_placed > 0 and not CONFIG.dry_run:
        print("\nTIP: Run '--protect' later to set GTT OCO for new holdings")
    
    print("=" * 70)
    
    return orders_placed

def run_base_price_orders(kite, stocks, bought_tracker, actual_spent: dict):
    """
    9:15 AM - Buy 1 share of each at MARKET price.
    Waits for fill and uses actual execution price for stop loss.
    Tracks actual spent amount for real-time budget monitoring.
    
    Args:
        kite: Kite client
        stocks: List of stock orders from CSV
        bought_tracker: Dict to track quantities bought per symbol
        actual_spent: Dict with 'total' key tracking actual money spent
    
    Returns:
        Number of orders placed
    """
    logger.info("="*60)
    logger.info("ðŸš€ PHASE 1: BASE PRICE RUN (1 share each @ MARKET)")
    logger.info("="*60)
    
    orders_placed = 0
    sl_placed = 0
    
    for stock in stocks:
        # Kill switch check
        if is_kill_switch_on():
            print("ðŸ›‘ Kill switch engaged. Halting further orders.")
            break
        
        symbol = stock['symbol']
        base_order = {
            'symbol': symbol,
            'quantity': 1,
            'order_type': 'MARKET',
            'product': stock['product'],
            'variety': stock['variety'],
            'price': stock['price']  # For logging only (CSV price)
        }
        
        result = place_buy_order(kite, base_order)
        
        if result.success:
            orders_placed += 1
            
            # Track bought quantity
            if symbol not in bought_tracker:
                bought_tracker[symbol] = 0
            
            # Get actual fill details
            fill_price = stock['price']  # Default to CSV price
            filled_qty = 1
            
            if not result.dry_run and result.order_id:
                # Wait for order completion and get actual fill
                fill_info = wait_for_order_completion(kite, result.order_id, symbol)
                if fill_info and fill_info.get('status') == 'COMPLETE':
                    filled_qty = fill_info.get('filled_quantity', 1)
                    fill_price = fill_info.get('average_price', stock['price'])
                    logger.info(f"   â†’ {symbol} filled: {filled_qty} @ â‚¹{fill_price:.2f}")
                elif fill_info and fill_info.get('filled_quantity', 0) == 0:
                    logger.warning(f"   â†’ {symbol} order not filled, skipping SL")
                    continue
            
            bought_tracker[symbol] += filled_qty
            
            # Track actual spent (real-time budget guard)
            actual_spent['total'] += filled_qty * fill_price
            
            # Place stop loss using ACTUAL fill price, not CSV price
            if STOP_LOSS_ENABLED and filled_qty > 0:
                sl_result = place_stop_loss(kite, symbol, filled_qty, fill_price, stock['product'])
                if sl_result:
                    sl_placed += 1
    
    logger.info(f"\nâœ… Base price orders: {orders_placed}/{len(stocks)}")
    if STOP_LOSS_ENABLED:
        sl_label = "OCO (SL+Target)" if USE_GTT and USE_OCO else "Stop losses"
        logger.info(f"ðŸ›¡ï¸  {sl_label} placed: {sl_placed}/{orders_placed}")
    return orders_placed


def calculate_budget_allocation(total_stocks: int, tranche_num: int) -> dict:
    """
    Calculate budget allocation for a tranche.
    
    Per-Stock Limits:
    - PER_STOCK_DAILY_BUDGET: Max â‚¹1L per stock per day
    - MAX_QTY_PER_STOCK: Max 500 shares per stock
    - Phase 1 gets 1 share each, remaining budget split across tranches
    
    Returns:
        {
            'tranche_budget': total budget for this tranche (all stocks combined),
            'per_stock_budget': budget per stock for this tranche,
            'per_stock_tranche_budget': per-stock limit for this tranche,
            'mode': 'budget'
        }
    """
    if not CONFIG.use_budget_mode or CONFIG.daily_budget <= 0:
        return {'mode': 'quantity'}  # Fall back to quantity-based

    # Base budget: Phase 1 is 1 share each (approx sum of LTPs)
    base_budget = CONFIG.base_budget_actual if CONFIG.base_budget_actual > 0 else (CONFIG.daily_budget * BASE_BUDGET_PERCENT)
    base_budget = min(base_budget, CONFIG.daily_budget)

    remaining_budget = max(0.0, CONFIG.daily_budget - base_budget)

    # Split remaining budget equally across TRANCHE_COUNT tranches and symbols
    tranche_budget_total = remaining_budget / TRANCHE_COUNT if TRANCHE_COUNT > 0 else 0.0
    per_stock_budget = tranche_budget_total / total_stocks if total_stocks > 0 else 0.0

    # Per-stock cap per tranche (so a single stock can't dominate the day)
    per_stock_cap_per_tranche = (CONFIG.per_stock_daily_budget / TRANCHE_COUNT) if TRANCHE_COUNT > 0 else CONFIG.per_stock_daily_budget
    per_stock_tranche_budget = min(per_stock_budget, per_stock_cap_per_tranche)

    effective_tranche_budget = per_stock_tranche_budget * total_stocks

    return {
        'mode': 'budget',
        'tranche_budget': effective_tranche_budget,
        'per_stock_budget': per_stock_tranche_budget,
        'per_stock_tranche_budget': per_stock_tranche_budget,
        'base_budget': base_budget,
        'remaining_daily': CONFIG.daily_budget - (base_budget + tranche_num * effective_tranche_budget)
    }


def run_tranche_orders(kite, stocks, tranche_num, bought_tracker, tranches_remaining, actual_spent: dict):
    """
    Execute one tranche - buy portion of remaining qty at LIMIT price.
    
    In BUDGET MODE: Calculates quantity based on budget allocation per stock.
    In QUANTITY MODE: Uses CSV quantities divided by remaining tranches.
    
    Uses batch LTP and tracks actual fills.
    Syncs with broker holdings for accurate position tracking.
    
    Args:
        kite: Kite client
        stocks: List of stock orders from CSV
        tranche_num: Current tranche number (1-4)
        bought_tracker: Dict tracking quantities already bought per symbol
        tranches_remaining: Number of tranches left including this one
        actual_spent: Dict with 'total' key tracking actual money spent
    
    Returns:
        Number of orders placed
    """
    # Calculate budget allocation for this tranche
    budget_info = calculate_budget_allocation(len(stocks), tranche_num)
    
    logger.info("="*60)
    logger.info(f"â³ TRANCHE {tranche_num}/{TRANCHE_COUNT} ({tranche_num * 25}% cumulative)")
    logger.info(f"   Time: {datetime.now().strftime('%H:%M:%S')}")
    if budget_info['mode'] == 'budget':
        logger.info(f"   Budget: â‚¹{budget_info['tranche_budget']:,.0f} (â‚¹{budget_info['per_stock_budget']:,.0f}/stock)")
    logger.info("="*60)
    
    # Batch fetch LTP for all symbols to reduce API calls
    symbols = [s['symbol'] for s in stocks]
    ltp_cache = batch_fetch_ltp(kite, symbols)
    
    # Sync with broker holdings for accurate position tracking (handles late LIMIT fills)
    actual_holdings = get_actual_holdings(kite, symbols)
    if actual_holdings:
        for sym, actual_qty in actual_holdings.items():
            if sym in bought_tracker and actual_qty > bought_tracker[sym]:
                logger.info(f"   â†”ï¸ Syncing {sym}: tracker={bought_tracker[sym]} -> broker={actual_qty}")
                bought_tracker[sym] = actual_qty
    
    orders_placed = 0
    sl_placed = 0
    
    for stock in stocks:
        # Kill switch check
        if is_kill_switch_on():
            logger.warning("ðŸ›‘ Kill switch activated! Stopping tranche orders.")
            break
        
        symbol = stock['symbol']
        total_qty = stock['quantity']
        already_bought = bought_tracker.get(symbol, 0)
        
        # Calculate remaining qty to buy (total - already bought)
        qty_left = total_qty - already_bought
        
        if qty_left <= 0:
            continue
        
        # Cancel any pending LIMIT orders for this symbol before placing new ones
        if not CONFIG.dry_run:
            cancel_open_limit_orders(kite, symbol)
        
        # Get LTP from cache or fallback (need it for budget-based qty calculation)
        try:
            if CONFIG.dry_run:
                ltp = stock['price']  # Use CSV price in dry run
            else:
                ltp = ltp_cache.get(symbol)
                if not ltp:
                    # Fallback to individual fetch if batch missed
                    ltp_data = with_backoff(lambda: kite.ltp(f"NSE:{symbol}"))
                    ltp = ltp_data[f"NSE:{symbol}"]['last_price']
            
            # Check LTP drift - skip if price moved too much from CSV price
            csv_price = stock['price']
            if csv_price > 0 and abs(ltp - csv_price) / csv_price > MAX_LTP_DRIFT:
                logger.warning(f"âš ï¸  {symbol}: LTP â‚¹{ltp:.2f} drifted >{MAX_LTP_DRIFT*100:.0f}% from CSV â‚¹{csv_price:.2f}, skipping")
                continue
            
            # Calculate quantity to buy
            if budget_info['mode'] == 'budget' and ltp > 0:
                # BUDGET MODE: qty = budget_per_stock / LTP
                budget_qty = int(budget_info['per_stock_budget'] / ltp)
                # Don't exceed CSV quantity limit
                qty_to_buy = min(budget_qty, qty_left)
                # At least 1 share if budget allows
                if qty_to_buy < 1 and budget_info['per_stock_budget'] >= ltp:
                    qty_to_buy = 1
                
                # Apply max qty per stock cap (default: 500 shares per stock total)
                max_remaining = CONFIG.max_qty_per_stock - already_bought
                if max_remaining <= 0:
                    logger.info(f"   â­ï¸ {symbol}: Already at max qty ({CONFIG.max_qty_per_stock}), skipping")
                    continue
                qty_to_buy = min(qty_to_buy, max_remaining)
                
                # Apply per-stock daily budget cap
                # Estimate already spent on this stock
                spent_on_stock = already_bought * ltp  # Approximate
                remaining_stock_budget = CONFIG.per_stock_daily_budget - spent_on_stock
                if remaining_stock_budget <= 0:
                    logger.info(f"   â­ï¸ {symbol}: Already at budget cap (â‚¹{CONFIG.per_stock_daily_budget:,.0f}), skipping")
                    continue
                max_by_budget = int(remaining_stock_budget / ltp)
                qty_to_buy = min(qty_to_buy, max_by_budget)
            else:
                # QUANTITY MODE: divide remaining equally among remaining tranches
                qty_to_buy = math.ceil(qty_left / tranches_remaining)
                qty_to_buy = min(qty_to_buy, qty_left)
                # Still apply max qty per stock cap
                max_remaining = CONFIG.max_qty_per_stock - already_bought
                qty_to_buy = min(qty_to_buy, max_remaining)
            
            if qty_to_buy < 1:
                continue
            
            limit_price = round_to_tick(ltp * LTP_DISCOUNT)  # 0.2% below LTP, tick-aligned
            
            tranche_order = {
                'symbol': symbol,
                'quantity': qty_to_buy,
                'order_type': 'LIMIT',
                'price': limit_price,
                'product': stock['product'],
                'variety': stock['variety']
            }
            
            result = place_buy_order(kite, tranche_order)
            
            if result.success:
                orders_placed += 1
                
                # Get actual fill details
                fill_price = limit_price
                filled_qty = qty_to_buy
                
                if not result.dry_run and result.order_id:
                    # Wait for order completion (shorter wait for LIMIT)
                    fill_info = wait_for_order_completion(kite, result.order_id, symbol, max_wait=15)
                    if fill_info:
                        filled_qty = fill_info.get('filled_quantity', 0)
                        if filled_qty > 0:
                            fill_price = fill_info.get('average_price', limit_price)
                            logger.info(f"   â†’ {symbol} filled: {filled_qty}/{qty_to_buy} @ â‚¹{fill_price:.2f}")
                        else:
                            logger.warning(f"   â†’ {symbol} LIMIT order pending/unfilled")
                            # Still track as "intended" for next tranche calculation
                
                # Update tracker with what was actually filled (or intended in dry run)
                if result.dry_run:
                    bought_tracker[symbol] = already_bought + qty_to_buy
                    filled_qty = qty_to_buy
                else:
                    bought_tracker[symbol] = already_bought + filled_qty
                
                # Track actual spent (real-time budget guard)
                actual_spent['total'] += filled_qty * fill_price
                
                # Place stop loss using ACTUAL fill price, only for filled qty
                if STOP_LOSS_ENABLED and filled_qty > 0:
                    sl_result = place_stop_loss(kite, symbol, filled_qty, fill_price, stock['product'])
                    if sl_result:
                        sl_placed += 1
                
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
    
    logger.info(f"\nâœ… Tranche {tranche_num} orders: {orders_placed}/{len(stocks)}")
    if STOP_LOSS_ENABLED:
        sl_label = "OCO (SL+Target)" if USE_GTT and USE_OCO else "Stop losses"
        logger.info(f"ðŸ›¡ï¸  {sl_label} placed: {sl_placed}/{orders_placed}")
    return orders_placed


def main():
    print("=" * 60)
    print("ZERODHA KITE - TRANCHE BUYING STRATEGY")
    print("=" * 60)
    print(f"\nðŸ“… Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Market hours guard (skip in dry run for testing)
    if not CONFIG.dry_run and not is_market_hours():
        print(f"\nâŒ Market is closed. Trading hours: {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d}")
        print("   Use --live flag during market hours to execute orders.")
        return
    
    # Validate credentials first
    if not validate_credentials():
        print("\nâŒ Cannot proceed without valid credentials")
        return
    
    # Read order book
    orders = read_order_book(CONFIG.order_book_file)
    
    if not orders:
        print("âŒ No orders found in order book!")
        return
    
    # Calculate totals
    total_orders = len(orders)
    csv_notional_investment = sum(o['quantity'] * o['price'] for o in orders)
    
    # Calculate actual Phase 1 cost (1 share of each stock)
    # This ensures base budget covers at least 1 share even for expensive stocks
    base_cost_actual = sum(o['price'] for o in orders)  # Sum of LTPs for 1 share each
    CONFIG.base_budget_actual = base_cost_actual
    
    # Budget guard
    if CONFIG.use_budget_mode and CONFIG.daily_budget > 0:
        if CONFIG.max_budget and CONFIG.daily_budget > CONFIG.max_budget:
            print(f"\nâŒ Daily budget (â‚¹{CONFIG.daily_budget:,.2f}) exceeds MAX_BUDGET (â‚¹{CONFIG.max_budget:,.2f}). Aborting.")
            return
    else:
        if CONFIG.max_budget and csv_notional_investment > CONFIG.max_budget:
            print(f"\nâŒ Total investment (â‚¹{csv_notional_investment:,.2f}) exceeds MAX_BUDGET (â‚¹{CONFIG.max_budget:,.2f}). Aborting.")
            return
    
    print(f"\nðŸ“‹ Found {total_orders} stocks in {CONFIG.order_book_file}")
    if CONFIG.use_budget_mode and CONFIG.daily_budget > 0:
        print(f"ðŸ’° Planned spend (daily budget): â‚¹{CONFIG.daily_budget:,.2f}")
        print(f"   CSV notional (qtyÃ—price): â‚¹{csv_notional_investment:,.2f} (ignored in budget mode)")
    else:
        print(f"ðŸ’° Total investment required: â‚¹{csv_notional_investment:,.2f}")
    
    # Display strategy summary
    print("\n" + "-" * 60)
    print("ðŸ“Š TRANCHE STRATEGY:")
    print("-" * 60)
    
    if CONFIG.use_budget_mode and CONFIG.daily_budget > 0:
        # Budget mode display - based on daily budget
        remaining_budget = max(0.0, CONFIG.daily_budget - base_cost_actual)
        tranche_budget_total = (remaining_budget / TRANCHE_COUNT) if TRANCHE_COUNT > 0 else 0.0
        per_stock_tranche_budget = (tranche_budget_total / total_orders) if total_orders > 0 else 0.0
        per_stock_tranche_budget = min(per_stock_tranche_budget, (CONFIG.per_stock_daily_budget / TRANCHE_COUNT) if TRANCHE_COUNT > 0 else CONFIG.per_stock_daily_budget)
        
        print(f"  ðŸ’µ MODE: BUDGET-BASED")
        print(f"  Per-Stock Limits:")
        print(f"    â€¢ Max â‚¹{CONFIG.per_stock_daily_budget:,.0f} per stock/day")
        print(f"    â€¢ Max {CONFIG.max_qty_per_stock} shares per stock")
        print(f"  Daily Budget: â‚¹{CONFIG.daily_budget:,.0f}")
        print(f"  Phase 1: 1 share each @ MARKET (~â‚¹{base_cost_actual:,.0f} total)")
        print(f"  Phase 2: Remaining â‚¹{remaining_budget:,.0f} split into {TRANCHE_COUNT} tranches")
        print(f"           Per tranche: ~â‚¹{tranche_budget_total:,.0f} total (~â‚¹{per_stock_tranche_budget:,.0f}/stock)")
        
        # Calculate max possible per stock
        avg_price = base_cost_actual / total_orders if total_orders > 0 else 0
        max_qty_by_budget = int(CONFIG.per_stock_daily_budget / avg_price) if avg_price > 0 else 0
        effective_max = min(max_qty_by_budget, CONFIG.max_qty_per_stock)
        print(f"  Effective Max: ~{effective_max} shares/stock (avg price â‚¹{avg_price:,.0f})")
    else:
        # Quantity mode display
        print(f"  ðŸ“¦ MODE: QUANTITY-BASED (from CSV)")
        print(f"  Phase 1: Buy 1 share of each @ MARKET (base price)")
        print(f"  Phase 2: {TRANCHE_COUNT} hourly tranches @ {int(TRANCHE_SIZE*100)}% each")
        print(f"  Max Qty: {CONFIG.max_qty_per_stock} shares per stock")
    
    print(f"  Limit Price: {(1-LTP_DISCOUNT)*100:.1f}% below LTP")
    print(f"  Interval: {TRANCHE_INTERVAL//60} minutes between tranches")
    if STOP_LOSS_ENABLED:
        if USE_GTT and USE_OCO:
            sl_type = "GTT OCO (SL + Target)"
            print(f"  Stop Loss: {STOP_LOSS_PERCENT*100:.0f}% below | Target: {TARGET_PERCENT*100:.0f}% above ({sl_type})")
        elif USE_GTT:
            print(f"  Stop Loss: {STOP_LOSS_PERCENT*100:.1f}% below buy price (GTT - persists)")
        else:
            print(f"  Stop Loss: {STOP_LOSS_PERCENT*100:.1f}% below buy price (SL-M - session)")
    else:
        print(f"  Stop Loss: DISABLED")
    print("-" * 60)
    
    # Display orders
    print(f"\n{'Symbol':<15} {'Total Qty':>10} {'Price':>10} {'Total':>12}")
    print("-" * 50)
    for order in orders:
        total = order['quantity'] * order['price']
        print(f"{order['symbol']:<15} {order['quantity']:>10} {order['price']:>10.2f} {total:>12.2f}")
    print("-" * 50)
    if CONFIG.use_budget_mode and CONFIG.daily_budget > 0:
        print(f"{'TOTAL':<15} {'':<10} {'':<10} {CONFIG.daily_budget:>12,.2f}")
    else:
        print(f"{'TOTAL':<15} {'':<10} {'':<10} {csv_notional_investment:>12,.2f}")
    print("-" * 50)
    
    if CONFIG.dry_run:
        print("\nâš ï¸  DRY RUN MODE - No actual orders will be placed")
        print("    Set DRY_RUN = False or use --live flag to execute real orders\n")
    else:
        print("\nðŸ”´ LIVE MODE - Orders will be executed!")
        if CONFIG.use_budget_mode and CONFIG.daily_budget > 0:
            print(f"    Daily budget: â‚¹{CONFIG.daily_budget:,.2f}")
        else:
            print(f"    Total investment: â‚¹{csv_notional_investment:,.2f}")
        print(f"    Duration: ~{TRANCHE_COUNT} hours\n")
        
        # TPIN Reminder for GTT/CNC sell orders
        if STOP_LOSS_ENABLED and USE_GTT:
            print("âš ï¸  CDSL TPIN REMINDER:")
            print("    Have you authorized holdings via TPIN today?")
            print("    Kite â†’ Portfolio â†’ Holdings â†’ Authorize")
            print("    (Required for GTT sell orders unless POA/DDPI submitted)\n")
        
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            return
    
    # Initialize Kite client
    kite = get_kite_client()
    
    # Initialize tracker from today's existing orders (enables idempotent re-runs)
    # If script was cancelled and re-run, this picks up where it left off
    symbols = [o['symbol'] for o in orders]
    bought_tracker, actual_spent = initialize_tracker_from_orders(kite, symbols)
    
    # Check if we've already completed buying for all stocks
    all_complete = all(
        bought_tracker.get(o['symbol'], 0) >= o['quantity']
        for o in orders
    )
    if all_complete:
        logger.info("âœ… All orders already complete from previous run!")
        print("\n" + "=" * 60)
        print("âœ… ALL STOCKS ALREADY PURCHASED")
        print("=" * 60)
        print("   Previous run completed all orders. Nothing to do.")
        print("   Use --protect flag to add GTT OCO protection.")
        return
    
    # Show resume status if there are existing orders
    if bought_tracker:
        print("\n" + "-" * 60)
        print("ðŸ“‹ RESUMING FROM PREVIOUS RUN:")
        print("-" * 60)
        for o in orders:
            sym = o['symbol']
            bought = bought_tracker.get(sym, 0)
            total = o['quantity']
            remaining = total - bought
            if bought > 0:
                print(f"   {sym:<15} {bought:>4}/{total:<4} bought, {remaining:>4} remaining")
        print("-" * 60)
    
    # PHASE 1: Base Price Run (1 share each at MARKET)
    # Skip stocks that already have at least 1 share bought
    stocks_needing_base = [o for o in orders if bought_tracker.get(o['symbol'], 0) < 1]
    if stocks_needing_base:
        run_base_price_orders(kite, stocks_needing_base, bought_tracker, actual_spent)
    else:
        logger.info("â­ï¸  Skipping Phase 1 - all stocks already have base orders")
    
    # Real-time budget check after base orders
    if CONFIG.max_budget and actual_spent['total'] > CONFIG.max_budget:
        logger.warning(f"ðŸš¨ Budget exceeded after base orders! Spent: â‚¹{actual_spent['total']:,.2f} > Max: â‚¹{CONFIG.max_budget:,.2f}")
        logger.warning("Skipping tranche orders.")
    else:
        # Calculate overall progress to determine starting tranche
        total_target_qty = sum(o['quantity'] for o in orders)
        total_bought_qty = sum(bought_tracker.get(o['symbol'], 0) for o in orders)
        overall_progress = total_bought_qty / total_target_qty if total_target_qty > 0 else 0
        
        # Estimate starting tranche (Phase 1 = base, then 25% per tranche)
        # Base takes ~0%, Tranche 1 = 25%, Tranche 2 = 50%, etc.
        if overall_progress >= 0.95:
            start_tranche = TRANCHE_COUNT + 1  # Skip all tranches
            logger.info(f"â­ï¸  Progress {overall_progress*100:.0f}% - all tranches effectively complete")
        elif overall_progress >= 0.75:
            start_tranche = 4  # Start at tranche 4
            logger.info(f"â­ï¸  Progress {overall_progress*100:.0f}% - resuming at tranche 4")
        elif overall_progress >= 0.50:
            start_tranche = 3  # Start at tranche 3
            logger.info(f"â­ï¸  Progress {overall_progress*100:.0f}% - resuming at tranche 3")
        elif overall_progress >= 0.25:
            start_tranche = 2  # Start at tranche 2
            logger.info(f"â­ï¸  Progress {overall_progress*100:.0f}% - resuming at tranche 2")
        else:
            start_tranche = 1  # Start from beginning
        
        # PHASE 2: Hourly Tranche Execution
        for tranche in range(start_tranche, TRANCHE_COUNT + 1):
            # Real-time budget check before each tranche
            if CONFIG.max_budget and actual_spent['total'] > CONFIG.max_budget * 0.95:
                logger.warning(f"ðŸš¨ Approaching budget limit ({actual_spent['total']:,.2f}/{CONFIG.max_budget:,.2f}). Stopping tranches.")
                break
            
            if tranche > start_tranche:
                wait_time = TRANCHE_INTERVAL if not CONFIG.dry_run else 2  # 2 sec in dry run
                print(f"\nâ° Waiting {wait_time//60 if wait_time > 60 else wait_time} {'minutes' if wait_time > 60 else 'seconds'} until next tranche...")
                time.sleep(wait_time)
            
            tranches_remaining = TRANCHE_COUNT - tranche + 1
            run_tranche_orders(kite, orders, tranche, bought_tracker, tranches_remaining, actual_spent)
    
    # Final summary
    print("\n" + "=" * 60)
    print("âœ… TRANCHE STRATEGY COMPLETED")
    print(f"   Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Total spent: â‚¹{actual_spent['total']:,.2f}")
    
    # Show what was bought
    print("\nðŸ“Š QUANTITIES BOUGHT:")
    for symbol, qty in bought_tracker.items():
        target = next((o['quantity'] for o in orders if o['symbol'] == symbol), 0)
        status = "âœ“" if qty >= target else f"({qty}/{target})"
        print(f"   {symbol:<15} {qty:>4} {status}")
    
    print("=" * 60)
    
    # Recommendation for end-of-day protection
    if not STOP_LOSS_ENABLED:
        print("\nðŸ’¡ TIP: Run 'python buy_stocks.py --protect' to set consolidated GTT OCO")
        print("   for all holdings (1 GTT per stock instead of per-order)")
        print("=" * 60)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Zerodha Kite Tranche Buying Strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python buy_stocks.py                  # Run tranche buying (dry run by default)
  python buy_stocks.py --live           # Run in live mode
  python buy_stocks.py --budget 50000   # Set daily budget to â‚¹50,000
  python buy_stocks.py --qty-mode       # Use CSV quantities instead of budget
  python buy_stocks.py --protect        # Protect holdings with single GTT OCO
  python buy_stocks.py --protect --sliced  # Protect with sliced GTT (multiple SL/Target levels)
  python buy_stocks.py --protect --sliced --live  # Execute sliced protection
  python buy_stocks.py --protect --refresh --live  # Refresh GTTs with trailing stops
  python buy_stocks.py --gtt-buy         # Place GTT buy orders for dip accumulation
  python buy_stocks.py --gtt-buy --refresh --live  # Refresh GTT BUYs using latest LTP
  python buy_stocks.py --delete-buy-gtts --live  # Delete ALL active BUY-side GTTs
  python buy_stocks.py --new-stocks     # Buy 1 share of NEW stocks from research_data.csv
  python buy_stocks.py --update-prices  # Update CSV with current market prices
  python buy_stocks.py --file orders.csv --live  # Use custom order file
        """
    )
    parser.add_argument(
        "--protect", 
        action="store_true", 
        help="Only protect existing holdings with GTT OCO orders (skip buying)"
    )
    parser.add_argument(
        "--reprice-pending-buys",
        action="store_true",
        help="Reprice all pending LIMIT BUY orders to 0.99×LTP (modify or cancel+recreate)"
    )
    parser.add_argument(
        "--reprice-discount",
        type=float,
        default=0.99,
        help="Discount multiplier for repricing pending buys (default: 0.99)"
    )
    parser.add_argument(
        "--delete-buy-gtts",
        action="store_true",
        help="Delete ALL active BUY-side GTTs (does not touch SELL protection GTTs)"
    )
    parser.add_argument(
        "--gtt-buy",
        action="store_true",
        help="Place GTT buy orders at dip triggers (default -2%%/-4%%, Top15 only)"
    )
    parser.add_argument(
        "--sliced",
        action="store_true",
        help="Use sliced GTT OCO (multiple graduated SL/Target levels per stock)"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh mode: delete & recreate GTTs (use with --protect or --gtt-buy)"
    )
    parser.add_argument(
        "--new-stocks",
        action="store_true",
        help="Buy 1 share each of NEW stocks from research_data.csv (not in current holdings)"
    )
    parser.add_argument(
        "--live", 
        action="store_true", 
        help="Run in live mode (override DRY_RUN setting)"
    )
    parser.add_argument(
        "--file", 
        type=str, 
        default=ORDER_BOOK_FILE,
        help=f"Path to order book CSV file (default: {ORDER_BOOK_FILE})"
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=DAILY_BUDGET,
        help=f"Daily budget in INR (default: â‚¹{DAILY_BUDGET:,.0f})"
    )
    parser.add_argument(
        "--qty-mode",
        action="store_true",
        help="Use CSV quantities instead of budget-based calculation"
    )
    parser.add_argument(
        "--per-stock-budget",
        type=float,
        default=PER_STOCK_DAILY_BUDGET,
        help=f"Max budget per stock per day (default: â‚¹{PER_STOCK_DAILY_BUDGET:,.0f})"
    )
    parser.add_argument(
        "--max-qty",
        type=int,
        default=MAX_QTY_PER_STOCK,
        help=f"Max quantity per stock (default: {MAX_QTY_PER_STOCK})"
    )
    parser.add_argument(
        "--update-prices",
        action="store_true",
        help="Fetch current LTP and update prices in order_book.csv"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    # Override config if --live flag is set
    if args.live:
        CONFIG.dry_run = False
    
    # Override config if --file is specified
    if args.file != ORDER_BOOK_FILE:
        CONFIG.order_book_file = args.file
    
    # Override budget if specified
    if args.budget != DAILY_BUDGET:
        CONFIG.daily_budget = args.budget
    
    # Switch to quantity mode if --qty-mode flag is set
    if args.qty_mode:
        CONFIG.use_budget_mode = False
    
    # Override per-stock limits if specified
    if args.per_stock_budget != PER_STOCK_DAILY_BUDGET:
        CONFIG.per_stock_daily_budget = args.per_stock_budget
    if args.max_qty != MAX_QTY_PER_STOCK:
        CONFIG.max_qty_per_stock = args.max_qty
    
    # Check for --update-prices flag to update CSV with current LTP
    if args.update_prices:
        # Validate credentials first
        if not validate_credentials():
            print("\nâŒ Cannot proceed without valid credentials")
            sys.exit(1)
        
        kite = get_kite_client()
        update_order_book_prices(kite, CONFIG.order_book_file)
        sys.exit(0)

    # Reprice all pending LIMIT BUY orders to (discount * LTP)
    elif args.reprice_pending_buys:
        print("=" * 70)
        print("ZERODHA KITE - REPRICE PENDING LIMIT BUY ORDERS")
        print("=" * 70)

        if not validate_credentials():
            print("\nâŒ Cannot proceed without valid credentials")
            sys.exit(1)

        if CONFIG.dry_run:
            print("\nâš ï¸  DRY RUN MODE - No orders will be modified")
        else:
            print("\nðŸ”´ LIVE MODE - Pending orders will be modified/replaced!")
            confirm = input("\nType 'CONFIRM' to proceed: ")
            if confirm != "CONFIRM":
                print("Aborted.")
                sys.exit(0)

        kite = get_kite_client()
        reprice_pending_limit_buy_orders(kite, discount=float(args.reprice_discount))
        sys.exit(0)

    # Delete all BUY-side GTTs (safe: doesn't delete SELL GTTs)
    elif args.delete_buy_gtts:
        print("=" * 70)
        print("ZERODHA KITE - DELETE ALL BUY-SIDE GTTs")
        print("=" * 70)

        if not validate_credentials():
            print("\nâŒ Cannot proceed without valid credentials")
            sys.exit(1)

        if CONFIG.dry_run:
            print("\nâš ï¸  DRY RUN MODE - No actual GTT orders will be deleted")
        else:
            print("\nðŸ”´ LIVE MODE - BUY-side GTTs will be deleted!")
            confirm = input("\nType 'CONFIRM' to proceed: ")
            if confirm != "CONFIRM":
                print("Aborted.")
                sys.exit(0)

        kite = get_kite_client()
        deleted = delete_existing_gtt_buys(kite, symbols_to_refresh=None)
        print(f"\nDeleted {deleted} BUY-side GTT(s)")
        sys.exit(0)
    
    # Check for --gtt-buy flag to place GTT buy orders for dip accumulation
    elif args.gtt_buy:
        print("=" * 70)
        print(f"ZERODHA KITE - GTT BUY ORDERS (DIP ACCUMULATION)")
        print("=" * 70)
        print(f"\nStrategy: Place GTT buy orders at -{GTT_BUY_LOWER_PERCENT*100:.0f}% and -{GTT_BUY_UPPER_PERCENT*100:.0f}% below current price")
        
        # Validate credentials first
        if not validate_credentials():
            print("\nERROR: Cannot proceed without valid credentials")
            sys.exit(1)
        
        if CONFIG.dry_run:
            print("\nDRY RUN MODE - No actual GTT orders will be placed")
        else:
            print("\nLIVE MODE - GTT BUY orders will be placed!")
            confirm = input("\nType 'CONFIRM' to proceed: ")
            if confirm != "CONFIRM":
                print("Aborted.")
                sys.exit(0)
        
        kite = get_kite_client()

        # Existing BUY GTTs (used for idempotency or refresh)
        existing_buy_gtts = get_existing_gtt_buy_symbols(kite)
        
        # Read stocks from order book
        orders = read_order_book(CONFIG.order_book_file)
        if not orders:
            print("\nERROR: No valid orders found in order book")
            sys.exit(1)

        # Universe filter: Top15 only
        before_rank_filter = len(orders)
        orders = [o for o in orders if _is_top15_rank(o.get('rank', ''))]
        filtered = before_rank_filter - len(orders)
        if filtered > 0:
            print(f"\nTop15 filter: skipped {filtered} non-Top15 symbols")
        if not orders:
            print("\nNothing to do - no Top15 symbols found in the file")
            sys.exit(0)

        symbols_in_book = {o['symbol'] for o in orders}

        if args.refresh:
            print("\nREFRESH MODE: Deleting existing BUY-side GTTs for these symbols and recreating with latest LTP...")
            deleted = delete_existing_gtt_buys(kite, symbols_to_refresh=symbols_in_book)
            print(f"Deleted {deleted} BUY GTTs")
            # After deletion we should not skip anything.
            existing_buy_gtts = set()
        else:
            # Idempotency: skip symbols that already have active BUY GTTs
            if existing_buy_gtts:
                before = len(orders)
                orders = [o for o in orders if o['symbol'] not in existing_buy_gtts]
                skipped = before - len(orders)
                if skipped > 0:
                    print(f"\nSkipping {skipped} symbols that already have active GTT BUY orders")
                if not orders:
                    print("\nNothing to do - all symbols already have GTT BUY orders")
                    sys.exit(0)
        
        # Get current LTPs for all symbols
        symbols = [o['symbol'] for o in orders]
        print(f"\nFetching current prices for {len(symbols)} stocks...")
        
        try:
            ltp_data = with_backoff(kite.ltp, ['NSE:' + s for s in symbols])
            stocks_data = []

            # Budget sizing for GTT BUY (only when budget mode is enabled)
            # If Allocation column exists, treat it as WEIGHT and split total daily budget across symbols.
            fallback_budget = 0.0
            total_alloc_weight = 0.0
            if CONFIG.use_budget_mode and len(orders) > 0:
                if CONFIG.daily_budget and CONFIG.daily_budget > 0:
                    fallback_budget = CONFIG.daily_budget / len(orders)
                fallback_budget = min(fallback_budget, CONFIG.per_stock_daily_budget)

                total_alloc_weight = sum(
                    float(o.get('allocation', 0.0) or 0.0)
                    for o in orders
                    if float(o.get('allocation', 0.0) or 0.0) > 0
                )

            for order in orders:
                symbol = order['symbol']
                key = f"NSE:{symbol}"
                if key in ltp_data:
                    ltp = ltp_data[key]['last_price']

                    # Decide quantity
                    if CONFIG.use_budget_mode:
                        alloc = float(order.get('allocation', 0.0) or 0.0)

                        if CONFIG.daily_budget and CONFIG.daily_budget > 0:
                            if total_alloc_weight > 0 and alloc > 0:
                                per_stock_budget = CONFIG.daily_budget * (alloc / total_alloc_weight)
                            else:
                                per_stock_budget = fallback_budget
                        else:
                            per_stock_budget = fallback_budget

                        per_stock_budget = min(per_stock_budget, CONFIG.per_stock_daily_budget)
                        qty = _compute_qty_from_budget(ltp, per_stock_budget, CONFIG.max_qty_per_stock)
                    else:
                        qty = int(order.get('quantity', 0) or 0)
                        qty = min(qty, CONFIG.max_qty_per_stock) if CONFIG.max_qty_per_stock > 0 else qty

                    if qty <= 0:
                        logger.warning(f"Budget/qty resulted in 0 for {symbol}, skipping")
                        continue

                    stocks_data.append({
                        'symbol': symbol,
                        'quantity': qty,
                        'ltp': ltp,
                        'product': order.get('product', 'CNC'),
                        'allocation': float(order.get('allocation', 0.0) or 0.0)
                    })
                else:
                    logger.warning(f"Could not get LTP for {symbol}, skipping")
            
            if stocks_data:
                place_gtt_buy_orders_for_stocks(kite, stocks_data)
            else:
                print("\nERROR: No valid stock data retrieved")
        except Exception as e:
            logger.error(f"Error fetching LTP data: {e}")
            sys.exit(1)
        
        sys.exit(0)
    
    # Check for --protect flag to only protect existing holdings
    elif args.protect:
        mode_name = "SLICED GTT OCO" if args.sliced else "GTT OCO"
        print("=" * 70)
        print(f"ZERODHA KITE - PROTECT EXISTING HOLDINGS ({mode_name})")
        print("=" * 70)
        
        # Validate credentials first
        if not validate_credentials():
            print("\nâŒ Cannot proceed without valid credentials")
            sys.exit(1)
        
        if args.sliced:
            print("\nðŸŽšï¸  SLICED MODE: Creates multiple GTTs per stock")
            print("   â€¢ Partial profit booking at different target levels")
            print("   â€¢ Graduated stop losses for position management")
            print(f"\n   Slices configured: {len(GTT_SLICES)}")
            for i, (qty_pct, sl_pct, tgt_pct) in enumerate(GTT_SLICES, 1):
                print(f"   {i}. {qty_pct*100:.0f}% qty â†’ SL -{sl_pct*100:.0f}% / Target +{tgt_pct*100:.0f}%")
        
        if CONFIG.dry_run:
            print("\nâš ï¸  DRY RUN MODE - No actual GTT orders will be placed")
        else:
            print("\nðŸ”´ LIVE MODE - GTT orders will be placed!")
            print("\nâš ï¸  CDSL TPIN REMINDER:")
            print("    Have you authorized holdings via TPIN today?")
            confirm = input("\nType 'CONFIRM' to proceed: ")
            if confirm != "CONFIRM":
                print("Aborted.")
                sys.exit(0)
        
        kite = get_kite_client()
        
        # Check for existing GTTs (idempotency)
        existing_gtts = get_existing_gtts(kite)
        if existing_gtts:
            print(f"\nâš ï¸  Found {len(existing_gtts)} existing active GTT orders")
            if args.refresh:
                print("\n🔄 REFRESH MODE: Deleting existing GTTs to recreate with trailing stops...")
                deleted = delete_existing_gtts(kite)
                print(f"   Deleted {deleted} GTT orders")
                print("   Recreating with updated SL/Target based on current LTP...\n")
            else:
                print("   Symbols already protected will be skipped to avoid duplicates")
                print("   TIP: Use --refresh to update existing GTTs with trailing stops")
        
        # Use sliced or regular protection
        if args.sliced:
            protect_existing_holdings_sliced(kite)
        else:
            protect_existing_holdings(kite)
    
    # Check for --new-stocks flag to buy only NEW stocks from research_data.csv
    elif args.new_stocks:
        print("=" * 70)
        print("ZERODHA KITE - BUY NEW STOCKS FROM RESEARCH DATA")
        print("=" * 70)
        
        # Validate credentials first
        if not validate_credentials():
            print("\nCannot proceed without valid credentials")
            sys.exit(1)
        
        if CONFIG.dry_run:
            print("\nDRY RUN MODE - No actual orders will be placed")
        else:
            print("\nLIVE MODE - Orders will be placed!")
            confirm = input("\nType 'CONFIRM' to proceed: ")
            if confirm != "CONFIRM":
                print("Aborted.")
                sys.exit(0)
        
        kite = get_kite_client()
        
        # Use research_data.csv by default, or --file if specified
        research_file = args.file if args.file != ORDER_BOOK_FILE else "data/research_data.csv"
        buy_new_stocks(kite, research_file)
    
    else:
        main()

