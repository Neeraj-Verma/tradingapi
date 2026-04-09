"""
Analyze Sold Stocks - Check LTP of recently sold stocks and calculate opportunity cost

This script:
1. Reads trade history from tradebook Excel file (downloaded from Kite)
2. Also fetches today's trades from Kite API
3. Gets current LTP for sold stocks
4. Calculates potential P&L if held vs sold

Usage:
    python analyze_sold_stocks_kite.py              # Use tradebook + today's trades
    python analyze_sold_stocks_kite.py --days 7     # Filter by days
    python analyze_sold_stocks_kite.py --tradebook "data/tradebook.xlsx"  # Custom file
"""

import os
import sys
import argparse
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
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

# Default tradebook path
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DEFAULT_TRADEBOOK = os.path.join(DATA_DIR, 'tradebook-VPR980-EQ (2).xlsx')


def read_tradebook_excel(filepath: str) -> List[dict]:
    """Read sell trades from Kite tradebook Excel file."""
    try:
        if not os.path.exists(filepath):
            logger.warning(f"Tradebook file not found: {filepath}")
            return []
        
        # Read Excel with correct structure (headers at row 14)
        df = pd.read_excel(filepath, header=None, skiprows=14)
        df.columns = ['Drop', 'Symbol', 'ISIN', 'Trade Date', 'Exchange', 'Segment', 
                      'Series', 'Trade Type', 'Auction', 'Quantity', 'Price', 
                      'Trade ID', 'Order ID', 'Order Execution Time']
        df = df.drop(columns=['Drop'])
        df = df.dropna(subset=['Symbol'])
        
        # Filter sell trades
        sells = df[df['Trade Type'] == 'sell'].copy()
        
        trades = []
        for _, row in sells.iterrows():
            trade_date = row['Trade Date']
            if isinstance(trade_date, str):
                trade_date = datetime.strptime(trade_date, '%Y-%m-%d')
            
            trades.append({
                'symbol': str(row['Symbol']).strip().upper(),
                'exchange': str(row.get('Exchange', 'NSE')).upper(),
                'quantity': int(float(row['Quantity']) if pd.notna(row['Quantity']) else 0),
                'price': float(row['Price']) if pd.notna(row['Price']) else 0,
                'trade_date': trade_date,
                'trade_id': str(row.get('Trade ID', '')),
                'order_id': str(row.get('Order ID', '')),
                'source': 'tradebook'
            })
        
        logger.info(f"Loaded {len(trades)} sell trades from tradebook")
        return trades
        
    except Exception as e:
        logger.error(f"Error reading tradebook: {e}")
        return []


def get_trades(kite: KiteConnect, days: int = 3) -> List[dict]:
    """Get trades from last N days."""
    try:
        # Get orders - this includes today's orders
        # For historical, we need to use trade history
        trades = []
        
        # Get today's trades
        today_orders = kite.orders()
        for o in today_orders:
            if o.get('status') == 'COMPLETE' and o.get('transaction_type') == 'SELL':
                trades.append({
                    'symbol': o.get('tradingsymbol', ''),
                    'exchange': o.get('exchange', 'NSE'),
                    'quantity': int(o.get('filled_quantity', 0) or 0),
                    'price': float(o.get('average_price', 0) or 0),
                    'order_time': o.get('order_timestamp', ''),
                    'order_id': o.get('order_id', '')
                })
        
        return trades
        
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return []


