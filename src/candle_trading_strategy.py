"""
Candle-Based Trading Strategy
Requires: pip install kiteconnect python-dotenv

Uses nifty50_candle_analysis.py output to:
1. Filter stocks with bullish candle patterns
2. Generate buy recommendations
3. Optionally place orders via Kite API

Strategy Rules:
- BUY: Strong Bullish, Bullish Marubozu, Hammer, Dragonfly Doji
- SELL: Strong Bearish, Bearish Marubozu, Shooting Star, Hanging Man
- Minimum strength score threshold for action
"""

import os
import csv
from datetime import datetime
from typing import List, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv
from kiteconnect import KiteConnect
import logging

# Import from candle analysis module
from nifty50_candle_analysis import TodayCandleAnalyzer, TodayCandle

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== CONFIGURATION ==========
API_KEY = os.getenv("API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

# Strategy Settings
MIN_STRENGTH_SCORE = 30          # Minimum score for BUY (-100 to +100)
MAX_STRENGTH_SCORE = -30         # Maximum score for SELL
MIN_CHANGE_PCT = 0.5             # Minimum % change for signal validity
MAX_STOCKS_TO_BUY = 10           # Max stocks to buy per day
BUDGET_PER_STOCK = 25000         # Budget allocation per stock (₹)

# Order Settings
DRY_RUN = True                   # Set False to place real orders
ORDER_TYPE = "LIMIT"             # LIMIT or MARKET
LIMIT_PRICE_BUFFER = 0.002       # 0.2% above LTP for limit orders
OUTPUT_CSV = "data/candle_recommendations.csv"

# Bullish candle types (BUY signals)
BULLISH_PATTERNS = [
    "Strong Bullish",
    "Bullish Marubozu",
    "Bullish",
    "Hammer",
    "Inverted Hammer",
    "Dragonfly Doji"
]

# Bearish candle types (SELL signals)
BEARISH_PATTERNS = [
    "Strong Bearish",
    "Bearish Marubozu",
    "Bearish",
    "Shooting Star",
    "Hanging Man",
    "Gravestone Doji"
]
# ===================================


@dataclass
class TradeRecommendation:
    """Trading recommendation based on candle analysis"""
    symbol: str
    action: str  # BUY, SELL, HOLD
    candle_type: str
    strength_score: int
    change_pct: float
    close_price: float
    volume: int
    reason: str
    quantity: int = 0
    
    def to_dict(self):
        return {
            'Symbol': self.symbol,
            'Action': self.action,
            'Candle_Type': self.candle_type,
            'Strength_Score': self.strength_score,
            'Change_Pct': f"{self.change_pct:.2f}%",
            'Close_Price': self.close_price,
            'Quantity': self.quantity,
            'Reason': self.reason
        }


def analyze_candle_for_trade(candle: TodayCandle) -> TradeRecommendation:
    """Analyze a candle and generate trade recommendation"""
    
    action = "HOLD"
    reason = ""
    
    # Check for BUY signals
    if candle.candle_type in BULLISH_PATTERNS:
        if candle.strength_score >= MIN_STRENGTH_SCORE:
            action = "BUY"
            reason = f"Bullish pattern ({candle.candle_type}) with strong score"
        elif candle.change_pct >= MIN_CHANGE_PCT:
            action = "BUY"
            reason = f"Bullish pattern ({candle.candle_type}) with good momentum"
        else:
            reason = f"Bullish but weak (score: {candle.strength_score})"
    
    # Check for SELL signals
    elif candle.candle_type in BEARISH_PATTERNS:
        if candle.strength_score <= MAX_STRENGTH_SCORE:
            action = "SELL"
            reason = f"Bearish pattern ({candle.candle_type}) with weak score"
        elif candle.change_pct <= -MIN_CHANGE_PCT:
            action = "SELL"
            reason = f"Bearish pattern ({candle.candle_type}) with negative momentum"
        else:
            reason = f"Bearish but not severe (score: {candle.strength_score})"
    
    # Neutral patterns
    else:
        reason = f"Neutral pattern ({candle.candle_type})"
    
    # Calculate quantity based on budget
    quantity = 0
    if action == "BUY" and candle.close > 0:
        quantity = int(BUDGET_PER_STOCK / candle.close)
    
    return TradeRecommendation(
        symbol=candle.symbol,
        action=action,
        candle_type=candle.candle_type,
        strength_score=candle.strength_score,
        change_pct=candle.change_pct,
        close_price=candle.close,
        volume=candle.volume,
        reason=reason,
        quantity=quantity
    )


def get_buy_recommendations(candles: List[TodayCandle]) -> List[TradeRecommendation]:
    """Filter and rank BUY recommendations"""
    
    recommendations = []
    
    for candle in candles:
        rec = analyze_candle_for_trade(candle)
        if rec.action == "BUY":
            recommendations.append(rec)
    
    # Sort by strength score (highest first)
    recommendations.sort(key=lambda r: r.strength_score, reverse=True)
    
    # Limit to max stocks
    return recommendations[:MAX_STOCKS_TO_BUY]


def get_sell_recommendations(candles: List[TodayCandle]) -> List[TradeRecommendation]:
    """Filter and rank SELL recommendations"""
    
    recommendations = []
    
    for candle in candles:
        rec = analyze_candle_for_trade(candle)
        if rec.action == "SELL":
            recommendations.append(rec)
    
    # Sort by strength score (lowest/most bearish first)
    recommendations.sort(key=lambda r: r.strength_score)
    
    return recommendations


def save_to_csv(recommendations: List[TradeRecommendation], filename: str):
    """Save recommendations to CSV"""
    
    if not recommendations:
        return
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Symbol', 'Action', 'Candle_Type', 
                                                'Strength_Score', 'Change_Pct', 
                                                'Close_Price', 'Quantity', 'Reason'])
        writer.writeheader()
        for rec in recommendations:
            writer.writerow(rec.to_dict())
    
    print(f"📁 Saved to {filename}")


