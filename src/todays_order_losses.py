"""
Zerodha Kite - Show today's order losses
- Today's Loss = LTP - Sell Price (what you could have gotten if sold now)
- All-Time Loss = Buy Price - Sell Price (actual realized loss)
"""

import os
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

def main():
    kite = KiteConnect(api_key=os.getenv("API_KEY"))
    kite.set_access_token(os.getenv("ACCESS_TOKEN"))

    # Get today's orders
    orders = kite.orders()
    
    # Get holdings for buy prices
    holdings = kite.holdings()
    holdings_map = {h['tradingsymbol']: h for h in holdings}

    # Collect sell orders with loss calculations
    sell_orders = []
    
    for order in orders:
        if order.get('status') == 'COMPLETE' and order.get('transaction_type') == 'SELL':
            symbol = order['tradingsymbol']
            sell_price = order.get('average_price', 0)
            quantity = order.get('filled_quantity', 0)
            
            # Get LTP for today's loss calculation
            try:
                ltp_data = kite.ltp(f"{order['exchange']}:{symbol}")
                ltp = ltp_data.get(f"{order['exchange']}:{symbol}", {}).get('last_price', sell_price)
            except:
                ltp = sell_price
            
            # Get buy price from holdings (average_price)
            holding = holdings_map.get(symbol, {})
            buy_price = holding.get('average_price', 0)
            
            # If not in holdings, try to get from order history or use 0
            if buy_price == 0:
                # Check if there was a buy order today
                for o in orders:
                    if o.get('tradingsymbol') == symbol and o.get('transaction_type') == 'BUY' and o.get('status') == 'COMPLETE':
                        buy_price = o.get('average_price', 0)
                        break
            
            # Today's Loss = (LTP - Sell Price) * Qty
            # If LTP > Sell Price, you sold too early (opportunity loss)
            todays_loss = (ltp - sell_price) * quantity
            
            # All-Time Loss = (Buy Price - Sell Price) * Qty
            # If Buy Price > Sell Price, you made a loss
            alltime_loss = (buy_price - sell_price) * quantity if buy_price > 0 else 0
            
            sell_orders.append({
                'symbol': symbol,
                'quantity': quantity,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'ltp': ltp,
                'todays_loss': todays_loss,
                'alltime_loss': alltime_loss,
                'order_time': order.get('order_timestamp')
            })

    # Sort by all-time loss (highest loss first)
    sell_orders.sort(key=lambda x: x['alltime_loss'], reverse=True)

    print("=" * 100)
    print("TODAY'S SELL ORDERS - LOSS ANALYSIS")
    print("=" * 100)
    print(f"{'Symbol':<20} {'Qty':>6} {'Buy':>10} {'Sell':>10} {'LTP':>10} {'Today Loss':>12} {'AllTime Loss':>14}")
    print("-" * 100)
    
    total_todays_loss = 0
    total_alltime_loss = 0
    
    for item in sell_orders:
        buy_str = f"{item['buy_price']:.2f}" if item['buy_price'] > 0 else "N/A"
        print(f"{item['symbol']:<20} {item['quantity']:>6} {buy_str:>10} {item['sell_price']:>10.2f} {item['ltp']:>10.2f} Rs.{item['todays_loss']:>10.2f} Rs.{item['alltime_loss']:>12.2f}")
        total_todays_loss += item['todays_loss']
        total_alltime_loss += item['alltime_loss']

    print("=" * 100)
    print(f"{'TOTAL':<20} {'':<6} {'':<10} {'':<10} {'':<10} Rs.{total_todays_loss:>10.2f} Rs.{total_alltime_loss:>12.2f}")
    print("=" * 100)
    print()
    print("Today's Loss  = (LTP - Sell Price) * Qty  --> Opportunity loss if positive")
    print("AllTime Loss  = (Buy Price - Sell Price) * Qty  --> Actual realized loss if positive")
    print("=" * 100)


if __name__ == "__main__":
    main()
