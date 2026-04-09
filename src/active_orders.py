"""
View and Cancel Active Orders - Shows today's pending orders

This script:
1. Fetches today's orders from Kite
2. Shows active/pending orders
3. Optionally cancels orders

Usage:
    python active_orders.py                       # Show active orders
    python active_orders.py --cancel              # Cancel all active orders
    python active_orders.py --cancel --symbol SBIN  # Cancel specific symbol
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


def get_active_orders(kite: KiteConnect) -> List[dict]:
    """Get today's active/pending orders."""
    try:
        orders = kite.orders()
        active = []
        
        for o in orders:
            status = o.get('status', '').upper()
            # Active statuses: OPEN, PENDING, TRIGGER PENDING
            if status in ['OPEN', 'PENDING', 'TRIGGER PENDING', 'AMO REQ RECEIVED']:
                active.append({
                    'order_id': o.get('order_id'),
                    'symbol': o.get('tradingsymbol', ''),
                    'exchange': o.get('exchange', 'NSE'),
                    'transaction_type': o.get('transaction_type', ''),
                    'quantity': int(o.get('quantity', 0) or 0),
                    'price': float(o.get('price', 0) or 0),
                    'trigger_price': float(o.get('trigger_price', 0) or 0),
                    'order_type': o.get('order_type', ''),
                    'product': o.get('product', ''),
                    'status': status,
                    'placed_at': o.get('order_timestamp', ''),
                    'variety': o.get('variety', '')
                })
        
        return active
        
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return []


def cancel_order(kite: KiteConnect, order_id: str, variety: str = 'regular', dry_run: bool = True) -> bool:
    """Cancel an order."""
    try:
        if dry_run:
            logger.info(f"[DRY RUN] Would cancel order: {order_id}")
            return True
        
        kite.cancel_order(variety=variety, order_id=order_id)
        logger.info(f"[OK] Cancelled order: {order_id}")
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] Cancel error for {order_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='View and cancel active orders')
    parser.add_argument('--cancel', action='store_true', help='Cancel active orders')
    parser.add_argument('--execute', action='store_true', help='Actually cancel (default is dry run)')
    parser.add_argument('--symbol', type=str, help='Filter by symbol')
    parser.add_argument('--buy-only', action='store_true', dest='buy_only', help='Only BUY orders')
    parser.add_argument('--sell-only', action='store_true', dest='sell_only', help='Only SELL orders')
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    print("=" * 80)
    print("ACTIVE ORDERS")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.cancel:
        print(f"Mode: {'DRY RUN CANCEL' if dry_run else '** CANCELLING ORDERS **'}")
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
    
    # Get active orders
    logger.info("Fetching orders...")
    orders = get_active_orders(kite)
    
    if not orders:
        print("No active orders found")
        return
    
    # Apply filters
    if args.symbol:
        orders = [o for o in orders if o['symbol'].upper() == args.symbol.upper()]
    if args.buy_only:
        orders = [o for o in orders if o['transaction_type'] == 'BUY']
    if args.sell_only:
        orders = [o for o in orders if o['transaction_type'] == 'SELL']
    
    if not orders:
        print("No orders match the filter criteria")
        return
    
    # Display orders
    print("-" * 120)
    print(f"{'Order ID':<20} {'Symbol':<15} {'Type':<6} {'Qty':>8} {'Price':>12} {'Trigger':>12} {'Status':<18} {'Product':<8}")
    print("-" * 120)
    
    total_buy_value = 0
    total_sell_value = 0
    
    for o in orders:
        price_str = f"{o['price']:,.2f}" if o['price'] > 0 else "MARKET"
        trigger_str = f"{o['trigger_price']:,.2f}" if o['trigger_price'] > 0 else "-"
        
        value = o['quantity'] * o['price'] if o['price'] > 0 else 0
        if o['transaction_type'] == 'BUY':
            total_buy_value += value
        else:
            total_sell_value += value
        
        print(f"{o['order_id']:<20} {o['symbol']:<15} {o['transaction_type']:<6} {o['quantity']:>8} {price_str:>12} {trigger_str:>12} {o['status']:<18} {o['product']:<8}")
    
    print("-" * 120)
    print(f"Total Orders: {len(orders)} | Buy Value: Rs.{total_buy_value:,.2f} | Sell Value: Rs.{total_sell_value:,.2f}")
    
    # Cancel if requested
    if args.cancel:
        print()
        print("=" * 80)
        print(f"CANCELLING {len(orders)} ORDERS")
        print("=" * 80)
        
        if not dry_run:
            confirm = input("WARNING: This will CANCEL all listed orders. Type 'YES' to confirm: ")
            if confirm != 'YES':
                print("Aborted.")
                return
        
        results = {'success': 0, 'failed': 0}
        
        for o in orders:
            success = cancel_order(
                kite=kite,
                order_id=o['order_id'],
                variety=o['variety'] or 'regular',
                dry_run=dry_run
            )
            
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
            
            if not dry_run:
                time.sleep(0.2)
        
        print()
        print(f"Cancelled: {results['success']} | Failed: {results['failed']}")
        
        if dry_run:
            print("\n** This was a DRY RUN. No orders were cancelled. **")
            print("   Run with --execute to actually cancel.")


if __name__ == "__main__":
    main()
