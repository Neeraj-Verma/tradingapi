"""
Place GTT OCO Orders or BUY Orders from buy.xlsx

This script supports three modes:
1. GTT OCO (default) - Places sell-side GTT with Stop Loss + Target
2. GTT BUY (--gtt-buy) - Places buy-side GTT at 2% below CMP
3. Market BUY (--buy) - Places immediate market buy orders

Usage:
    python place_gtt_orders.py                       # Dry run GTT OCO (SL + Target)
    python place_gtt_orders.py --execute             # Place GTT OCO orders
    python place_gtt_orders.py --gtt-buy             # Dry run GTT BUY (2% below)
    python place_gtt_orders.py --gtt-buy --execute   # Place GTT BUY orders
    python place_gtt_orders.py --gtt-buy --trigger-pct 3  # GTT BUY at 3% below
    python place_gtt_orders.py --buy                 # Dry run market BUY
    python place_gtt_orders.py --buy --execute       # Place market BUY orders
    python place_gtt_orders.py --allocation 10       # Use 10% of quantity
    python place_gtt_orders.py --symbol SBIN         # Single stock only
"""

import os
import re
import sys
import time
import argparse
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'gtt_orders_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# Constants
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
BUY_XLSX_PATH = os.path.join(DATA_DIR, 'buy.xlsx')
BUY_CMP_CSV_PATH = os.path.join(DATA_DIR, 'buy_with_cmp_latest.csv')

# Stock name to NSE symbol mapping (from generate_buy_csv.py)
STOCK_TO_SYMBOL = {
    'HDFC Bank': 'HDFCBANK',
    'ICICI Bank': 'ICICIBANK',
    'Asian Paints': 'ASIANPAINT',
    'Pidilite': 'PIDILITIND',
    'Titan': 'TITAN',
    'HUL': 'HINDUNILVR',
    'Nestle': 'NESTLEIND',
    'Kotak Bank': 'KOTAKBANK',
    'Sun Pharma': 'SUNPHARMA',
    'Dr Reddy': 'DRREDDY',
    'L&T': 'LT',
    'Siemens': 'SIEMENS',
    'ABB': 'ABB',
    'Cummins': 'CUMMINSIND',
    'Polycab': 'POLYCAB',
    'KEI Industries': 'KEI',
    'Apollo Hospitals': 'APOLLOHOSP',
    'Tata Elxsi': 'TATAELXSI',
    'Jio Financial': 'JIOFIN',
    'Zomato': 'ETERNAL',
    'ITC': 'ITC',
    'BHEL': 'BHEL',
    'PNB': 'PNB',
    'ONGC': 'ONGC',
    'NTPC': 'NTPC',
    'NHPC': 'NHPC',
    'CIPLA': 'CIPLA',
    'WIPRO': 'WIPRO',
    'RBL Bank': 'RBLBANK',
    'Yes Bank': 'YESBANK',
    'Coal India': 'COALINDIA',
    'SAIL': 'SAIL',
    'IRB Infra': 'IRB',
    'Apollo Tyres': 'APOLLOTYRE',
    'Ador Welding': 'ADORWELD',
    'RCF': 'RCF',
    'Mazagon Dock': 'MAZDOCK',
    'Godawari Power': 'GPPL',
    '20 Microns': '20MICRONS',
    'Zomato (Old holding)': 'ETERNAL',
}

# SL Execution buffer - limit price below trigger to ensure fill
SL_EXECUTION_BUFFER = 0.005  # 0.5% below trigger


def get_symbol(stock_name: str) -> str:
    """Get NSE symbol from stock name."""
    stock_name = stock_name.strip()
    if stock_name in STOCK_TO_SYMBOL:
        return STOCK_TO_SYMBOL[stock_name]
    return stock_name.upper().replace(' ', '')


# Global tick size map (populated from Kite API)
TICK_SIZE_MAP: Dict[str, float] = {}