def get_trade_history(kite: KiteConnect, days: int = 3) -> List[dict]:
    """Get trade history from Kite for last N days using trades endpoint."""
    try:
        all_trades = []
        
        # Get today's trades
        try:
            today_trades = kite.trades()
            for t in today_trades:
                if t.get('transaction_type') == 'SELL':
                    all_trades.append({
                        'symbol': t.get('tradingsymbol', ''),
                        'exchange': t.get('exchange', 'NSE'),
                        'quantity': int(t.get('quantity', 0) or 0),
                        'price': float(t.get('average_price', 0) or 0),
                        'trade_time': t.get('fill_timestamp') or t.get('order_timestamp', ''),
                        'order_id': t.get('order_id', ''),
                        'trade_id': t.get('trade_id', '')
                    })
        except Exception as e:
            logger.warning(f"Could not fetch today's trades: {e}")
        
        # For older trades, check order history
        try:
            orders = kite.orders()
            for o in orders:
                if o.get('status') == 'COMPLETE' and o.get('transaction_type') == 'SELL':
                    # Check if not already added
                    order_id = o.get('order_id', '')
                    if not any(t['order_id'] == order_id for t in all_trades):
                        all_trades.append({
                            'symbol': o.get('tradingsymbol', ''),
                            'exchange': o.get('exchange', 'NSE'),
                            'quantity': int(o.get('filled_quantity', 0) or 0),
                            'price': float(o.get('average_price', 0) or 0),
                            'trade_time': o.get('order_timestamp', ''),
                            'order_id': order_id,
                            'trade_id': ''
                        })
        except Exception as e:
            logger.warning(f"Could not fetch orders: {e}")
        
        return all_trades
        
    except Exception as e:
        logger.error(f"Error fetching trade history: {e}")
        return []


