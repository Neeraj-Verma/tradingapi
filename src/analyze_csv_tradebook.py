"""
Analyze CSV Tradebook - Calculate P&L from sold stocks vs current LTP

Usage:
    python src/analyze_csv_tradebook.py                              # Default file
    python src/analyze_csv_tradebook.py --file "data/tradebook.csv"  # Custom file
"""

import os
import sys
import argparse
import pandas as pd
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description='Analyze CSV tradebook P&L')
    parser.add_argument('--file', type=str, default='data/tradebook-VPR980-EQ (2).csv',
                        help='Path to tradebook CSV file')
    args = parser.parse_args()
    
    # Read CSV
    if not os.path.exists(args.file):
        print(f"File not found: {args.file}")
        return
    
    df = pd.read_csv(args.file)
    print(f"Loaded {len(df)} trades from {args.file}")
    
    # Aggregate by symbol (sum qty, weighted avg price)
    grouped = df.groupby('Symbol').apply(
        lambda x: pd.Series({
            'Qty': x['Quantity'].sum(),
            'Avg_Sell_Price': (x['Quantity'] * x['Price']).sum() / x['Quantity'].sum()
        })
    ).reset_index()
    
    print(f"Aggregated to {len(grouped)} unique symbols")
    print()
    
    # Connect to Kite
    api_key = os.getenv("API_KEY", "").strip()
    access_token = os.getenv("ACCESS_TOKEN", "").strip()
    
    if not api_key or not access_token:
        print("Missing API_KEY or ACCESS_TOKEN")
        return
    
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    # Verify connection
    try:
        profile = kite.profile()
        print(f"Connected as: {profile.get('user_name', 'Unknown')}")
    except Exception as e:
        print(f"Connection failed: {e}")
        return
    
    # Get LTP
    symbols = grouped['Symbol'].tolist()
    instruments = [f'NSE:{s}' for s in symbols]
    
    try:
        ltp_data = kite.ltp(instruments)
    except Exception as e:
        print(f"Failed to fetch LTP: {e}")
        return
    
    # Calculate P&L
    results = []
    for _, row in grouped.iterrows():
        sym = row['Symbol']
        qty = int(row['Qty'])
        avg_sell = row['Avg_Sell_Price']
        ltp = ltp_data.get(f'NSE:{sym}', {}).get('last_price', 0)
        
        if ltp <= 0:
            continue
        
        sold_val = qty * avg_sell
        curr_val = qty * ltp
        pnl = curr_val - sold_val
        pct = ((ltp - avg_sell) / avg_sell * 100) if avg_sell > 0 else 0
        
        results.append({
            'symbol': sym,
            'qty': qty,
            'avg_sell': avg_sell,
            'ltp': ltp,
            'sold_val': sold_val,
            'curr_val': curr_val,
            'pnl': pnl,
            'pct': pct
        })
    
    # Sort by P&L descending
    results.sort(key=lambda x: x['pnl'], reverse=True)
    
    # Print results
    print()
    print("=" * 130)
    print(f"{'Symbol':<15} {'Qty':>8} {'Sold @':>12} {'LTP':>12} {'Sold Value':>15} {'Curr Value':>15} {'Opp P&L':>15} {'Opp%':>10}")
    print("-" * 130)
    
    total_sold = 0
    total_curr = 0
    
    for r in results:
        sign = "+" if r['pnl'] >= 0 else ""
        print(f"{r['symbol']:<15} {r['qty']:>8} {r['avg_sell']:>12,.2f} {r['ltp']:>12,.2f} "
              f"{r['sold_val']:>15,.2f} {r['curr_val']:>15,.2f} {sign}{r['pnl']:>14,.2f} {sign}{r['pct']:>9.2f}%")
        
        total_sold += r['sold_val']
        total_curr += r['curr_val']
    
    print("-" * 130)
    total_pnl = total_curr - total_sold
    sign = "+" if total_pnl >= 0 else ""
    pct = ((total_curr - total_sold) / total_sold * 100) if total_sold > 0 else 0
    print(f"{'TOTAL':<15} {'':<8} {'':<12} {'':<12} {total_sold:>15,.2f} {total_curr:>15,.2f} "
          f"{sign}{total_pnl:>14,.2f} {sign}{pct:>9.2f}%")
    
    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Sold Value: Rs. {total_sold:,.2f}")
    print(f"Current Value if Held: Rs. {total_curr:,.2f}")
    
    if total_pnl >= 0:
        print(f"\n[MISSED GAINS] You would have gained Rs. {total_pnl:,.2f} more if you held")
    else:
        print(f"\n[GOOD DECISION] You avoided Rs. {abs(total_pnl):,.2f} in losses by selling")
    
    # Top missed/avoided
    missed = [r for r in results if r['pnl'] > 0]
    avoided = [r for r in results if r['pnl'] < 0]
    
    if missed:
        print(f"\nTop Missed Gains:")
        for r in missed[:5]:
            print(f"  {r['symbol']}: +Rs. {r['pnl']:,.2f} (+{r['pct']:.2f}%)")
    
    if avoided:
        print(f"\nAvoided Losses:")
        for r in avoided[:5]:
            print(f"  {r['symbol']}: Rs. {r['pnl']:,.2f} ({r['pct']:.2f}%)")


if __name__ == "__main__":
    main()