def fetch_tick_sizes(kite: KiteConnect, exchange: str = "NSE") -> Dict[str, float]:
    """Fetch tick sizes for all instruments from Kite API."""
    global TICK_SIZE_MAP
    try:
        instruments = kite.instruments(exchange)
        for inst in instruments:
            symbol = (inst.get('tradingsymbol') or '').strip().upper()
            tick = inst.get('tick_size', 0.05)
            if symbol and tick:
                TICK_SIZE_MAP[symbol] = float(tick)
        logger.info(f"Loaded tick sizes for {len(TICK_SIZE_MAP)} instruments")
        return TICK_SIZE_MAP
    except Exception as e:
        logger.error(f"Error fetching tick sizes: {e}")
        return {}


def get_tick_size(symbol: str) -> float:
    """Get tick size for a symbol (default 0.05 if not found)."""
    return TICK_SIZE_MAP.get(symbol, 0.05)


def round_to_tick(price: float, tick_size: float = 0.05) -> float:
    """Round price to valid tick size."""
    if tick_size <= 0:
        return round(price, 2)
    return round(round(price / tick_size) * tick_size, 2)


def parse_target_value(target_str: str) -> float:
    """
    Parse target percentage from string.
    Handles: "20", "15-20", "20-25", etc.
    Returns the lower bound (conservative target).
    """
    if pd.isna(target_str):
        return 15.0  # Default 15%
    
    target_str = str(target_str).strip()
    
    # Try to extract first number (handles "15-20", "20", etc.)
    match = re.search(r'(\d+(?:\.\d+)?)', target_str)
    if match:
        return float(match.group(1))
    
    return 15.0  # Default


def parse_stoploss_value(sl_str) -> float:
    """Parse stop loss percentage."""
    if pd.isna(sl_str):
        return 10.0  # Default 10%
    
    try:
        return float(sl_str)
    except (ValueError, TypeError):
        return 10.0


def load_stock_data() -> pd.DataFrame:
    """
    Load and merge data from buy.xlsx and buy_with_cmp_latest.csv.
    Returns DataFrame with: Symbol, CMP, Quantity, StopLoss%, Target%
    """
    # Load buy.xlsx for SL and Target
    df_xlsx = pd.read_excel(BUY_XLSX_PATH)
    df_xlsx['Symbol'] = df_xlsx['Stock'].apply(get_symbol)
    df_xlsx['StopLoss_Pct'] = df_xlsx['Stop Loss (%)'].apply(parse_stoploss_value)
    df_xlsx['Target_Pct'] = df_xlsx['Target (%)'].apply(parse_target_value)
    
    # Load buy_with_cmp_latest.csv for CMP and Quantity
    df_cmp = pd.read_csv(BUY_CMP_CSV_PATH)
    
    # Merge on Symbol
    # Keep only rows with valid quantity > 0
    df_cmp = df_cmp[df_cmp['Quantity'] > 0].copy()
    
    # Create mapping from xlsx
    sl_target_map = df_xlsx.groupby('Symbol').agg({
        'StopLoss_Pct': 'first',
        'Target_Pct': 'first'
    }).to_dict('index')
    
    # Add SL and Target to CMP data
    df_cmp['StopLoss_Pct'] = df_cmp['Symbol'].apply(
        lambda x: sl_target_map.get(x, {}).get('StopLoss_Pct', 10.0)
    )
    df_cmp['Target_Pct'] = df_cmp['Symbol'].apply(
        lambda x: sl_target_map.get(x, {}).get('Target_Pct', 15.0)
    )
    
    # De-duplicate by Symbol (take first occurrence)
    df_final = df_cmp.drop_duplicates(subset=['Symbol'], keep='first')
    
    return df_final


def get_existing_gtt_symbols(kite: KiteConnect) -> set:
    """Get symbols that already have active GTT orders."""
    try:
        gtts = kite.get_gtts()
        symbols = set()
        for gtt in gtts:
            if gtt.get('status') == 'active':
                symbol = gtt.get('condition', {}).get('tradingsymbol', '')
                if symbol:
                    symbols.add(symbol)
        return symbols
    except Exception as e:
        logger.error(f"Error fetching existing GTTs: {e}")
        return set()


