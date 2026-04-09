"""
Zerodha Kite - Sell all stocks bought today
Requires: pip install kiteconnect python-dotenv

This script:
1. Fetches all orders placed today from Kite API
2. Filters for COMPLETE BUY orders
3. Places SELL orders for those stocks at MARKET price
"""

import os
from datetime import datetime
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
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Set to False for actual execution, True for dry run
DRY_RUN = True

# Order type for selling: MARKET or LIMIT
SELL_ORDER_TYPE = "MARKET"  # Use MARKET for immediate execution
LIMIT_PRICE_DISCOUNT = 0.002  # 0.2% below LTP if using LIMIT orders
# ===================================


def get_kite_client():
    """Initialize and return Kite client"""
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    return kite


def get_todays_buy_orders(kite):
    """
    Get all successfully executed BUY orders placed today
    Returns list of dicts with order details
    """
    try:
        # Get all orders for today
        orders = kite.orders()
        today = datetime.now().strftime("%Y-%m-%d")
        
        todays_buys = []
        
        for order in orders:
            # Check if order was placed today
            order_date = order.get('order_timestamp')
            if order_date:
                if isinstance(order_date, datetime):
                    order_date_str = order_date.strftime("%Y-%m-%d")
                else:
                    order_date_str = str(order_date)[:10]
            else:
                continue
            
            # Filter: Today + BUY + COMPLETE status
            if (order_date_str == today and 
                order['transaction_type'] == 'BUY' and 
                order['status'] == 'COMPLETE'):
                
                todays_buys.append({
                    'order_id': order['order_id'],
                    'tradingsymbol': order['tradingsymbol'],
                    'exchange': order['exchange'],
                    'quantity': order['filled_quantity'],  # Use filled qty, not ordered
                    'average_price': order.get('average_price', 0),
                    'product': order['product'],
                    'variety': order.get('variety', 'regular'),
                    'order_timestamp': order['order_timestamp']
                })
        
        return todays_buys
    
    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return []


def aggregate_orders_by_symbol(orders):
    """
    Aggregate multiple orders of same symbol into one
    (In case multiple tranches were bought)
    """
    aggregated = {}
    
    for order in orders:
        symbol = order['tradingsymbol']
        
        if symbol not in aggregated:
            aggregated[symbol] = {
                'tradingsymbol': symbol,
                'exchange': order['exchange'],
                'quantity': 0,
                'total_value': 0,
                'product': order['product'],
                'variety': order['variety'],
                'orders': []
            }
        
        aggregated[symbol]['quantity'] += order['quantity']
        aggregated[symbol]['total_value'] += order['quantity'] * order['average_price']
        aggregated[symbol]['orders'].append(order['order_id'])
    
    # Calculate weighted average price
    for symbol in aggregated:
        if aggregated[symbol]['quantity'] > 0:
            aggregated[symbol]['average_price'] = (
                aggregated[symbol]['total_value'] / aggregated[symbol]['quantity']
            )
        else:
            aggregated[symbol]['average_price'] = 0
    
    return list(aggregated.values())


def get_current_ltp(kite, stocks):
    """Get current LTP for all stocks"""
    if not stocks:
        return {}
    
    try:
        instruments = [f"{s['exchange']}:{s['tradingsymbol']}" for s in stocks]
        quotes = kite.quote(instruments)
        
        ltp_map = {}
        for instrument, data in quotes.items():
            symbol = instrument.split(':')[1]
            ltp_map[symbol] = data.get('last_price', 0)
        
        return ltp_map
    
    except Exception as e:
        logger.error(f"Error fetching LTP: {e}")
        return {}


def sell_stock(kite, stock, ltp=None):
    """Place sell order for a stock"""
    try:
        # Determine order type and price
        if SELL_ORDER_TYPE == "LIMIT" and ltp:
            order_type = kite.ORDER_TYPE_LIMIT
            price = round(ltp * (1 - LIMIT_PRICE_DISCOUNT), 2)
        else:
            order_type = kite.ORDER_TYPE_MARKET
            price = None
        
        order_params = {
            'tradingsymbol': stock['tradingsymbol'],
            'exchange': stock['exchange'],
            'transaction_type': kite.TRANSACTION_TYPE_SELL,
            'quantity': stock['quantity'],
            'order_type': order_type,
            'product': stock['product'],
            'variety': kite.VARIETY_REGULAR
        }
        
        if price:
            order_params['price'] = price
        
        if DRY_RUN:
            price_str = f"@ ₹{price:.2f}" if price else "@ MARKET"
            logger.info(
                f"[DRY RUN] Would sell: {stock['tradingsymbol']} x {stock['quantity']} "
                f"{price_str} (Bought @ ₹{stock['average_price']:.2f})"
            )
            return "DRY_RUN"
        else:
            order_id = kite.place_order(**order_params)
            logger.info(
                f"Sold: {stock['tradingsymbol']} x {stock['quantity']} - Order ID: {order_id}"
            )
            return order_id
    
    except Exception as e:
        logger.error(f"Error selling {stock['tradingsymbol']}: {e}")
        return None


