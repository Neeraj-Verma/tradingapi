"""
Analyze Sold Stocks - Compare sold prices with current LTP
Creates a CSV with P/L analysis for stocks that were sold

Supports brokerage contract note format with columns:
- Security/Contract Description
- Buy(B) / Sell(S)
- Quantity
- Gross Rate / Trade Price Per Unit (Rs)
- Net Total (Before Levies) (Rs)
"""

import os
import sys
import re
from pathlib import Path
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Setup paths
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load environment
_src_env = REPO_ROOT / "src" / ".env"
_root_env = REPO_ROOT / ".env"
if _src_env.exists():
    load_dotenv(dotenv_path=_src_env, override=False)
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)

from kiteconnect import KiteConnect


def extract_symbol(description: str) -> str:
    """Extract trading symbol from Security/Contract Description
    E.g., 'ADANIGREEN-EQ/INE364U01010' -> 'ADANIGREEN'
          'ADANIPORTS-A/INE742F01042' -> 'ADANIPORTS'
    """
    if pd.isna(description):
        return None
    # Take part before first '-' or '/'
    match = re.match(r'^([A-Z0-9&]+)', str(description).upper())
    return match.group(1) if match else None


def analyze_sold_stocks():
    """Analyze sold stocks and calculate current P/L based on LTP"""
    
    # Read sold stocks data
    sold_path = REPO_ROOT / "data" / "s_sold.xlsx"
    if not sold_path.exists():
        print(f"❌ File not found: {sold_path}")
        return None
    
    df = pd.read_excel(sold_path)
    print(f"📊 Loaded {len(df)} rows from s_sold.xlsx")
    
    # Check if it's brokerage contract note format
    if 'Security/Contract Description' in df.columns:
        print("📋 Detected brokerage contract note format")
        
        # Filter only Sell transactions
        df = df[df['Buy(B) / Sell(S)'] == 'S'].copy()
        print(f"📊 Found {len(df)} sell transactions")
        
        # Extract symbol from description
        df['Symbol'] = df['Security/Contract Description'].apply(extract_symbol)
        df = df.dropna(subset=['Symbol'])
        
        # Rename columns
        df = df.rename(columns={
            'Quantity': 'Quantity',
            'Gross Rate / Trade Price Per Unit (Rs)': 'Sell_Price',
            'Net Total (Before Levies) (Rs)': 'Sold_Value'
        })
        
        # Ensure numeric
        df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce').fillna(0).astype(int)
        df['Sell_Price'] = pd.to_numeric(df['Sell_Price'], errors='coerce').fillna(0)
        df['Sold_Value'] = pd.to_numeric(df['Sold_Value'], errors='coerce').fillna(0)
        
        # Aggregate by symbol (sum quantity and value, weighted avg price)
        aggregated = df.groupby('Symbol').agg({
            'Quantity': 'sum',
            'Sold_Value': 'sum'
        }).reset_index()
        
        # Calculate weighted average sell price
        aggregated['Avg_Sell_Price'] = aggregated['Sold_Value'] / aggregated['Quantity']
        df = aggregated
        
        print(f"📊 Aggregated to {len(df)} unique stocks")
    else:
        # Legacy format: Symbol, Quantity, Sold_Value, Avg_Sell_Price
        df.columns = ['Symbol', 'Quantity', 'Sold_Value', 'Avg_Sell_Price']
    
    # Connect to Kite for LTP
    api_key = os.getenv("API_KEY")
    access_token = os.getenv("ACCESS_TOKEN")
    
    if not api_key or not access_token:
        print("❌ Kite credentials not found in environment")
        return None
    
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    
    print("✅ Connected to Kite")
    
    # Get LTP for all symbols
    symbols = df['Symbol'].tolist()
    nse_symbols = [f"NSE:{s}" for s in symbols]
    
    try:
        # Fetch LTP in batches (Kite allows max ~500 at once)
        ltp_data = kite.ltp(nse_symbols)
        print(f"✅ Fetched LTP for {len(ltp_data)} stocks")
    except Exception as e:
        print(f"❌ Error fetching LTP: {e}")
        return None
    
    # Calculate P/L
    results = []
    total_sold_value = 0
    total_current_value = 0
    
    for _, row in df.iterrows():
        symbol = row['Symbol']
        qty = int(row['Quantity'])
        sold_value = float(row['Sold_Value'])
        avg_sell_price = float(row['Avg_Sell_Price'])
        
        key = f"NSE:{symbol}"
        if key in ltp_data:
            ltp = ltp_data[key]['last_price']
            current_value = ltp * qty
            pl = current_value - sold_value  # Positive = missed opportunity
            pl_pct = (pl / sold_value * 100) if sold_value > 0 else 0
            
            total_sold_value += sold_value
            total_current_value += current_value
            
            results.append({
                'Symbol': symbol,
                'Quantity': qty,
                'Avg_Sell_Price': round(avg_sell_price, 2),
                'Current_LTP': round(ltp, 2),
                'Sold_Value': round(sold_value, 2),
                'Current_Value': round(current_value, 2),
                'PL': round(pl, 2),
                'PL_Pct': round(pl_pct, 2)
            })
        else:
            print(f"⚠️ No LTP for {symbol}")
            results.append({
                'Symbol': symbol,
                'Quantity': qty,
                'Avg_Sell_Price': round(avg_sell_price, 2),
                'Current_LTP': 0,
                'Sold_Value': round(sold_value, 2),
                'Current_Value': 0,
                'PL': 0,
                'PL_Pct': 0
            })
    
    # Create DataFrame and sort by P/L %
    result_df = pd.DataFrame(results)
    result_df = result_df.sort_values('PL_Pct', ascending=False)
    
    # Save to CSV
    output_path = REPO_ROOT / "data" / "sold_stocks_analysis.csv"
    result_df.to_csv(output_path, index=False)
    print(f"✅ Saved analysis to: {output_path}")
    
    # Print summary
    total_pl = total_current_value - total_sold_value
    total_pl_pct = (total_pl / total_sold_value * 100) if total_sold_value > 0 else 0
    
    print("\n" + "="*60)
    print("📊 SOLD STOCKS ANALYSIS SUMMARY")
    print("="*60)
    print(f"Total Stocks Analyzed: {len(results)}")
    print(f"Total Sold Value:      ₹{total_sold_value:,.2f}")
    print(f"Current Value (LTP):   ₹{total_current_value:,.2f}")
    print(f"Total P/L:             ₹{total_pl:,.2f} ({total_pl_pct:+.2f}%)")
    print("="*60)
    
    # Top 10 Gainers (missed opportunities)
    print("\n🟢 TOP 10 GAINERS (Sold too early - Missed Opportunity):")
    print("-"*60)
    top_gainers = result_df.head(10)
    for _, row in top_gainers.iterrows():
        print(f"  {row['Symbol']:15} LTP: ₹{row['Current_LTP']:>10,.2f}  P/L: ₹{row['PL']:>10,.2f} ({row['PL_Pct']:>+7.2f}%)")
    
    # Top 10 Losers (good sells)
    print("\n🔴 TOP 10 LOSERS (Good decision to sell):")
    print("-"*60)
    top_losers = result_df.tail(10).iloc[::-1]
    for _, row in top_losers.iterrows():
        print(f"  {row['Symbol']:15} LTP: ₹{row['Current_LTP']:>10,.2f}  P/L: ₹{row['PL']:>10,.2f} ({row['PL_Pct']:>+7.2f}%)")
    
    print("\n" + "="*60)
    
    return result_df


if __name__ == "__main__":
    analyze_sold_stocks()
