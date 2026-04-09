"""
Zerodha Kite - Sell all stocks with negative P&L
Requires: pip install kiteconnect python-dotenv
"""

import os
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
DRY_RUN = False
# ===================================


def get_kite_client():
    """Initialize and return Kite client"""
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)
    return kite


def get_negative_holdings(kite):
    """Get holdings with negative P&L"""
    try:
        holdings = kite.holdings()
        negative_holdings = []
        
        for stock in holdings:
            pnl = stock.get('pnl', 0)
            quantity = stock.get('quantity', 0)
            
            if pnl < 0 and quantity > 0:
                negative_holdings.append({
                    'tradingsymbol': stock['tradingsymbol'],
                    'exchange': stock['exchange'],
                    'quantity': quantity,
                    'pnl': pnl,
                    'average_price': stock.get('average_price', 0),
                    'last_price': stock.get('last_price', 0)
                })
        
        return negative_holdings
    except Exception as e:
        logger.error(f"Error fetching holdings: {e}")
        return []


def get_negative_positions(kite):
    """Get positions (intraday/F&O) with negative P&L"""
    try:
        positions = kite.positions()
        negative_positions = []
        
        # Check both day and net positions
        for pos in positions.get('net', []):
            pnl = pos.get('pnl', 0)
            quantity = pos.get('quantity', 0)
            
            if pnl < 0 and quantity > 0:
                negative_positions.append({
                    'tradingsymbol': pos['tradingsymbol'],
                    'exchange': pos['exchange'],
                    'quantity': quantity,
                    'pnl': pnl,
                    'product': pos.get('product', 'CNC'),
                    'average_price': pos.get('average_price', 0),
                    'last_price': pos.get('last_price', 0)
                })
        
        return negative_positions
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return []


def sell_stock(kite, stock, is_position=False):
    """Place sell order for a stock"""
    try:
        # Determine product type
        if is_position:
            product = stock.get('product', kite.PRODUCT_CNC)
        else:
            product = kite.PRODUCT_CNC  # Holdings are always CNC
        
        order_params = {
            'tradingsymbol': stock['tradingsymbol'],
            'exchange': stock['exchange'],
            'transaction_type': kite.TRANSACTION_TYPE_SELL,
            'quantity': stock['quantity'],
            'order_type': kite.ORDER_TYPE_MARKET,
            'product': product,
            'variety': kite.VARIETY_REGULAR
        }
        
        if DRY_RUN:
            logger.info(f"[DRY RUN] Would sell: {stock['tradingsymbol']} x {stock['quantity']} (P&L: ₹{stock['pnl']:.2f})")
            return None
        else:
            order_id = kite.place_order(**order_params)
            logger.info(f"Sold: {stock['tradingsymbol']} x {stock['quantity']} - Order ID: {order_id}")
            return order_id
            
    except Exception as e:
        logger.error(f"Error selling {stock['tradingsymbol']}: {e}")
        return None


def main():
    print("=" * 60)
    print("ZERODHA KITE - SELL NEGATIVE P&L STOCKS")
    print("=" * 60)
    
    if DRY_RUN:
        print("\n⚠️  DRY RUN MODE - No actual orders will be placed")
        print("    Set DRY_RUN = False to execute real orders\n")
    else:
        print("\n🔴 LIVE MODE - Orders will be executed!\n")
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Aborted.")
            return
    
    # Initialize Kite client
    kite = get_kite_client()
    
    # Get negative P&L holdings
    print("\n📊 Checking Holdings...")
    negative_holdings = get_negative_holdings(kite)
    
    # Get negative P&L positions
    print("📊 Checking Positions...")
    negative_positions = get_negative_positions(kite)
    
    # Display summary
    total_negative = len(negative_holdings) + len(negative_positions)
    total_loss = sum(h['pnl'] for h in negative_holdings) + sum(p['pnl'] for p in negative_positions)
    
    print(f"\n📉 Found {total_negative} stocks with negative P&L")
    print(f"💰 Total unrealized loss: ₹{total_loss:.2f}\n")
    
    if total_negative == 0:
        print("✅ No stocks with negative P&L found!")
        return
    
    # Display negative holdings
    if negative_holdings:
        print("\n--- HOLDINGS WITH NEGATIVE P&L ---")
        for stock in negative_holdings:
            print(f"  {stock['tradingsymbol']:20} Qty: {stock['quantity']:>6}  P&L: ₹{stock['pnl']:>10.2f}")
    
    # Display negative positions
    if negative_positions:
        print("\n--- POSITIONS WITH NEGATIVE P&L ---")
        for stock in negative_positions:
            print(f"  {stock['tradingsymbol']:20} Qty: {stock['quantity']:>6}  P&L: ₹{stock['pnl']:>10.2f}")
    
    # Sell stocks
    print("\n" + "=" * 60)
    print("SELLING STOCKS...")
    print("=" * 60)
    
    orders_placed = 0
    
    for stock in negative_holdings:
        result = sell_stock(kite, stock, is_position=False)
        if result or DRY_RUN:
            orders_placed += 1
    
    for stock in negative_positions:
        result = sell_stock(kite, stock, is_position=True)
        if result or DRY_RUN:
            orders_placed += 1
    
    print(f"\n✅ {orders_placed}/{total_negative} sell orders processed")
    print("=" * 60)


if __name__ == "__main__":
    main()
