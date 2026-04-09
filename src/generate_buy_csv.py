"""
Generate buy CSV with live CMP and calculated quantities.

- Reads buy.xlsx
- Fetches live prices from Kite
- Calculates quantity based on:
  - Total Investment: 50 lacs (50,00,000)
  - Suggested Allocation (%)
  - Max per stock: Investment Amount (₹) column
"""

import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Load environment variables
load_dotenv()

# Total Investment Amount
TOTAL_INVESTMENT = 5000000  # 50 lacs

# Stock name to NSE symbol mapping
STOCK_TO_SYMBOL = {
    'HDFC Bank': 'HDFCBANK',
    'ICICI Bank': 'ICICIBANK',
    'Asian Paints': 'ASIANPAINT',
    'Pidilite': 'PIDILITIND',
    'Titan': 'TITAN',
    'HUL': 'HINDUNILVR',
    'Nestle': 'NESTLEIND',
    'Kotak Bank': 'KOTAKBANK',
    'Sun Pharma': 'SUNPHARMA',
    'Dr Reddy': 'DRREDDY',
    'L&T': 'LT',
    'Siemens': 'SIEMENS',
    'ABB': 'ABB',
    'Cummins': 'CUMMINSIND',
    'Polycab': 'POLYCAB',
    'KEI Industries': 'KEI',
    'Apollo Hospitals': 'APOLLOHOSP',
    'Tata Elxsi': 'TATAELXSI',
    'Jio Financial': 'JIOFIN',
    'Zomato': 'ETERNAL',  # Zomato renamed to ETERNAL
    'ITC': 'ITC',
    'BHEL': 'BHEL',
    'PNB': 'PNB',
    'ONGC': 'ONGC',
    'NTPC': 'NTPC',
    'NHPC': 'NHPC',
    'CIPLA': 'CIPLA',
    'WIPRO': 'WIPRO',
    'RBL Bank': 'RBLBANK',
    'Yes Bank': 'YESBANK',
    'Coal India': 'COALINDIA',
    'SAIL': 'SAIL',
    'IRB Infra': 'IRB',
    'Apollo Tyres': 'APOLLOTYRE',
    'Ador Welding': 'ADORWELD',
    'RCF': 'RCF',
    'Mazagon Dock': 'MAZDOCK',
    'Godawari Power': 'GPPL',
    '20 Microns': '20MICRONS',
    'Zomato (Old holding)': 'ETERNAL',  # Zomato renamed to ETERNAL
    # Already NSE symbols
    'APOLLOHOSP': 'APOLLOHOSP',
    'BEL': 'BEL',
    'BHARTIARTL': 'BHARTIARTL',
    'CAPLIPOINT': 'CAPLIPOINT',
    'DATAMATICS': 'DATAMATICS',
    'FEDERALBNK': 'FEDERALBNK',
    'GICRE': 'GICRE',
    'HINDALCO': 'HINDALCO',
    'HINDUNILVR': 'HINDUNILVR',
    'HUDCO': 'HUDCO',
    'IDEAFORGE': 'IDEAFORGE',
    'IOC': 'IOC',
    'MAZDOCK': 'MAZDOCK',
    'NATIONALUM': 'NATIONALUM',
    'NESTLEIND': 'NESTLEIND',
    'PAYTM': 'PAYTM',
    'PNCINFRA': 'PNCINFRA',
    'POWERMECH': 'POWERMECH',
    'PREMIERPOL': 'PREMIERPOL',
    'SBIN': 'SBIN',
    'SOLARINDS': 'SOLARINDS',
    'SUZLON': 'SUZLON',
    'TECHM': 'TECHM',
    'TRENT': 'TRENT',
    'ZENTEC': 'ZENTEC',
}


def get_symbol(stock_name: str) -> str:
    """Get NSE symbol from stock name."""
    stock_name = stock_name.strip()
    if stock_name in STOCK_TO_SYMBOL:
        return STOCK_TO_SYMBOL[stock_name]
    # If not in mapping, assume it's already a symbol
    return stock_name.upper().replace(' ', '')


def fetch_live_prices(symbols: list[str], exchange: str = "NSE") -> dict[str, float]:
    """Fetch live LTP for symbols from Kite."""
    api_key = os.getenv("API_KEY", "").strip()
    access_token = os.getenv("ACCESS_TOKEN", "").strip()

    if not api_key or not access_token:
        print("ERROR: Missing API_KEY/ACCESS_TOKEN for Kite LTP")
        return {}

    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        instruments = [f"{exchange}:{s}" for s in symbols]
        data = kite.ltp(instruments)

        ltp_map: dict[str, float] = {}
        for s in symbols:
            key = f"{exchange}:{s}"
            if key in data and isinstance(data[key], dict):
                ltp_map[s] = float(data[key].get("last_price", 0.0) or 0.0)

        return ltp_map
    except Exception as e:
        print(f"Error fetching LTP: {e}")
        return {}


