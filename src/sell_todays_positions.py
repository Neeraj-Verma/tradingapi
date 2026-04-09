"""
Sell Today's Positions - Sell stocks bought today (intraday/CNC positions)

This script:
1. Fetches today's positions from Kite
2. Shows day positions (stocks bought today)
3. Places sell orders to square off

Usage:
    python sell_todays_positions.py                   # Show today's positions
    python sell_todays_positions.py --execute         # Sell all today's buys
    python sell_todays_positions.py --symbol SBIN     # Sell specific symbol
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


def get_todays_positions(kite: KiteConnect) -> List[dict]:
    """Get today's positions (day positions with quantity > 0)."""
    try:
        positions = kite.positions()
        day_positions = positions.get('day', [])
        
        results = []
        for p in day_positions:
            symbol = p.get('tradingsymbol', '')
            quantity = int(p.get('quantity', 0) or 0)
            
            # Only include positions with quantity > 0 (long positions to sell)
            if quantity <= 0:
                continue
            
            buy_quantity = int(p.get('buy_quantity', 0) or 0)
            sell_quantity = int(p.get('sell_quantity', 0) or 0)
            avg_price = float(p.get('average_price', 0) or 0)
            last_price = float(p.get('last_price', 0) or 0)
            pnl = float(p.get('pnl', 0) or 0)
            day_buy_value = float(p.get('day_buy_value', 0) or 0)
            product = p.get('product', 'CNC')
            
            pnl_pct = 0
            if avg_price > 0:
                pnl_pct = ((last_price - avg_price) / avg_price) * 100
            
            results.append({
                'symbol': symbol,
                'exchange': p.get('exchange', 'NSE'),
                'quantity': quantity,
                'buy_quantity': buy_quantity,
                'sell_quantity': sell_quantity,
                'avg_price': avg_price,
                'last_price': last_price,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'product': product,
                'value': quantity * last_price,
                'day_buy_value': day_buy_value
            })
        
        # Sort by P&L percentage
        results.sort(key=lambda x: x['pnl_pct'])
        return results
        
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return []