def place_gtt_oco(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    buy_price: float,
    sl_pct: float,
    target_pct: float,
    dry_run: bool = True
) -> Optional[dict]:
    """
    Place GTT OCO (One Cancels Other) order.
    
    Args:
        kite: KiteConnect instance
        symbol: Trading symbol (e.g., 'SBIN')
        quantity: Number of shares
        buy_price: Current market price (used as base)
        sl_pct: Stop loss percentage (e.g., 10 for 10%)
        target_pct: Target percentage (e.g., 20 for 20%)
        dry_run: If True, only log without placing order
    
    Returns:
        GTT response dict or None on failure
    """
    try:
        # Get tick size for this symbol
        tick = get_tick_size(symbol)
        
        # Calculate trigger prices
        sl_trigger = round_to_tick(buy_price * (1 - sl_pct / 100), tick)
        sl_limit = round_to_tick(sl_trigger * (1 - SL_EXECUTION_BUFFER), tick)
        
        target_trigger = round_to_tick(buy_price * (1 + target_pct / 100), tick)
        target_limit = round_to_tick(target_trigger, tick)
        
        # OCO orders (two legs)
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
        
        if dry_run:
            logger.info(
                f"[DRY RUN] GTT OCO: {symbol:15} x {quantity:>5} | "
                f"CMP: Rs.{buy_price:>10,.2f} | "
                f"SL: Rs.{sl_trigger:>10,.2f} ({sl_pct}% down) | "
                f"Target: Rs.{target_trigger:>10,.2f} ({target_pct}% up)"
            )
            return {"status": "dry_run", "symbol": symbol}
        
        # Place actual GTT
        gtt_response = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_OCO,
            tradingsymbol=symbol,
            exchange="NSE",
            trigger_values=[sl_trigger, target_trigger],
            last_price=round_to_tick(buy_price, tick),
            orders=oco_orders
        )
        
        logger.info(
            f"[OK] GTT OCO Placed: {symbol:15} x {quantity:>5} | "
            f"SL: Rs.{sl_trigger:,.2f} | Target: Rs.{target_trigger:,.2f} | "
            f"GTT ID: {gtt_response.get('trigger_id', 'N/A')}"
        )
        
        return gtt_response
        
    except Exception as e:
        logger.error(f"[FAIL] GTT Error for {symbol}: {e}")
        return None


def place_gtt_buy(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    cmp: float,
    trigger_pct: float = 2.0,
    dry_run: bool = True
) -> Optional[dict]:
    """
    Place GTT BUY order - triggers when price drops below CMP.
    
    Args:
        kite: KiteConnect instance
        symbol: Trading symbol (e.g., 'SBIN')
        quantity: Number of shares to buy
        cmp: Current market price
        trigger_pct: Percentage below CMP to trigger (default: 2%)
        dry_run: If True, only log without placing order
    
    Returns:
        GTT response dict or None on failure
    """
    try:
        # Get tick size for this symbol
        tick = get_tick_size(symbol)
        
        # Calculate trigger price (2% below CMP)
        trigger_price = round_to_tick(cmp * (1 - trigger_pct / 100), tick)
        # Limit price slightly above trigger to ensure fill
        limit_price = round_to_tick(trigger_price * 1.001, tick)
        
        if dry_run:
            logger.info(
                f"[DRY RUN] GTT BUY: {symbol:15} x {quantity:>5} | "
                f"CMP: Rs.{cmp:>10,.2f} | "
                f"Trigger: Rs.{trigger_price:>10,.2f} ({trigger_pct}% below)"
            )
            return {"status": "dry_run", "symbol": symbol}
        
        # Place GTT single trigger for buy
        gtt_response = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_SINGLE,
            tradingsymbol=symbol,
            exchange="NSE",
            trigger_values=[trigger_price],
            last_price=round_to_tick(cmp, tick),
            orders=[{
                "exchange": "NSE",
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_BUY,
                "quantity": quantity,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "product": kite.PRODUCT_CNC,
                "price": limit_price
            }]
        )
        
        logger.info(
            f"[OK] GTT BUY Placed: {symbol:15} x {quantity:>5} | "
            f"Trigger: Rs.{trigger_price:,.2f} ({trigger_pct}% below Rs.{cmp:,.2f}) | "
            f"GTT ID: {gtt_response.get('trigger_id', 'N/A')}"
        )
        
        return gtt_response
        
    except Exception as e:
        logger.error(f"[FAIL] GTT BUY Error for {symbol}: {e}")
        return None


