"""
Nifty 50 Today's Candle Performance Analyzer
Requires: pip install kiteconnect python-dotenv

Analyzes TODAY's candlestick for all Nifty 50 stocks:
- Candle color (Bullish/Bearish)
- Body size and strength
- Upper/Lower shadows
- Day's range and volatility
- Change vs previous close
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv
from kiteconnect import KiteConnect
import logging

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== CONFIGURATION ==========
API_KEY = os.getenv("API_KEY")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
HISTORICAL_CALL_DELAY = 0.35  # Rate limiting for Kite API
# ===================================

# Nifty 50 stocks (as of 2024)
NIFTY_50_STOCKS = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"
]


@dataclass
class TodayCandle:
    """Today's candle data with analysis"""
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    prev_close: float
    
    @property
    def change(self) -> float:
        """Price change from previous close"""
        return self.close - self.prev_close
    
    @property
    def change_pct(self) -> float:
        """Percentage change from previous close"""
        return (self.change / self.prev_close * 100) if self.prev_close > 0 else 0
    
    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)
    
    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)
    
    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low
    
    @property
    def total_range(self) -> float:
        return self.high - self.low
    
    @property
    def range_pct(self) -> float:
        """Day's range as percentage of open"""
        return (self.total_range / self.open * 100) if self.open > 0 else 0
    
    @property
    def is_bullish(self) -> bool:
        return self.close > self.open
    
    @property
    def is_bearish(self) -> bool:
        return self.close < self.open
    
    @property
    def body_ratio(self) -> float:
        """Body size as ratio of total range (0-1)"""
        return self.body_size / self.total_range if self.total_range > 0 else 0
    
    @property
    def candle_type(self) -> str:
        """Classify candle type based on body and shadows"""
        if self.total_range == 0:
            return "Flat"
        
        body_pct = self.body_size / self.close * 100
        
        # Doji: Very small body
        if body_pct < 0.3:
            if self.upper_shadow > self.lower_shadow * 2:
                return "Gravestone Doji"
            elif self.lower_shadow > self.upper_shadow * 2:
                return "Dragonfly Doji"
            return "Doji"
        
        # Marubozu: No shadows
        shadow_tolerance = self.total_range * 0.05
        if self.upper_shadow <= shadow_tolerance and self.lower_shadow <= shadow_tolerance:
            return "Bullish Marubozu" if self.is_bullish else "Bearish Marubozu"
        
        # Hammer/Hanging Man: Small body at top, long lower shadow
        if self.body_ratio < 0.35 and self.lower_shadow >= self.body_size * 2:
            if self.upper_shadow <= self.total_range * 0.1:
                return "Hammer" if self.is_bullish else "Hanging Man"
        
        # Shooting Star/Inverted Hammer: Small body at bottom, long upper shadow
        if self.body_ratio < 0.35 and self.upper_shadow >= self.body_size * 2:
            if self.lower_shadow <= self.total_range * 0.1:
                return "Shooting Star" if self.is_bearish else "Inverted Hammer"
        
        # Spinning Top: Small body, both shadows present
        if self.body_ratio < 0.3:
            return "Spinning Top"
        
        # Strong candles
        if self.body_ratio > 0.7:
            return "Strong Bullish" if self.is_bullish else "Strong Bearish"
        
        # Normal candles
        return "Bullish" if self.is_bullish else "Bearish"
    
    @property
    def strength_score(self) -> int:
        """Score from -100 (very bearish) to +100 (very bullish)"""
        # Base score from change
        score = min(max(self.change_pct * 10, -50), 50)
        
        # Body strength bonus
        if self.body_ratio > 0.6:
            score += 20 if self.is_bullish else -20
        
        # Shadow analysis
        if self.lower_shadow > self.upper_shadow * 1.5:
            score += 10  # Buying pressure
        elif self.upper_shadow > self.lower_shadow * 1.5:
            score -= 10  # Selling pressure
        
        return int(min(max(score, -100), 100))