def place_sell_order(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    cmp: float,
    product: str = 'CNC',
    exchange: str = 'NSE',
    dry_run: bool = True
) -> Optional[dict]:
    """Place a limit sell order at slightly below CMP."""
    try:
        tick = get_tick_size(symbol)
        # Sell at 0.3% below CMP to ensure quick fill
        limit_price = round_to_tick(cmp * 0.997, tick)
        
        # Map product type
        product_type = kite.PRODUCT_CNC if product == 'CNC' else kite.PRODUCT_MIS
        
        if dry_run:
            logger.info(f"[DRY RUN] SELL: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f} ({product})")
            return {"status": "dry_run", "symbol": symbol}
        
        order_response = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=exchange,
            tradingsymbol=symbol,
            transaction_type=kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            order_type=kite.ORDER_TYPE_LIMIT,
            product=product_type,
            price=limit_price
        )
        
        logger.info(f"[OK] SELL: {symbol:15} x {quantity:>5} @ Rs.{limit_price:,.2f} | Order ID: {order_response}")
        return {"order_id": order_response, "symbol": symbol}
        
    except Exception as e:
        logger.error(f"[FAIL] SELL Error for {symbol}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Sell today's positions")
    parser.add_argument('--execute', action='store_true', help='Actually place orders (default is dry run)')
    parser.add_argument('--symbol', type=str, help='Sell specific symbol only')
    parser.add_argument('--profit-only', action='store_true', dest='profit_only', help='Sell only profitable positions')
    parser.add_argument('--loss-only', action='store_true', dest='loss_only', help='Sell only loss-making positions')
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    print("=" * 100)
    print("SELL TODAY'S POSITIONS")
    print("=" * 100)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'DRY RUN' if dry_run else '** LIVE EXECUTION **'}")
    if args.symbol:
        print(f"Symbol filter: {args.symbol.upper()}")
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
    
    # Get today's positions
    logger.info("Fetching today's positions...")
    positions = get_todays_positions(kite)
    
    if not positions:
        print("No positions to sell (no stocks bought today with open quantity)")
        return
    
    # Display all positions
    print("-" * 120)
    print(f"{'Symbol':<15} {'Product':<6} {'Qty':>8} {'Avg Price':>12} {'LTP':>12} {'P&L':>12} {'P&L%':>10} {'Value':>15}")
    print("-" * 120)
    
    total_value = 0
    total_pnl = 0
    
    for p in positions:
        sign = "+" if p['pnl'] >= 0 else ""
        print(f"{p['symbol']:<15} {p['product']:<6} {p['quantity']:>8} {p['avg_price']:>12,.2f} {p['last_price']:>12,.2f} {sign}{p['pnl']:>11,.2f} {sign}{p['pnl_pct']:>9.2f}% {p['value']:>15,.2f}")
        total_value += p['value']
        total_pnl += p['pnl']
    
    print("-" * 120)
    sign = "+" if total_pnl >= 0 else ""
    print(f"{'TOTAL':<15} {'':<6} {'':<8} {'':<12} {'':<12} {sign}{total_pnl:>11,.2f} {'':<10} {total_value:>15,.2f}")
    
    # Apply filters
    to_sell = positions
    
    if args.symbol:
        to_sell = [p for p in positions if p['symbol'].upper() == args.symbol.upper()]
        if not to_sell:
            print(f"\nSymbol {args.symbol} not found in today's positions")
            return
    
    if args.profit_only:
        to_sell = [p for p in to_sell if p['pnl'] > 0]
    if args.loss_only:
        to_sell = [p for p in to_sell if p['pnl'] < 0]
    
    if not to_sell:
        print("\nNo positions match the filter criteria")
        return
    
    print()
    print("=" * 100)
    print(f"SELLING {len(to_sell)} POSITIONS")
    print("=" * 100)
    
    if not dry_run:
        confirm = input("WARNING: This will SELL all listed positions. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted.")
            return
    
    # Place sell orders
    results = {'success': [], 'failed': []}
    total_sold = 0
    realized_pnl = 0
    
    print()
    print("-" * 100)
    print(f"{'Symbol':<15} {'Qty':>8} {'LTP':>12} {'Value':>15} {'P&L':>12} {'P&L%':>10}")
    print("-" * 100)
    
    for p in to_sell:
        symbol = p['symbol']
        quantity = p['quantity']
        cmp = p['last_price']
        value = p['value']
        product = p['product']
        exchange = p['exchange']
        
        sign = "+" if p['pnl'] >= 0 else ""
        print(f"{symbol:<15} {quantity:>8} {cmp:>12,.2f} {value:>15,.2f} {sign}{p['pnl']:>11,.2f} {sign}{p['pnl_pct']:>9.2f}%")
        
        result = place_sell_order(
            kite=kite,
            symbol=symbol,
            quantity=quantity,
            cmp=cmp,
            product=product,
            exchange=exchange,
            dry_run=dry_run
        )
        
        if result:
            results['success'].append(symbol)
            total_sold += value
            realized_pnl += p['pnl']
        else:
            results['failed'].append(symbol)
        
        if not dry_run:
            time.sleep(0.3)
    
    # Summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"Sell orders placed: {len(results['success'])}")
    print(f"Failed: {len(results['failed'])}")
    print(f"Total value: Rs. {total_sold:,.2f}")
    sign = "+" if realized_pnl >= 0 else ""
    print(f"Expected P&L: {sign}Rs. {realized_pnl:,.2f}")
    
    if results['failed']:
        print(f"Failed symbols: {', '.join(results['failed'])}")
    
    if dry_run:
        print("\n** This was a DRY RUN. No orders were placed. **")
        print("   Run with --execute to place actual orders.")


if __name__ == "__main__":
    main()