def place_market_buy_order(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    cmp: float,
    dry_run: bool = True
) -> Optional[dict]:
    """
    Place a limit buy order at slightly above CMP (simulates market order).
    
    Args:
        kite: KiteConnect instance
        symbol: Trading symbol (e.g., 'SBIN')
        quantity: Number of shares to buy
        cmp: Current market price
        dry_run: If True, only log without placing order
    
    Returns:
        Order response dict or None on failure
    """
    try:
        # Get tick size for this symbol
        tick = get_tick_size(symbol)
        
        # Use limit order at 0.5% above CMP to ensure fill (API doesn't allow unprotected market orders)
        limit_price = round_to_tick(cmp * 1.005, tick)
        
        if dry_run:
            logger.info(
                f"[DRY RUN] BUY LIMIT: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f}"
            )
            return {"status": "dry_run", "symbol": symbol}
        
        # Place limit buy order
        order_response = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange="NSE",
            tradingsymbol=symbol,
            transaction_type=kite.TRANSACTION_TYPE_BUY,
            quantity=quantity,
            order_type=kite.ORDER_TYPE_LIMIT,
            product=kite.PRODUCT_CNC,
            price=limit_price
        )
        
        logger.info(
            f"[OK] BUY Order Placed: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f} | "
            f"Order ID: {order_response}"
        )
        
        return {"order_id": order_response, "symbol": symbol}
        
    except Exception as e:
        logger.error(f"[FAIL] BUY Error for {symbol}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Place GTT OCO orders or Buy orders from buy.xlsx')
    parser.add_argument('--execute', action='store_true', help='Actually place orders (default is dry run)')
    parser.add_argument('--symbol', type=str, help='Place order for specific symbol only')
    parser.add_argument('--skip-existing', action='store_true', default=True, help='Skip symbols with existing GTTs')
    parser.add_argument('--allocation', type=float, default=20.0, help='Percentage of quantity to allocate (default: 20%%)')
    parser.add_argument('--buy', action='store_true', help='Place BUY orders at market price')
    parser.add_argument('--gtt-buy', action='store_true', dest='gtt_buy', help='Place GTT BUY orders (trigger at 2%% below CMP)')
    parser.add_argument('--trigger-pct', type=float, default=2.0, dest='trigger_pct', help='GTT BUY trigger %% below CMP (default: 2%%)')
    args = parser.parse_args()
    
    dry_run = not args.execute
    allocation_pct = args.allocation / 100.0  # Convert to decimal
    is_buy_mode = args.buy
    is_gtt_buy_mode = args.gtt_buy
    trigger_pct = args.trigger_pct
    
    # Determine mode name
    if is_buy_mode:
        mode_name = "BUY MARKET ORDERS"
    elif is_gtt_buy_mode:
        mode_name = f"GTT BUY ORDERS ({trigger_pct}% below CMP)"
    else:
        mode_name = "GTT OCO SELL ORDERS (SL + Target)"
    
    print("=" * 80)
    print(mode_name)
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else '** LIVE EXECUTION **'}")
    print(f"Allocation: {args.allocation}% of calculated quantity")
    print()
    
    if not dry_run:
        confirm = input("WARNING: This will place REAL orders. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted.")
            return
    
    # Initialize Kite
    api_key = os.getenv("API_KEY", "").strip()
    access_token = os.getenv("ACCESS_TOKEN", "").strip()
    
    if not api_key or not access_token:
        logger.error("Missing API_KEY or ACCESS_TOKEN in environment")
        return
    
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    # Verify connection
    try:
        profile = kite.profile()
        logger.info(f"Connected as: {profile.get('user_name', 'Unknown')}")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return
    
    # Fetch tick sizes for all instruments
    logger.info("Fetching tick sizes from Kite API...")
    fetch_tick_sizes(kite, "NSE")
    
    # Load stock data
    logger.info("Loading stock data...")
    df = load_stock_data()
    logger.info(f"Loaded {len(df)} stocks with valid quantity")
    
    # Filter by symbol if specified
    if args.symbol:
        df = df[df['Symbol'] == args.symbol.upper()]
        if df.empty:
            logger.error(f"Symbol {args.symbol} not found in data")
            return
    
    # Get existing GTTs to avoid duplicates
    existing_gtt_symbols = set()
    if args.skip_existing and not dry_run:
        existing_gtt_symbols = get_existing_gtt_symbols(kite)
        logger.info(f"Found {len(existing_gtt_symbols)} symbols with existing GTTs")
    
    # Place GTT orders
    results = {
        'success': [],
        'skipped': [],
        'failed': []
    }
    
    print()
    print("-" * 80)
    if is_buy_mode:
        print(f"{'Symbol':<15} {'Qty':>6} {'CMP':>12} {'Limit':>12} {'Investment':>15}")
    elif is_gtt_buy_mode:
        print(f"{'Symbol':<15} {'Qty':>6} {'CMP':>12} {'Trigger':>12} {'Investment':>15}")
    else:
        print(f"{'Symbol':<15} {'Qty':>6} {'CMP':>12} {'SL%':>6} {'SL Price':>12} {'Target%':>8} {'Target':>12}")
    print("-" * 80)
    
    for idx, row in df.iterrows():
        symbol = row['Symbol']
        full_quantity = int(row['Quantity'])
        quantity = max(1, int(full_quantity * allocation_pct))  # Apply allocation %, min 1 share
        cmp = float(row['CMP'])
        sl_pct = float(row['StopLoss_Pct'])
        target_pct = float(row['Target_Pct'])
        
        # Get tick size for this symbol
        tick = get_tick_size(symbol)
        
        # Skip if already has GTT (only for GTT modes, not market buy)
        if not is_buy_mode and symbol in existing_gtt_symbols:
            logger.info(f"[SKIP] Skipping {symbol} - already has active GTT")
            results['skipped'].append(symbol)
            continue
        
        # Calculate prices for display (using correct tick size)
        sl_price = round_to_tick(cmp * (1 - sl_pct / 100), tick)
        target_price = round_to_tick(cmp * (1 + target_pct / 100), tick)
        gtt_buy_trigger = round_to_tick(cmp * (1 - trigger_pct / 100), tick)
        limit_buy_price = round_to_tick(cmp * 1.005, tick)  # 0.5% above CMP for limit buy
        investment = quantity * cmp
        
        if is_buy_mode:
            print(f"{symbol:<15} {quantity:>6} {cmp:>12,.2f} {limit_buy_price:>12,.2f} {investment:>15,.2f}")
        elif is_gtt_buy_mode:
            print(f"{symbol:<15} {quantity:>6} {cmp:>12,.2f} {gtt_buy_trigger:>12,.2f} {investment:>15,.2f}")
        else:
            print(f"{symbol:<15} {quantity:>6} {cmp:>12,.2f} {sl_pct:>6.0f}% {sl_price:>12,.2f} {target_pct:>8.0f}% {target_price:>12,.2f}")
        
        # Place order
        if is_buy_mode:
            result = place_market_buy_order(
                kite=kite,
                symbol=symbol,
                quantity=quantity,
                cmp=cmp,
                dry_run=dry_run
            )
        elif is_gtt_buy_mode:
            result = place_gtt_buy(
                kite=kite,
                symbol=symbol,
                quantity=quantity,
                cmp=cmp,
                trigger_pct=trigger_pct,
                dry_run=dry_run
            )
        else:
            result = place_gtt_oco(
                kite=kite,
                symbol=symbol,
                quantity=quantity,
                buy_price=cmp,
                sl_pct=sl_pct,
                target_pct=target_pct,
                dry_run=dry_run
            )
        
        if result:
            results['success'].append(symbol)
        else:
            results['failed'].append(symbol)
        
        # Rate limiting - small delay between orders
        if not dry_run:
            time.sleep(0.3)
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Stocks:    {len(df)}")
    print(f"Successful:      {len(results['success'])}")
    print(f"Skipped:         {len(results['skipped'])}")
    print(f"Failed:          {len(results['failed'])}")
    
    if results['failed']:
        print(f"\nFailed symbols: {', '.join(results['failed'])}")
    
    if dry_run:
        print("\n** This was a DRY RUN. No orders were placed. **")
        print("   Run with --execute to place actual orders.")


if __name__ == "__main__":
    main()