class TodayCandleAnalyzer:
    """Analyzes today's candle for Nifty 50 stocks"""
    
    def __init__(self):
        self.kite = KiteConnect(api_key=API_KEY)
        self.kite.set_access_token(ACCESS_TOKEN)
        self._instruments_cache: Dict[str, List] = {}
        self._last_api_call: Optional[datetime] = None
    
    def _throttle_api_call(self):
        """Rate limiting for API calls"""
        if self._last_api_call:
            elapsed = (datetime.now() - self._last_api_call).total_seconds()
            if elapsed < HISTORICAL_CALL_DELAY:
                time.sleep(HISTORICAL_CALL_DELAY - elapsed)
        self._last_api_call = datetime.now()
    
    def _get_instruments(self, exchange: str = "NSE") -> List:
        """Get instruments list (cached)"""
        if exchange not in self._instruments_cache:
            self._instruments_cache[exchange] = self.kite.instruments(exchange)
        return self._instruments_cache[exchange]
    
    def get_today_candle(self, symbol: str) -> Optional[TodayCandle]:
        """Get today's OHLC data for a symbol"""
        try:
            # Get instrument token
            instruments = self._get_instruments("NSE")
            token = None
            for inst in instruments:
                if inst.get('tradingsymbol', '').upper() == symbol.upper():
                    token = inst.get('instrument_token')
                    break
            
            if not token:
                logger.debug(f"Token not found for {symbol}")
                return None
            
            # Rate limiting
            self._throttle_api_call()
            
            # Fetch last 2 days data (today + previous for prev_close)
            to_date = datetime.now()
            from_date = to_date - timedelta(days=5)  # Buffer for weekends
            
            data = self.kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day"
            )
            
            if len(data) < 2:
                return None
            
            today = data[-1]
            prev = data[-2]
            
            return TodayCandle(
                symbol=symbol,
                open=today['open'],
                high=today['high'],
                low=today['low'],
                close=today['close'],
                volume=today['volume'],
                prev_close=prev['close']
            )
            
        except Exception as e:
            logger.debug(f"Error fetching {symbol}: {e}")
            return None
    
    def analyze_all(self) -> List[TodayCandle]:
        """Analyze all Nifty 50 stocks"""
        results = []
        
        for i, symbol in enumerate(NIFTY_50_STOCKS, 1):
            print(f"\r📊 Fetching: {symbol} ({i}/{len(NIFTY_50_STOCKS)})", end="", flush=True)
            
            candle = self.get_today_candle(symbol)
            if candle:
                results.append(candle)
        
        print("\r" + " " * 50)
        return results


def get_candle_emoji(candle: TodayCandle) -> str:
    """Get emoji based on candle type"""
    ctype = candle.candle_type
    
    if "Bullish" in ctype or ctype == "Hammer":
        return "🟢"
    elif "Bearish" in ctype or ctype in ["Shooting Star", "Hanging Man"]:
        return "🔴"
    elif "Doji" in ctype or ctype == "Spinning Top":
        return "⚪"
    else:
        return "🟢" if candle.is_bullish else "🔴"


def format_volume(vol: int) -> str:
    """Format volume in lakhs/crores"""
    if vol >= 10000000:
        return f"{vol/10000000:.1f}Cr"
    elif vol >= 100000:
        return f"{vol/100000:.1f}L"
    else:
        return f"{vol/1000:.0f}K"


