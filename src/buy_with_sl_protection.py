"""
Buy Stocks with GTT OCO Protection (Stop Loss + Target)

This script:
1. Fetches LTP for specified stocks
2. Calculates quantity based on budget per stock
3. Places BUY orders (LIMIT at 0.5% above CMP)
4. Places GTT OCO orders: Sell if loss >= SL% OR profit >= Target%

Usage:
    python buy_with_sl_protection.py --symbols POWERMECH,SOLARINDS,MAZDOCK --budget 100000
    python buy_with_sl_protection.py --symbols POWERMECH,SOLARINDS,MAZDOCK --budget 100000 --execute
    python buy_with_sl_protection.py --symbols SBIN --sl-pct 1 --target-pct 2   # 1% SL, 2% Target
    python buy_with_sl_protection.py --symbols SBIN --no-gtt                     # Buy only, no GTT
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

# Default Stop Loss percentage
DEFAULT_SL_PCT = 5.0  # 5% below buy price
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


def get_ltp(kite: KiteConnect, symbols: List[str], exchange: str = "NSE") -> Dict[str, float]:
    """Fetch LTP for given symbols."""
    try:
        instruments = [f"{exchange}:{s}" for s in symbols]
        ltp_data = kite.ltp(instruments)
        
        result = {}
        for sym in symbols:
            key = f"{exchange}:{sym}"
            ltp = ltp_data.get(key, {}).get('last_price', 0)
            if ltp > 0:
                result[sym] = float(ltp)
            else:
                logger.warning(f"Could not fetch LTP for {sym}")
        
        return result
    except Exception as e:
        logger.error(f"Error fetching LTP: {e}")
        return {}


def place_buy_order(
    kite: KiteConnect,
    symbol: str,
    quantity: int,
    cmp: float,
    exchange: str = "NSE",
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
            exchange=exchange,
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
    
    Args:
        kite: KiteConnect instance
        symbol: Trading symbol
        quantity: Number of shares
        buy_price: Buy price (used as base for SL/Target calculation)
        sl_pct: Stop loss percentage (e.g., 1 for 1% below buy price)
        target_pct: Target percentage (e.g., 2 for 2% above buy price)
        exchange: Exchange (default NSE)
        dry_run: If True, only log without placing order
    """
    try:
        tick = get_tick_size(symbol)
        
        # Calculate SL trigger and limit
        sl_trigger = round_to_tick(buy_price * (1 - sl_pct / 100), tick)
        sl_limit = round_to_tick(sl_trigger * (1 - SL_EXECUTION_BUFFER), tick)  # 1% below trigger
        
        # Calculate Target trigger and limit
        target_trigger = round_to_tick(buy_price * (1 + target_pct / 100), tick)
        target_limit = round_to_tick(target_trigger, tick)
        
        if dry_run:
            logger.info(
                f"[DRY RUN] GTT OCO: {symbol:15} x {quantity:>5} | "
                f"Buy: Rs.{buy_price:>10,.2f} | "
                f"SL: Rs.{sl_trigger:>10,.2f} (-{sl_pct}%) | "
                f"Target: Rs.{target_trigger:>10,.2f} (+{target_pct}%)"
            )
            return {"status": "dry_run", "symbol": symbol, "sl_trigger": sl_trigger, "target_trigger": target_trigger}
        
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
            f"[OK] GTT OCO: {symbol:15} x {quantity:>5} | "
            f"SL: Rs.{sl_trigger:,.2f} (-{sl_pct}%) | "
            f"Target: Rs.{target_trigger:,.2f} (+{target_pct}%) | GTT ID: {gtt_id}"
        )
        return {"gtt_id": gtt_id, "symbol": symbol, "sl_trigger": sl_trigger, "target_trigger": target_trigger}
        
    except Exception as e:
        logger.error(f"[FAIL] GTT OCO Error for {symbol}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Buy stocks with stop loss protection')
    parser.add_argument('--execute', action='store_true', help='Actually place orders (default is dry run)')
    parser.add_argument('--symbols', type=str, required=True, help='Comma-separated symbols (e.g., POWERMECH,SOLARINDS,MAZDOCK)')
    parser.add_argument('--budget', type=float, default=100000, help='Budget per stock in Rs (default: 100000)')
    parser.add_argument('--sl-pct', type=float, default=1.0, dest='sl_pct', help='Stop loss percentage (default: 1.0)')
    parser.add_argument('--target-pct', type=float, default=2.0, dest='target_pct', help='Target profit percentage (default: 2.0)')
    parser.add_argument('--no-gtt', action='store_true', dest='no_gtt', help='Skip GTT OCO orders')
    args = parser.parse_args()
    
    dry_run = not args.execute
    symbols = [s.strip().upper() for s in args.symbols.split(',')]
    budget_per_stock = args.budget
    sl_pct = args.sl_pct
    target_pct = args.target_pct
    skip_gtt = args.no_gtt
    
    print("=" * 120)
    print("BUY WITH GTT OCO PROTECTION (SL + TARGET)")
    print("=" * 120)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'DRY RUN' if dry_run else '** LIVE EXECUTION **'}")
    print(f"Stocks: {', '.join(symbols)}")
    print(f"Budget per stock: Rs. {budget_per_stock:,.0f}")
    print(f"Stop Loss: {sl_pct}% below buy price")
    print(f"Target: {target_pct}% above buy price")
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
    
    # Get LTP for all symbols
    logger.info(f"Fetching LTP for {len(symbols)} stocks...")
    ltp_data = get_ltp(kite, symbols)
    
    if not ltp_data:
        logger.error("Could not fetch LTP data. Check if market is open and symbols are valid.")
        return
    
    # Calculate quantities and display plan
    print("-" * 130)
    print(f"{'Symbol':<15} {'LTP':>12} {'Budget':>15} {'Quantity':>10} {'Est Value':>15} {'SL (-'+str(sl_pct)+'%)':>14} {'Target (+'+str(target_pct)+'%)':>14}")
    print("-" * 130)
    
    orders_to_place = []
    total_investment = 0
    
    for sym in symbols:
        ltp = ltp_data.get(sym)
        if not ltp:
            print(f"{sym:<15} {'LTP NOT FOUND':>12} - SKIPPED")
            continue
        
        quantity = int(budget_per_stock / ltp)
        if quantity < 1:
            print(f"{sym:<15} {ltp:>12,.2f} {budget_per_stock:>15,.0f} {'TOO EXPENSIVE':>10} - SKIPPED")
            continue
        
        est_value = quantity * ltp
        sl_trigger = round_to_tick(ltp * (1 - sl_pct / 100), get_tick_size(sym))
        target_trigger = round_to_tick(ltp * (1 + target_pct / 100), get_tick_size(sym))
        
        print(f"{sym:<15} {ltp:>12,.2f} {budget_per_stock:>15,.0f} {quantity:>10} {est_value:>15,.2f} {sl_trigger:>14,.2f} {target_trigger:>14,.2f}")
        
        orders_to_place.append({
            'symbol': sym,
            'ltp': ltp,
            'quantity': quantity,
            'est_value': est_value,
            'sl_trigger': sl_trigger,
            'target_trigger': target_trigger
        })
        total_investment += est_value
    
    print("-" * 130)
    print(f"{'TOTAL':<15} {'':<12} {budget_per_stock * len(symbols):>15,.0f} {'':<10} {total_investment:>15,.2f}")
    print()
    
    if not orders_to_place:
        print("No valid orders to place.")
        return
    
    # Confirmation for live execution
    if not dry_run:
        print("\n" + "=" * 60)
        print("WARNING: This will place REAL orders!")
        print(f"Total stocks: {len(orders_to_place)}")
        print(f"Total investment: Rs. {total_investment:,.2f}")
        print("=" * 60)
        confirm = input("Type 'YES' to confirm: ")
        if confirm != 'YES':
            print("Aborted.")
            return
    
    # Place orders
    print()
    print("=" * 120)
    print("PLACING ORDERS")
    print("=" * 120)
    
    buy_results = []
    gtt_results = []
    
    for order in orders_to_place:
        sym = order['symbol']
        qty = order['quantity']
        ltp = order['ltp']
        
        # Place BUY order
        print(f"\n[{sym}] Placing BUY order...")
        buy_result = place_buy_order(
            kite=kite,
            symbol=sym,
            quantity=qty,
            cmp=ltp,
            dry_run=dry_run
        )
        
        if buy_result:
            buy_results.append(buy_result)
            buy_price = buy_result.get('price', ltp * 1.005)
            
            # Place GTT OCO order (if not skipped)
            if not skip_gtt:
                print(f"[{sym}] Placing GTT OCO (SL -{sl_pct}% / Target +{target_pct}%)...")
                gtt_result = place_gtt_oco(
                    kite=kite,
                    symbol=sym,
                    quantity=qty,
                    buy_price=buy_price,
                    sl_pct=sl_pct,
                    target_pct=target_pct,
                    dry_run=dry_run
                )
                if gtt_result:
                    gtt_results.append(gtt_result)
    
    # Final summary
    print()
    print("=" * 120)
    print("SUMMARY")
    print("=" * 120)
    print(f"BUY orders placed: {len(buy_results)}")
    print(f"GTT OCO orders placed: {len(gtt_results)}")
    print(f"Total investment: Rs. {total_investment:,.2f}")
    
    if dry_run:
        print()
        print("** This was a DRY RUN. No orders were placed. **")
        print("   Run with --execute to place actual orders.")


if __name__ == "__main__":
    main()
