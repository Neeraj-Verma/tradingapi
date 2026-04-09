"""
Sell Today's Positions based on Loss/Profit thresholds

This script:
1. Fetches today's positions from Kite
2. Sells if:
   - Loss >= Rs.1000 (default, configurable via --max-loss)
   - OR Profit >= 2% (default, configurable via --min-profit)

Usage:
    python sell_loss_profit_positions.py                           # Show qualifying positions
    python sell_loss_profit_positions.py --execute                 # Sell positions meeting criteria
    python sell_loss_profit_positions.py --max-loss 500            # Sell if loss >= Rs.500
    python sell_loss_profit_positions.py --min-profit 3            # Sell if profit >= 3%
    python sell_loss_profit_positions.py --max-loss 1000 --min-profit 2 --execute
"""

import os
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


def should_sell(position: dict, max_loss: float, min_profit_pct: float) -> tuple[bool, str]:
    """
    Check if position should be sold based on loss/profit criteria.
    Returns (should_sell, reason)
    """
    pnl = position['pnl']
    pnl_pct = position['pnl_pct']
    
    # Sell if loss >= max_loss (e.g., -1000)
    if pnl <= -max_loss:
        return True, f"LOSS >= Rs.{max_loss}"
    
    # Sell if profit >= min_profit_pct (e.g., 2%)
    if pnl_pct >= min_profit_pct:
        return True, f"PROFIT >= {min_profit_pct}%"
    
    return False, ""


def main():
    parser = argparse.ArgumentParser(description="Sell positions based on loss/profit thresholds")
    parser.add_argument('--execute', action='store_true', help='Actually place orders (default is dry run)')
    parser.add_argument('--max-loss', type=float, default=1000, dest='max_loss',
                        help='Sell if loss >= this amount in Rs (default: 1000)')
    parser.add_argument('--min-profit', type=float, default=2.0, dest='min_profit',
                        help='Sell if profit >= this percentage (default: 2.0)')
    parser.add_argument('--symbol', type=str, help='Check specific symbol only')
    args = parser.parse_args()
    
    dry_run = not args.execute
    max_loss = args.max_loss
    min_profit_pct = args.min_profit
    
    print("=" * 120)
    print("SELL POSITIONS - LOSS/PROFIT THRESHOLD")
    print("=" * 120)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'DRY RUN' if dry_run else '** LIVE EXECUTION **'}")
    print(f"Criteria: Sell if LOSS >= Rs.{max_loss:,.0f} OR PROFIT >= {min_profit_pct}%")
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
        print("No open positions found for today")
        return
    
    # Filter by symbol if specified
    if args.symbol:
        positions = [p for p in positions if p['symbol'].upper() == args.symbol.upper()]
        if not positions:
            print(f"Symbol {args.symbol} not found in today's positions")
            return
    
    # Display all positions with sell status
    print("-" * 140)
    print(f"{'Symbol':<15} {'Prod':<5} {'Qty':>8} {'Avg':>12} {'LTP':>12} {'P&L':>12} {'P&L%':>10} {'Value':>15} {'SELL?':<20}")
    print("-" * 140)
    
    total_value = 0
    total_pnl = 0
    positions_to_sell = []
    
    for p in positions:
        sign = "+" if p['pnl'] >= 0 else ""
        sell, reason = should_sell(p, max_loss, min_profit_pct)
        sell_status = f"YES - {reason}" if sell else "NO"
        
        if sell:
            positions_to_sell.append({**p, 'sell_reason': reason})
        
        print(f"{p['symbol']:<15} {p['product']:<5} {p['quantity']:>8} {p['avg_price']:>12,.2f} {p['last_price']:>12,.2f} {sign}{p['pnl']:>11,.2f} {sign}{p['pnl_pct']:>9.2f}% {p['value']:>15,.2f} {sell_status:<20}")
        total_value += p['value']
        total_pnl += p['pnl']
    
    print("-" * 140)
    sign = "+" if total_pnl >= 0 else ""
    print(f"{'TOTAL':<15} {'':<5} {'':<8} {'':<12} {'':<12} {sign}{total_pnl:>11,.2f} {'':<10} {total_value:>15,.2f}")
    print()
    
    # Summary of positions to sell
    if not positions_to_sell:
        print("=" * 60)
        print("No positions meet the sell criteria")
        print("=" * 60)
        return
    
    sell_pnl = sum(p['pnl'] for p in positions_to_sell)
    sell_value = sum(p['value'] for p in positions_to_sell)
    
    print("=" * 120)
    print(f"POSITIONS TO SELL: {len(positions_to_sell)}")
    print(f"Total Value: Rs.{sell_value:,.2f}")
    print(f"Combined P&L: Rs.{sell_pnl:,.2f}")
    print("=" * 120)
    
    # Confirmation for live execution
    if not dry_run:
        confirm = input("\nWARNING: This will place REAL SELL orders. Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted.")
            return
    
    # Place sell orders
    print()
    successful = 0
    failed = 0
    
    for p in positions_to_sell:
        print(f"\nProcessing: {p['symbol']} ({p['sell_reason']})")
        result = place_sell_order(
            kite=kite,
            symbol=p['symbol'],
            quantity=p['quantity'],
            cmp=p['last_price'],
            product=p['product'],
            exchange=p['exchange'],
            dry_run=dry_run
        )
        if result:
            successful += 1
        else:
            failed += 1
    
    # Final summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total positions checked: {len(positions)}")
    print(f"Positions meeting criteria: {len(positions_to_sell)}")
    print(f"Sell orders placed: {successful}")
    print(f"Failed orders: {failed}")
    
    if dry_run:
        print()
        print("** This was a DRY RUN. No orders were placed. **")
        print("   Run with --execute to place actual orders.")


if __name__ == "__main__":
    main()