def calculate_pnl(buy_price, sell_price, quantity):
    """Calculate estimated P&L"""
    gross_pnl = (sell_price - buy_price) * quantity
    # Approximate charges (STT, brokerage, etc.) ~0.1%
    charges = abs(sell_price * quantity * 0.001)
    net_pnl = gross_pnl - charges
    return net_pnl


def main():
    print("=" * 70)
    print("ZERODHA KITE - SELL ALL STOCKS BOUGHT TODAY")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if DRY_RUN:
        print("\n⚠️  DRY RUN MODE - No actual orders will be placed")
        print("    Set DRY_RUN = False in the script to execute real orders\n")
    else:
        print("\n🔴 LIVE MODE - Orders will be executed!")
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            return
    
    # Initialize Kite client
    print("\n🔌 Connecting to Kite...")
    kite = get_kite_client()
    
    # Get today's BUY orders
    print("📊 Fetching today's orders...")
    todays_buys = get_todays_buy_orders(kite)
    
    if not todays_buys:
        print("\n✅ No BUY orders found for today!")
        return
    
    # Aggregate by symbol (in case multiple orders for same stock)
    print("📦 Aggregating orders...")
    aggregated_stocks = aggregate_orders_by_symbol(todays_buys)
    
    # Get current LTP for all stocks
    print("💹 Fetching current prices...")
    ltp_map = get_current_ltp(kite, aggregated_stocks)
    
    # Display summary
    print(f"\n📈 Found {len(todays_buys)} BUY orders across {len(aggregated_stocks)} stocks")
    
    total_buy_value = 0
    total_current_value = 0
    
    print("\n" + "-" * 70)
    print(f"{'Symbol':<15} {'Qty':>8} {'Buy Avg':>12} {'LTP':>12} {'Est. P&L':>12}")
    print("-" * 70)
    
    for stock in aggregated_stocks:
        symbol = stock['tradingsymbol']
        qty = stock['quantity']
        buy_price = stock['average_price']
        ltp = ltp_map.get(symbol, buy_price)
        
        buy_value = buy_price * qty
        current_value = ltp * qty
        pnl = calculate_pnl(buy_price, ltp, qty)
        
        total_buy_value += buy_value
        total_current_value += current_value
        
        pnl_str = f"₹{pnl:+,.2f}"
        pnl_color = "🟢" if pnl >= 0 else "🔴"
        
        print(f"{symbol:<15} {qty:>8} ₹{buy_price:>10,.2f} ₹{ltp:>10,.2f} {pnl_color}{pnl_str:>10}")
    
    print("-" * 70)
    total_pnl = total_current_value - total_buy_value
    pnl_percent = (total_pnl / total_buy_value * 100) if total_buy_value > 0 else 0
    print(f"{'TOTAL':<15} {'':<8} ₹{total_buy_value:>10,.2f} ₹{total_current_value:>10,.2f} {'₹':>2}{total_pnl:+,.2f} ({pnl_percent:+.2f}%)")
    print("-" * 70)
    
    # Confirm before selling
    if not DRY_RUN:
        print(f"\n⚠️  About to sell {len(aggregated_stocks)} stocks worth ₹{total_current_value:,.2f}")
        confirm_sell = input("Type 'SELL' to confirm: ")
        if confirm_sell != "SELL":
            print("Aborted.")
            return
    
    # Sell all stocks
    print("\n" + "=" * 70)
    print("PLACING SELL ORDERS...")
    print("=" * 70)
    
    orders_placed = 0
    orders_failed = 0
    
    for stock in aggregated_stocks:
        symbol = stock['tradingsymbol']
        ltp = ltp_map.get(symbol)
        
        result = sell_stock(kite, stock, ltp)
        
        if result:
            orders_placed += 1
        else:
            orders_failed += 1
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Orders placed: {orders_placed}")
    if orders_failed > 0:
        print(f"❌ Orders failed: {orders_failed}")
    if DRY_RUN:
        print("\n📝 This was a dry run. Set DRY_RUN = False to execute actual orders.")
    print("=" * 70)


if __name__ == "__main__":
    main()
