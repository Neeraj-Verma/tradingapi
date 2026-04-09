"""
Sell All Holdings - Liquidate all CNC holdings at market price

This script:
1. Fetches all CNC holdings from Kite
2. Places sell orders for all holdings at limit price (slightly below CMP)

Usage:
    python sell_all_holdings.py                   # Dry run, show holdings
    python sell_all_holdings.py --execute         # Sell all holdings
    python sell_all_holdings.py --symbol SBIN     # Sell specific symbol only
    python sell_all_holdings.py --negative-only   # Sell only loss-making holdings
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

# Global tick size map
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


def get_holdings(kite: KiteConnect) -> List[dict]:
    """Get all CNC holdings with P&L info."""
    try:
        holdings = kite.holdings()
        results = []
        
        for h in holdings:
            symbol = h.get('tradingsymbol', '')
            quantity = int(h.get('quantity', 0) or 0)
            
            if quantity <= 0:
                continue
            
            avg_price = float(h.get('average_price', 0) or 0)
            last_price = float(h.get('last_price', 0) or 0)
            pnl = float(h.get('pnl', 0) or 0)
            
            pnl_pct = 0
            if avg_price > 0:
                pnl_pct = ((last_price - avg_price) / avg_price) * 100
            
            results.append({
                'symbol': symbol,
                'quantity': quantity,
                'avg_price': avg_price,
                'last_price': last_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'value': quantity * last_price
            })
        
        # Sort by P&L (most negative first)
        results.sort(key=lambda x: x['pnl_pct'])
        return results
        
    except Exception as e:
        logger.error(f"Error fetching holdings: {e}")
        return []


def place_sell_order(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    cmp: float,
    dry_run: bool = True
) -> Optional[dict]:
    """Place a limit sell order at slightly below CMP."""
    try:
        tick = get_tick_size(symbol)
        # Sell at 0.5% below CMP to ensure fill
        limit_price = round_to_tick(cmp * 0.995, tick)
        
        if dry_run:
            logger.info(f"[DRY RUN] SELL: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f}")
            return {"status": "dry_run", "symbol": symbol}
        
        order_response = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange="NSE",
            tradingsymbol=symbol,
            transaction_type=kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            order_type=kite.ORDER_TYPE_LIMIT,
            product=kite.PRODUCT_CNC,
            price=limit_price
        )
        
        logger.info(f"[OK] SELL: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f} | Order ID: {order_response}")
        return {"order_id": order_response, "symbol": symbol}
        
    except Exception as e:
        logger.error(f"[FAIL] SELL Error for {symbol}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Sell all holdings')
    parser.add_argument('--execute', action='store_true', help='Actually place orders (default is dry run)')
    parser.add_argument('--symbol', type=str, help='Sell specific symbol only')
    parser.add_argument('--negative-only', action='store_true', dest='negative_only', help='Sell only loss-making holdings')
    parser.add_argument('--min-loss', type=float, default=0, dest='min_loss', help='Min loss %% to sell (with --negative-only)')
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    print("=" * 80)
    print("SELL ALL HOLDINGS")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if dry_run else '** LIVE EXECUTION **'}")
    if args.negative_only:
        print(f"Filter: Negative holdings only (loss >= {args.min_loss}%)")
    if args.symbol:
        print(f"Symbol: {args.symbol.upper()}")
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
    
    # Get holdings
    logger.info("Fetching holdings...")
    holdings = get_holdings(kite)
    
    if not holdings:
        print("No holdings found")
        return
    
    # Display all holdings
    print()
    print("-" * 100)
    print(f"{'Symbol':<15} {'Qty':>8} {'Avg Price':>12} {'LTP':>12} {'P&L':>12} {'P&L%':>10} {'Value':>15}")
    print("-" * 100)
    
    total_value = 0
    total_pnl = 0
    
    for h in holdings:
        sign = "+" if h['pnl'] >= 0 else ""
        print(f"{h['symbol']:<15} {h['quantity']:>8} {h['avg_price']:>12,.2f} {h['last_price']:>12,.2f} {sign}{h['pnl']:>11,.2f} {sign}{h['pnl_pct']:>9.2f}% {h['value']:>15,.2f}")
        total_value += h['value']
        total_pnl += h['pnl']
    
    print("-" * 100)
    sign = "+" if total_pnl >= 0 else ""
    print(f"{'TOTAL':<15} {'':<8} {'':<12} {'':<12} {sign}{total_pnl:>11,.2f} {'':<10} {total_value:>15,.2f}")
    
    # Filter holdings
    to_sell = holdings
    
    if args.symbol:
        to_sell = [h for h in holdings if h['symbol'].upper() == args.symbol.upper()]
        if not to_sell:
            print(f"\nSymbol {args.symbol} not found in holdings")
            return
    
    if args.negative_only:
        to_sell = [h for h in to_sell if h['pnl_pct'] <= -args.min_loss]
        if not to_sell:
            print(f"\nNo holdings with loss >= {args.min_loss}%")
            return
    
    print()
    print("=" * 80)
    print(f"SELLING {len(to_sell)} HOLDINGS")
    print("=" * 80)
    
    if not dry_run:
        confirm = input("WARNING: This will SELL all listed holdings. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted.")
            return
    
    # Place sell orders
    results = {'success': [], 'failed': []}
    total_sold = 0
    
    print()
    print("-" * 80)
    print(f"{'Symbol':<15} {'Qty':>8} {'LTP':>12} {'Value':>15} {'P&L%':>10}")
    print("-" * 80)
    
    for h in to_sell:
        symbol = h['symbol']
        quantity = h['quantity']
        cmp = h['last_price']
        value = h['value']
        
        sign = "+" if h['pnl_pct'] >= 0 else ""
        print(f"{symbol:<15} {quantity:>8} {cmp:>12,.2f} {value:>15,.2f} {sign}{h['pnl_pct']:>9.2f}%")
        
        result = place_sell_order(
            kite=kite,
            symbol=symbol,
            quantity=quantity,
            cmp=cmp,
            dry_run=dry_run
        )
        
        if result:
            results['success'].append(symbol)
            total_sold += value
        else:
            results['failed'].append(symbol)
        
        if not dry_run:
            time.sleep(0.3)
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Sell orders placed: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")
    print(f"Total value: Rs. {total_sold:,.2f}")
    
    if results['failed']:
        print(f"Failed symbols: {', '.join(results['failed'])}")
    
    if dry_run:
        print("\n** This was a DRY RUN. No orders were placed. **")
        print("   Run with --execute to place actual orders.")


if __name__ == "__main__":
    main()