def get_ltp(kite: KiteConnect, symbols: List[str], exchange: str = "NSE") -> Dict[str, float]:
    """Get LTP for symbols."""
    try:
        if not symbols:
            return {}
        
        instruments = [f"{exchange}:{s}" for s in symbols]
        data = kite.ltp(instruments)
        
        result = {}
        for s in symbols:
            key = f"{exchange}:{s}"
            if key in data:
                result[s] = float(data[key].get('last_price', 0) or 0)
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching LTP: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(description='Analyze sold stocks P&L')
    parser.add_argument('--days', type=int, default=3, help='Number of days to look back (default: 3)')
    parser.add_argument('--tradebook', type=str, default='data/tradebook-VPR980-EQ (2).xlsx', 
                        help='Path to tradebook Excel file')
    args = parser.parse_args()
    
    print("=" * 100)
    print("SOLD STOCKS ANALYSIS")
    print("=" * 100)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Looking back: {args.days} days")
    print(f"Tradebook: {args.tradebook}")
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
    
    # Get sold trades from API
    logger.info("Fetching sold trades from Kite API...")
    api_trades = get_trade_history(kite, args.days)
    logger.info(f"Found {len(api_trades)} trades from API")
    
    # Read tradebook Excel for historical/settled trades
    tradebook_trades = []
    if args.tradebook:
        tradebook_trades = read_tradebook_excel(args.tradebook)
        # Filter by days
        cutoff_date = datetime.now() - timedelta(days=args.days)
        filtered_tb = []
        for t in tradebook_trades:
            trade_date = t.get('trade_date')
            if trade_date:
                if isinstance(trade_date, datetime):
                    if trade_date >= cutoff_date:
                        filtered_tb.append(t)
                else:
                    filtered_tb.append(t)  # Include if can't parse date
            else:
                filtered_tb.append(t)
        tradebook_trades = filtered_tb
        logger.info(f"Found {len(tradebook_trades)} trades from tradebook (within {args.days} days)")
    
    # Merge trades (API + tradebook), dedupe by order_id
    seen_orders = set()
    trades = []
    
    # Add API trades first (more recent/accurate)
    for t in api_trades:
        order_id = t.get('order_id', '')
        if order_id and order_id not in seen_orders:
            seen_orders.add(order_id)
            trades.append(t)
        elif not order_id:
            trades.append(t)
    
    # Add tradebook trades not already seen
    for t in tradebook_trades:
        order_id = t.get('order_id', '')
        if order_id and order_id not in seen_orders:
            seen_orders.add(order_id)
            trades.append(t)
        elif not order_id:
            trades.append(t)
    
    logger.info(f"Total merged trades: {len(trades)}")
    
    if not trades:
        print("No sold trades found")
        return
    
    # Aggregate by symbol (sum quantities, weighted avg price)
    aggregated = defaultdict(lambda: {'quantity': 0, 'total_value': 0, 'trades': []})
    
    for t in trades:
        symbol = t['symbol']
        qty = t['quantity']
        price = t['price']
        
        aggregated[symbol]['quantity'] += qty
        aggregated[symbol]['total_value'] += qty * price
        aggregated[symbol]['trades'].append(t)
        aggregated[symbol]['exchange'] = t.get('exchange', 'NSE')
    
    # Calculate weighted average sell price
    for symbol, data in aggregated.items():
        if data['quantity'] > 0:
            data['avg_sell_price'] = data['total_value'] / data['quantity']
        else:
            data['avg_sell_price'] = 0
    
    # Get current LTP
    symbols = list(aggregated.keys())
    logger.info(f"Fetching LTP for {len(symbols)} symbols...")
    ltp_map = get_ltp(kite, symbols)
    
    # Calculate P&L
    results = []
    for symbol, data in aggregated.items():
        ltp = ltp_map.get(symbol, 0)
        qty = data['quantity']
        avg_sell = data['avg_sell_price']
        
        if ltp <= 0 or avg_sell <= 0:
            continue
        
        sell_value = qty * avg_sell
        current_value = qty * ltp
        opportunity_pnl = current_value - sell_value  # Positive = missed gain, Negative = avoided loss
        opportunity_pct = ((ltp - avg_sell) / avg_sell) * 100 if avg_sell > 0 else 0
        
        results.append({
            'symbol': symbol,
            'quantity': qty,
            'avg_sell_price': avg_sell,
            'ltp': ltp,
            'sell_value': sell_value,
            'current_value': current_value,
            'opportunity_pnl': opportunity_pnl,
            'opportunity_pct': opportunity_pct,
            'num_trades': len(data['trades'])
        })
    
    # Sort by opportunity P&L (biggest missed gains first)
    results.sort(key=lambda x: x['opportunity_pnl'], reverse=True)
    
    # Display results
    print()
    print("-" * 130)
    print(f"{'Symbol':<15} {'Qty':>8} {'Sold @':>12} {'LTP':>12} {'Sold Value':>15} {'Curr Value':>15} {'Opp P&L':>15} {'Opp%':>10}")
    print("-" * 130)
    
    total_sell_value = 0
    total_current_value = 0
    total_opportunity = 0
    
    for r in results:
        sign = "+" if r['opportunity_pnl'] >= 0 else ""
        print(f"{r['symbol']:<15} {r['quantity']:>8} {r['avg_sell_price']:>12,.2f} {r['ltp']:>12,.2f} {r['sell_value']:>15,.2f} {r['current_value']:>15,.2f} {sign}{r['opportunity_pnl']:>14,.2f} {sign}{r['opportunity_pct']:>9.2f}%")
        
        total_sell_value += r['sell_value']
        total_current_value += r['current_value']
        total_opportunity += r['opportunity_pnl']
    
    print("-" * 130)
    sign = "+" if total_opportunity >= 0 else ""
    opp_pct = ((total_current_value - total_sell_value) / total_sell_value * 100) if total_sell_value > 0 else 0
    print(f"{'TOTAL':<15} {'':<8} {'':<12} {'':<12} {total_sell_value:>15,.2f} {total_current_value:>15,.2f} {sign}{total_opportunity:>14,.2f} {sign}{opp_pct:>9.2f}%")
    
    # Summary
    print()
    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    
    missed_gains = [r for r in results if r['opportunity_pnl'] > 0]
    avoided_losses = [r for r in results if r['opportunity_pnl'] < 0]
    
    print(f"\nTotal Sold Stocks: {len(results)}")
    print(f"Total Sell Value: Rs. {total_sell_value:,.2f}")
    print(f"Current Value if Held: Rs. {total_current_value:,.2f}")
    
    if total_opportunity >= 0:
        print(f"\n[MISSED GAINS] You would have gained Rs. {total_opportunity:,.2f} more if you held")
    else:
        print(f"\n[GOOD DECISION] You avoided Rs. {abs(total_opportunity):,.2f} in losses by selling")
    
    if missed_gains:
        print(f"\nMissed Gains ({len(missed_gains)} stocks):")
        for r in missed_gains[:5]:
            print(f"  {r['symbol']}: +Rs. {r['opportunity_pnl']:,.2f} ({r['opportunity_pct']:+.2f}%)")
    
    if avoided_losses:
        print(f"\nAvoided Losses ({len(avoided_losses)} stocks):")
        for r in avoided_losses[-5:]:
            print(f"  {r['symbol']}: Rs. {r['opportunity_pnl']:,.2f} ({r['opportunity_pct']:.2f}%)")


if __name__ == "__main__":
    main()