def place_orders(kite: KiteConnect, recommendations: List[TradeRecommendation]):
    """Place buy orders for recommendations"""
    
    if not recommendations:
        print("No orders to place.")
        return
    
    print("\n" + "=" * 60)
    print("PLACING ORDERS")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for rec in recommendations:
        try:
            # Calculate limit price
            if ORDER_TYPE == "LIMIT":
                price = round(rec.close_price * (1 + LIMIT_PRICE_BUFFER), 2)
                order_type = kite.ORDER_TYPE_LIMIT
            else:
                price = None
                order_type = kite.ORDER_TYPE_MARKET
            
            if DRY_RUN:
                price_str = f"@ ₹{price:.2f}" if price else "@ MARKET"
                print(f"[DRY RUN] Would BUY: {rec.symbol} x {rec.quantity} {price_str}")
                print(f"          Reason: {rec.reason}")
                success_count += 1
            else:
                order_params = {
                    'tradingsymbol': rec.symbol,
                    'exchange': 'NSE',
                    'transaction_type': kite.TRANSACTION_TYPE_BUY,
                    'quantity': rec.quantity,
                    'order_type': order_type,
                    'product': kite.PRODUCT_CNC,
                    'variety': kite.VARIETY_REGULAR
                }
                
                if price:
                    order_params['price'] = price
                
                order_id = kite.place_order(**order_params)
                print(f"✅ BUY: {rec.symbol} x {rec.quantity} - Order ID: {order_id}")
                success_count += 1
        
        except Exception as e:
            print(f"❌ FAILED: {rec.symbol} - {e}")
            failed_count += 1
    
    print(f"\n✅ Success: {success_count} | ❌ Failed: {failed_count}")


def generate_order_book(recommendations: List[TradeRecommendation], filename: str = "data/order_book.csv"):
    """Generate order_book.csv compatible with buy_stocks.py"""
    
    if not recommendations:
        print("No recommendations to save.")
        return
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Symbol', 'Quantity', 'Price', 'Transaction', 'Variety', 'Product', 'Order_Type', 'Rank'])
        
        for i, rec in enumerate(recommendations, 1):
            writer.writerow([
                rec.symbol,
                rec.quantity,
                rec.close_price,
                'BUY',
                'regular',
                'CNC',
                'LIMIT',
                i
            ])
    
    print(f"📁 Order book saved to {filename}")
    print(f"   Run 'python buy_stocks.py' to execute these orders")