def main():
    print("=" * 90)
    print("NIFTY 50 - TODAY'S CANDLE PERFORMANCE")
    print("=" * 90)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    analyzer = TodayCandleAnalyzer()
    candles = analyzer.analyze_all()
    
    if not candles:
        print("❌ No data available. Market may be closed or API error.")
        return
    
    # Sort by change percentage
    candles.sort(key=lambda c: c.change_pct, reverse=True)
    
    # Summary stats
    gainers = [c for c in candles if c.change_pct > 0]
    losers = [c for c in candles if c.change_pct < 0]
    unchanged = [c for c in candles if c.change_pct == 0]
    
    print(f"📊 Analyzed: {len(candles)} stocks")
    print(f"🟢 Gainers: {len(gainers)} | 🔴 Losers: {len(losers)} | ⚪ Unchanged: {len(unchanged)}")
    print()
    
    # Display all stocks
    print("-" * 90)
    print(f"{'Symbol':<12} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Chg%':>8} {'Type':<18} {'Vol':<8}")
    print("-" * 90)
    
    for c in candles:
        emoji = get_candle_emoji(c)
        chg_str = f"{c.change_pct:+.2f}%"
        vol_str = format_volume(c.volume)
        
        print(f"{emoji} {c.symbol:<10} {c.open:>10.2f} {c.high:>10.2f} {c.low:>10.2f} {c.close:>10.2f} {chg_str:>8} {c.candle_type:<18} {vol_str:<8}")
    
    print("-" * 90)
    
    # Top Gainers
    print("\n" + "=" * 50)
    print("🔥 TOP 5 GAINERS")
    print("=" * 50)
    for c in candles[:5]:
        print(f"  🟢 {c.symbol:<12} {c.change_pct:+.2f}%  ({c.candle_type})")
    
    # Top Losers
    print("\n" + "=" * 50)
    print("📉 TOP 5 LOSERS")
    print("=" * 50)
    for c in candles[-5:]:
        print(f"  🔴 {c.symbol:<12} {c.change_pct:+.2f}%  ({c.candle_type})")
    
    # Strong Candle Patterns
    print("\n" + "=" * 50)
    print("💪 STRONG CANDLE PATTERNS")
    print("=" * 50)
    
    strong_patterns = [c for c in candles if c.candle_type in [
        "Strong Bullish", "Strong Bearish", "Bullish Marubozu", "Bearish Marubozu"
    ]]
    
    if strong_patterns:
        for c in strong_patterns:
            emoji = "🟢" if "Bullish" in c.candle_type else "🔴"
            print(f"  {emoji} {c.symbol:<12} {c.candle_type:<18} {c.change_pct:+.2f}%")
    else:
        print("  No strong patterns today")
    
    # Reversal Signals
    print("\n" + "=" * 50)
    print("🔄 REVERSAL PATTERNS")
    print("=" * 50)
    
    reversal_patterns = [c for c in candles if c.candle_type in [
        "Hammer", "Shooting Star", "Hanging Man", "Inverted Hammer",
        "Doji", "Dragonfly Doji", "Gravestone Doji"
    ]]
    
    if reversal_patterns:
        for c in reversal_patterns:
            if c.candle_type in ["Hammer", "Dragonfly Doji", "Inverted Hammer"]:
                emoji = "🟢"
                signal = "Bullish reversal"
            elif c.candle_type in ["Shooting Star", "Hanging Man", "Gravestone Doji"]:
                emoji = "🔴"
                signal = "Bearish reversal"
            else:
                emoji = "⚪"
                signal = "Indecision"
            print(f"  {emoji} {c.symbol:<12} {c.candle_type:<18} → {signal}")
    else:
        print("  No reversal patterns today")
    
    # Strength Analysis
    print("\n" + "=" * 50)
    print("📊 STRENGTH SCORES (Top 10)")
    print("=" * 50)
    
    candles_by_strength = sorted(candles, key=lambda c: c.strength_score, reverse=True)
    
    print(f"{'Symbol':<12} {'Score':>8} {'Interpretation':<30}")
    print("-" * 50)
    
    for c in candles_by_strength[:10]:
        score = c.strength_score
        if score >= 50:
            interp = "Very Bullish 🟢🟢"
        elif score >= 20:
            interp = "Bullish 🟢"
        elif score >= -20:
            interp = "Neutral ⚪"
        elif score >= -50:
            interp = "Bearish 🔴"
        else:
            interp = "Very Bearish 🔴🔴"
        
        print(f"{c.symbol:<12} {score:>+8} {interp:<30}")
    
    # Market Summary
    print("\n" + "=" * 50)
    print("📈 MARKET SUMMARY")
    print("=" * 50)
    
    avg_change = sum(c.change_pct for c in candles) / len(candles)
    bullish_count = sum(1 for c in candles if c.is_bullish)
    bearish_count = sum(1 for c in candles if c.is_bearish)
    
    print(f"  Average Change:    {avg_change:+.2f}%")
    print(f"  Bullish Candles:   {bullish_count}/{len(candles)}")
    print(f"  Bearish Candles:   {bearish_count}/{len(candles)}")
    
    if avg_change > 0.5:
        print(f"\n  📊 Market Sentiment: BULLISH 🟢")
    elif avg_change < -0.5:
        print(f"\n  📊 Market Sentiment: BEARISH 🔴")
    else:
        print(f"\n  📊 Market Sentiment: NEUTRAL ⚪")
    
    print("\n" + "=" * 90)


if __name__ == "__main__":
    main()