def main():
    # Read buy.xlsx
    excel_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'buy.xlsx')
    df = pd.read_excel(excel_path)
    
    print(f"Loaded {len(df)} stocks from buy.xlsx")
    print(f"Total Investment: ₹{TOTAL_INVESTMENT:,.0f} (50 lacs)")
    
    # Get unique symbols
    df['Symbol'] = df['Stock'].apply(get_symbol)
    unique_symbols = df['Symbol'].unique().tolist()
    
    print(f"\nFetching live prices for {len(unique_symbols)} unique symbols...")
    
    # Fetch live prices
    ltp_map = fetch_live_prices(unique_symbols)
    
    if not ltp_map:
        print("Failed to fetch live prices. Exiting.")
        return
    
    print(f"Fetched prices for {len(ltp_map)} symbols")
    
    # Calculate quantities
    results = []
    total_allocated = 0
    
    for idx, row in df.iterrows():
        stock = row['Stock']
        symbol = row['Symbol']
        suggested_allocation_pct = float(row['Suggested Allocation (%)'] or 0)
        max_investment = float(row['Investment Amount (₹)'] or 0)
        
        cmp = ltp_map.get(symbol, 0)
        
        if cmp <= 0:
            print(f"  Warning: No CMP for {symbol}")
            results.append({
                'Stock': stock,
                'Symbol': symbol,
                'Sector': row.get('Sector', ''),
                'Strategy Bucket': row.get('Strategy Bucket', ''),
                'Suggested Allocation (%)': suggested_allocation_pct,
                'Max Investment (₹)': max_investment,
                'CMP': 0,
                'Calculated Investment (₹)': 0,
                'Final Investment (₹)': 0,
                'Quantity': 0,
                'Status': 'No CMP'
            })
            continue
        
        # Calculate based on allocation percentage
        calculated_investment = (suggested_allocation_pct / 100) * TOTAL_INVESTMENT
        
        # Cap at max investment amount
        final_investment = min(calculated_investment, max_investment)
        
        # Calculate quantity (floor to whole shares)
        quantity = int(final_investment // cmp)
        
        # Actual investment based on quantity
        actual_investment = quantity * cmp
        total_allocated += actual_investment
        
        results.append({
            'Stock': stock,
            'Symbol': symbol,
            'Sector': row.get('Sector', ''),
            'Strategy Bucket': row.get('Strategy Bucket', ''),
            'Suggested Allocation (%)': suggested_allocation_pct,
            'Max Investment (₹)': max_investment,
            'CMP': round(cmp, 2),
            'Calculated Investment (₹)': round(calculated_investment, 2),
            'Final Investment (₹)': round(actual_investment, 2),
            'Quantity': quantity,
            'Status': 'OK' if quantity > 0 else 'Qty=0'
        })
    
    # Create output DataFrame
    output_df = pd.DataFrame(results)
    
    # Save to CSV
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', f'buy_with_cmp_{timestamp}.csv')
    output_df.to_csv(output_path, index=False)
    
    # Also save without timestamp (try, might be locked)
    output_path_latest = os.path.join(os.path.dirname(__file__), '..', 'data', 'buy_with_cmp_latest.csv')
    try:
        output_df.to_csv(output_path_latest, index=False)
    except PermissionError:
        print(f"\nWarning: Could not overwrite {output_path_latest} (file may be open)")
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total stocks processed: {len(results)}")
    print(f"Stocks with CMP: {len([r for r in results if r['CMP'] > 0])}")
    print(f"Stocks with Quantity > 0: {len([r for r in results if r['Quantity'] > 0])}")
    print(f"Total Allocated: ₹{total_allocated:,.2f}")
    print(f"Remaining: ₹{TOTAL_INVESTMENT - total_allocated:,.2f}")
    print(f"\nOutput saved to:")
    print(f"  - {output_path}")
    print(f"  - {output_path_latest}")
    
    # Print table
    print(f"\n{'='*70}")
    print(f"DETAILED OUTPUT")
    print(f"{'='*70}")
    print(output_df.to_string(index=False))


if __name__ == "__main__":
    main()
