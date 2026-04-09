"""
Buy Top Losers - Identifies and buys top losing stocks with GTT OCO protection

This script:
1. Fetches OHLC data for NIFTY 50 stocks (or custom list)
2. Calculates % change from previous close
3. Ranks stocks by loss percentage (most negative first)
4. Places buy orders for top N losers (contrarian dip buying)
5. Places GTT OCO orders (Stop Loss + Target) for protection

Usage:
    python buy_top_losers.py                      # Dry run, show top 10 losers
    python buy_top_losers.py --execute            # Buy top 5 losers with GTT
    python buy_top_losers.py --top 10 --execute   # Buy top 10 losers
    python buy_top_losers.py --amount 50000       # Rs. 50,000 per stock
    python buy_top_losers.py --min-loss 2         # Only stocks with 2%+ loss
    python buy_top_losers.py --sl-pct 1 --target-pct 2  # 1% SL, 2% Target
    python buy_top_losers.py --no-gtt             # Buy without GTT protection
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# NIFTY 50 stocks
NIFTY_50 = [
    'ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK',
    'BAJAJ-AUTO', 'BAJFINANCE', 'BAJAJFINSV', 'BEL', 'BPCL',
    'BHARTIARTL', 'BRITANNIA', 'CIPLA', 'COALINDIA', 'DRREDDY',
    'EICHERMOT', 'ETERNAL', 'GRASIM', 'HCLTECH', 'HDFCBANK',
    'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK',
    'ITC', 'INDUSINDBK', 'INFY', 'JSWSTEEL', 'KOTAKBANK',
    'LT', 'M&M', 'MARUTI', 'NTPC', 'NESTLEIND',
    'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE', 'SHRIRAMFIN',
    'SBIN', 'SUNPHARMA', 'TCS', 'TATACONSUM', 'TATAMOTORS',
    'TATASTEEL', 'TECHM', 'TITAN', 'ULTRACEMCO', 'WIPRO'
]

# Global tick size map
TICK_SIZE_MAP: Dict[str, float] = {}

# GTT OCO Settings
DEFAULT_SL_PCT = 1.0      # 1% stop loss
DEFAULT_TARGET_PCT = 2.0  # 2% target profit
SL_EXECUTION_BUFFER = 0.01  # 1% below trigger for gap-down fill


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


def get_top_losers(kite: KiteConnect, symbols: List[str], exchange: str = "NSE") -> List[dict]:
    """
    Get stocks sorted by loss percentage (most negative first).
    
    Returns list of dicts with: symbol, last_price, prev_close, change, change_pct
    """
    try:
        instruments = [f"{exchange}:{s}" for s in symbols]
        data = kite.ohlc(instruments)
        
        results = []
        for s in symbols:
            key = f"{exchange}:{s}"
            quote = data.get(key)
            if not isinstance(quote, dict):
                continue
            
            last_price = float(quote.get("last_price", 0) or 0)
            ohlc = quote.get("ohlc") or {}
            prev_close = float(ohlc.get("close", 0) or 0)
            
            if last_price <= 0 or prev_close <= 0:
                continue
            
            change = last_price - prev_close
            change_pct = (change / prev_close) * 100
            
            results.append({
                "symbol": s,
                "last_price": last_price,
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct
            })
        
        # Sort by change_pct ascending (top losers first - most negative)
        results.sort(key=lambda x: x["change_pct"])
        return results
        
    except Exception as e:
        logger.error(f"Error fetching OHLC data: {e}")
        return []


def place_buy_order(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    cmp: float,
    dry_run: bool = True
) -> Optional[dict]:
    """Place a limit buy order at slightly above CMP."""
    try:
        tick = get_tick_size(symbol)
        limit_price = round_to_tick(cmp * 1.005, tick)  # 0.5% above CMP
        
        if dry_run:
            logger.info(f"[DRY RUN] BUY: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f}")
            return {"status": "dry_run", "symbol": symbol, "price": limit_price, "quantity": quantity}
        
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
        
        logger.info(f"[OK] BUY: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f} | Order ID: {order_response}")
        return {"order_id": order_response, "symbol": symbol, "price": limit_price, "quantity": quantity}
        
    except Exception as e:
        logger.error(f"[FAIL] BUY Error for {symbol}: {e}")
        return None


def place_gtt_oco(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    buy_price: float,
    sl_pct: float,
    target_pct: float,
    exchange: str = "NSE",
    dry_run: bool = True
) -> Optional[dict]:
    """
    Place GTT OCO (One Cancels Other) order for market protection.
    Sells if price drops below SL OR rises above target.
    """
    try:
        tick = get_tick_size(symbol)
        
        # Calculate SL trigger and limit
        sl_trigger = round_to_tick(buy_price * (1 - sl_pct / 100), tick)
        sl_limit = round_to_tick(sl_trigger * (1 - SL_EXECUTION_BUFFER), tick)
        
        # Calculate Target trigger and limit
        target_trigger = round_to_tick(buy_price * (1 + target_pct / 100), tick)
        target_limit = round_to_tick(target_trigger, tick)
        
        if dry_run:
            logger.info(
                f"[DRY RUN] GTT OCO: {symbol:15} x {quantity:>5} | "
                f"SL: Rs.{sl_trigger:,.2f} (-{sl_pct}%) | "
                f"Target: Rs.{target_trigger:,.2f} (+{target_pct}%)"
            )
            return {"status": "dry_run", "symbol": symbol}
        
        # OCO orders (two legs)
        oco_orders = [
            {  # Leg 1: Stop Loss
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                "quantity": quantity,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "product": kite.PRODUCT_CNC,
                "price": sl_limit
            },
            {  # Leg 2: Profit Target
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": kite.TRANSACTION_TYPE_SELL,
                "quantity": quantity,
                "order_type": kite.ORDER_TYPE_LIMIT,
                "product": kite.PRODUCT_CNC,
                "price": target_limit
            }
        ]
        
        # Place GTT OCO order
        gtt_response = kite.place_gtt(
            trigger_type=kite.GTT_TYPE_OCO,
            tradingsymbol=symbol,
            exchange=exchange,
            trigger_values=[sl_trigger, target_trigger],
            last_price=round_to_tick(buy_price, tick),
            orders=oco_orders
        )
        
        gtt_id = gtt_response.get('trigger_id', gtt_response)
        logger.info(
            f"[OK] GTT OCO: {symbol:15} | "
            f"SL: Rs.{sl_trigger:,.2f} | Target: Rs.{target_trigger:,.2f} | GTT ID: {gtt_id}"
        )
        return {"gtt_id": gtt_id, "symbol": symbol}
        
    except Exception as e:
        logger.error(f"[FAIL] GTT OCO Error for {symbol}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Buy top losing stocks with GTT OCO protection (contrarian dip buying)')
    parser.add_argument('--execute', action='store_true', help='Actually place orders (default is dry run)')
    parser.add_argument('--top', type=int, default=5, help='Number of top losers to buy (default: 5)')
    parser.add_argument('--amount', type=float, default=25000, help='Amount per stock in Rs (default: 25000)')
    parser.add_argument('--min-loss', type=float, default=0.5, dest='min_loss', help='Minimum loss %% to consider (default: 0.5)')
    parser.add_argument('--symbols', type=str, help='Comma-separated symbols (default: NIFTY 50)')
    parser.add_argument('--sl-pct', type=float, default=DEFAULT_SL_PCT, dest='sl_pct', help=f'Stop loss percentage (default: {DEFAULT_SL_PCT})')
    parser.add_argument('--target-pct', type=float, default=DEFAULT_TARGET_PCT, dest='target_pct', help=f'Target profit percentage (default: {DEFAULT_TARGET_PCT})')
    parser.add_argument('--no-gtt', action='store_true', dest='no_gtt', help='Skip GTT OCO orders (buy only)')
    args = parser.parse_args()
    
    dry_run = not args.execute
    top_n = args.top
    amount_per_stock = args.amount
    min_loss_pct = args.min_loss
    sl_pct = args.sl_pct
    target_pct = args.target_pct
    skip_gtt = args.no_gtt
    
    # Parse custom symbols if provided
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]
    else:
        symbols = NIFTY_50
    
    print("=" * 100)
    print("BUY TOP LOSERS WITH GTT OCO PROTECTION (Contrarian Dip Buying)")
    print("=" * 100)
    print(f"Mode: {'DRY RUN' if dry_run else '** LIVE EXECUTION **'}")
    print(f"Universe: {len(symbols)} stocks")
    print(f"Top N to buy: {top_n}")
    print(f"Amount per stock: Rs. {amount_per_stock:,.0f}")
    print(f"Min loss required: {min_loss_pct}%")
    print(f"Stop Loss: {sl_pct}% | Target: {target_pct}%")
    print(f"GTT OCO: {'DISABLED' if skip_gtt else 'ENABLED'}")
    print()
    
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
    
    # Fetch tick sizes
    logger.info("Fetching tick sizes...")
    fetch_tick_sizes(kite, "NSE")
    
    # Get top losers
    logger.info(f"Fetching OHLC for {len(symbols)} stocks...")
    losers = get_top_losers(kite, symbols)
    
    if not losers:
        logger.error("No data retrieved")
        return
    
    # Display all losers (negative change stocks)
    print()
    print("-" * 80)
    print(f"{'Rank':<6} {'Symbol':<15} {'LTP':>12} {'Prev Close':>12} {'Change':>10} {'Change%':>10}")
    print("-" * 80)
    
    for i, g in enumerate(losers[:20], 1):  # Show top 20 losers
        sign = "+" if g['change'] >= 0 else ""
        print(f"{i:<6} {g['symbol']:<15} {g['last_price']:>12,.2f} {g['prev_close']:>12,.2f} {sign}{g['change']:>9,.2f} {sign}{g['change_pct']:>9.2f}%")
    
    # Filter by min loss (stocks with negative change >= min_loss)
    qualified = [g for g in losers if g['change_pct'] <= -min_loss_pct]
    
    if not qualified:
        print(f"\nNo stocks with loss >= {min_loss_pct}%")
        return
    
    # Select top N losers
    to_buy = qualified[:top_n]
    
    print()
    print("=" * 80)
    print(f"BUYING TOP {len(to_buy)} LOSERS (min {min_loss_pct}% loss)")
    print("=" * 80)
    
    if not dry_run:
        confirm = input("WARNING: This will place REAL orders. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted.")
            return
    
    # Place orders
    results = {'buy_success': [], 'buy_failed': [], 'gtt_success': [], 'gtt_failed': []}
    total_invested = 0
    
    print()
    print("-" * 100)
    print(f"{'Symbol':<15} {'Qty':>6} {'Price':>12} {'Amount':>15} {'Loss%':>10} {'SL':>12} {'Target':>12}")
    print("-" * 100)
    
    for g in to_buy:
        symbol = g['symbol']
        cmp = g['last_price']
        quantity = max(1, int(amount_per_stock // cmp))
        investment = quantity * cmp
        tick = get_tick_size(symbol)
        sl_price = round_to_tick(cmp * 1.005 * (1 - sl_pct / 100), tick)
        target_price = round_to_tick(cmp * 1.005 * (1 + target_pct / 100), tick)
        
        print(f"{symbol:<15} {quantity:>6} {cmp:>12,.2f} {investment:>15,.2f} {g['change_pct']:>9.2f}% {sl_price:>12,.2f} {target_price:>12,.2f}")
        
        # Place BUY order
        buy_result = place_buy_order(
            kite=kite,
            symbol=symbol,
            quantity=quantity,
            cmp=cmp,
            dry_run=dry_run
        )
        
        if buy_result:
            results['buy_success'].append(symbol)
            total_invested += investment
            buy_price = buy_result.get('price', cmp * 1.005)
            
            # Place GTT OCO order (if not skipped)
            if not skip_gtt:
                gtt_result = place_gtt_oco(
                    kite=kite,
                    symbol=symbol,
                    quantity=quantity,
                    buy_price=buy_price,
                    sl_pct=sl_pct,
                    target_pct=target_pct,
                    dry_run=dry_run
                )
                if gtt_result:
                    results['gtt_success'].append(symbol)
                else:
                    results['gtt_failed'].append(symbol)
        else:
            results['buy_failed'].append(symbol)
        
        if not dry_run:
            time.sleep(0.3)
    
    # Summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"BUY orders placed: {len(results['buy_success'])}")
    print(f"BUY failed: {len(results['buy_failed'])}")
    if not skip_gtt:
        print(f"GTT OCO placed: {len(results['gtt_success'])}")
        print(f"GTT failed: {len(results['gtt_failed'])}")
    print(f"Total invested: Rs. {total_invested:,.2f}")
    
    if results['buy_failed']:
        print(f"Failed BUY symbols: {', '.join(results['buy_failed'])}")
    if results['gtt_failed']:
        print(f"Failed GTT symbols: {', '.join(results['gtt_failed'])}")
    
    if dry_run:
        print("\n** This was a DRY RUN. No orders were placed. **")
        print("   Run with --execute to place actual orders.")


if __name__ == "__main__":
    main()