def main():
    print("=" * 70)
    print("CANDLE-BASED TRADING STRATEGY")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Budget per stock: ₹{BUDGET_PER_STOCK:,}")
    print(f"Max stocks to buy: {MAX_STOCKS_TO_BUY}")
    
    if DRY_RUN:
        print("\n⚠️  DRY RUN MODE - No actual orders will be placed")
    else:
        print("\n🔴 LIVE MODE - Orders will be executed!")
    
    # Step 1: Analyze candles
    print("\n" + "=" * 70)
    print("STEP 1: ANALYZING CANDLE PATTERNS")
    print("=" * 70)
    
    analyzer = TodayCandleAnalyzer()
    candles = analyzer.analyze_all()
    
    if not candles:
        print("❌ No candle data available. Market may be closed.")
        return
    
    print(f"\n✅ Analyzed {len(candles)} stocks")
    
    # Step 2: Generate recommendations
    print("\n" + "=" * 70)
    print("STEP 2: GENERATING RECOMMENDATIONS")
    print("=" * 70)
    
    buy_recs = get_buy_recommendations(candles)
    sell_recs = get_sell_recommendations(candles)
    
    print(f"\n🟢 BUY Recommendations: {len(buy_recs)}")
    print(f"🔴 SELL Recommendations: {len(sell_recs)}")
    
    # Display BUY recommendations
    if buy_recs:
        print("\n--- BUY RECOMMENDATIONS ---")
        print(f"{'Rank':<5} {'Symbol':<12} {'Type':<18} {'Score':>8} {'Change':>8} {'Price':>10} {'Qty':>6}")
        print("-" * 70)
        
        total_investment = 0
        for i, rec in enumerate(buy_recs, 1):
            print(f"{i:<5} {rec.symbol:<12} {rec.candle_type:<18} {rec.strength_score:>+8} {rec.change_pct:>+7.2f}% ₹{rec.close_price:>9.2f} {rec.quantity:>6}")
            total_investment += rec.close_price * rec.quantity
        
        print("-" * 70)
        print(f"Total Investment: ₹{total_investment:,.2f}")
    
    # Display SELL recommendations
    if sell_recs:
        print("\n--- SELL RECOMMENDATIONS ---")
        print(f"{'Symbol':<12} {'Type':<18} {'Score':>8} {'Change':>8} {'Reason':<30}")
        print("-" * 70)
        
        for rec in sell_recs[:10]:  # Top 10 bearish
            print(f"{rec.symbol:<12} {rec.candle_type:<18} {rec.strength_score:>+8} {rec.change_pct:>+7.2f}% {rec.reason[:30]}")
    
    # Step 3: Save recommendations
    print("\n" + "=" * 70)
    print("STEP 3: SAVING RESULTS")
    print("=" * 70)
    
    # Save all recommendations to CSV
    all_recs = buy_recs + sell_recs
    save_to_csv(all_recs, OUTPUT_CSV)
    
    # Step 4: Action menu
    print("\n" + "=" * 70)
    print("STEP 4: SELECT ACTION")
    print("=" * 70)
    
    if not buy_recs:
        print("\n⚠️  No BUY recommendations today based on candle patterns.")
        return
    
    print("\nOptions:")
    print("  1. Generate order_book.csv (for buy_stocks.py)")
    print("  2. Place orders directly")
    print("  3. Exit")
    
    choice = input("\nEnter choice (1/2/3): ").strip()
    
    if choice == "1":
        generate_order_book(buy_recs)
    
    elif choice == "2":
        if not DRY_RUN:
            confirm = input("Type 'CONFIRM' to place real orders: ")
            if confirm != "CONFIRM":
                print("Aborted.")
                return
        
        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(ACCESS_TOKEN)
        place_orders(kite, buy_recs)
    
    else:
        print("Exiting without action.")
    
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
