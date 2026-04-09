"""
Market Agent - Daily Market Analysis
Provides:
1. Top Gainers (stocks with highest % gain today)
2. Top Losers (stocks with highest % loss today)
3. New Market Heroes (high momentum, volume breakout stocks)
4. Best Sector Today with Top 5 stocks

Usage in Streamlit UI via "Day Run" button.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from dotenv import load_dotenv
from kiteconnect import KiteConnect

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
REPO_ROOT = Path(__file__).resolve().parents[1]
_src_env = REPO_ROOT / "src" / ".env"
_root_env = REPO_ROOT / ".env"
if _src_env.exists():
    load_dotenv(dotenv_path=_src_env, override=False)
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)


# ==================== SECTOR MAPPING ====================
# Common Indian stocks to sector mapping
SECTOR_MAPPING = {
    # Banking & Finance
    'HDFCBANK': 'Banking', 'ICICIBANK': 'Banking', 'SBIN': 'Banking',
    'KOTAKBANK': 'Banking', 'AXISBANK': 'Banking', 'INDUSINDBK': 'Banking',
    'BANKBARODA': 'Banking', 'PNB': 'Banking', 'FEDERALBNK': 'Banking',
    'IDFCFIRSTB': 'Banking', 'BANDHANBNK': 'Banking', 'AUBANK': 'Banking',
    'BAJFINANCE': 'NBFC', 'BAJAJFINSV': 'NBFC', 'HDFCLIFE': 'Insurance',
    'SBILIFE': 'Insurance', 'ICICIPRULI': 'Insurance', 'ICICIGI': 'Insurance',
    'CHOLAFIN': 'NBFC', 'SHRIRAMFIN': 'NBFC', 'MUTHOOTFIN': 'NBFC',
    
    # IT
    'TCS': 'IT', 'INFY': 'IT', 'WIPRO': 'IT', 'HCLTECH': 'IT',
    'TECHM': 'IT', 'LTIM': 'IT', 'PERSISTENT': 'IT', 'COFORGE': 'IT',
    'MPHASIS': 'IT', 'LTTS': 'IT', 'MINDTREE': 'IT', 'NIITTECH': 'IT',
    
    # Pharma/Healthcare
    'SUNPHARMA': 'Pharma', 'DRREDDY': 'Pharma', 'CIPLA': 'Pharma',
    'DIVISLAB': 'Pharma', 'BIOCON': 'Pharma', 'LUPIN': 'Pharma',
    'AUROPHARMA': 'Pharma', 'TORNTPHARM': 'Pharma', 'ALKEM': 'Pharma',
    'APOLLOHOSP': 'Healthcare', 'MAXHEALTH': 'Healthcare', 'FORTIS': 'Healthcare',
    
    # Auto
    'MARUTI': 'Auto', 'TATAMOTORS': 'Auto', 'M&M': 'Auto',
    'BAJAJ-AUTO': 'Auto', 'HEROMOTOCO': 'Auto', 'EICHERMOT': 'Auto',
    'ASHOKLEY': 'Auto', 'TVSMOTOR': 'Auto', 'BHARATFORG': 'Auto',
    
    # Energy/Oil & Gas
    'RELIANCE': 'Energy', 'ONGC': 'Energy', 'IOC': 'Energy',
    'BPCL': 'Energy', 'HPCL': 'Energy', 'GAIL': 'Energy',
    'NTPC': 'Power', 'POWERGRID': 'Power', 'ADANIGREEN': 'Power',
    'TATAPOWER': 'Power', 'ADANIPOWER': 'Power', 'TORNTPOWER': 'Power',
    'ADANIENT': 'Conglomerate', 'ADANIPORTS': 'Ports',
    
    # Metals
    'TATASTEEL': 'Metals', 'JSWSTEEL': 'Metals', 'HINDALCO': 'Metals',
    'VEDL': 'Metals', 'COALINDIA': 'Metals', 'NMDC': 'Metals',
    'SAIL': 'Metals', 'NATIONALUM': 'Metals', 'JINDALSTEL': 'Metals',
    
    # FMCG
    'HINDUNILVR': 'FMCG', 'ITC': 'FMCG', 'NESTLEIND': 'FMCG',
    'BRITANNIA': 'FMCG', 'DABUR': 'FMCG', 'MARICO': 'FMCG',
    'COLPAL': 'FMCG', 'GODREJCP': 'FMCG', 'TATACONSUM': 'FMCG',
    'VBL': 'FMCG', 'MCDOWELL-N': 'FMCG', 'UBL': 'FMCG',
    
    # Cement/Construction
    'ULTRACEMCO': 'Cement', 'SHREECEM': 'Cement', 'AMBUJACEM': 'Cement',
    'ACC': 'Cement', 'DALMIACEM': 'Cement', 'RAMCOCEM': 'Cement',
    'LT': 'Infrastructure', 'LARSEN': 'Infrastructure', 
    'DLF': 'Realty', 'GODREJPROP': 'Realty', 'OBEROIRLTY': 'Realty', 
    'PRESTIGE': 'Realty', 'BRIGADE': 'Realty',
    
    # Telecom/Internet
    'BHARTIARTL': 'Telecom', 'INDIAMART': 'Telecom', 'ZOMATO': 'Internet',
    'NAUKRI': 'Internet', 'PAYTM': 'Internet', 'POLICYBZR': 'Insurance',
    
    # Consumer Durables
    'TITAN': 'Consumer', 'HAVELLS': 'Consumer', 'VOLTAS': 'Consumer',
    'WHIRLPOOL': 'Consumer', 'BLUESTAR': 'Consumer', 'CROMPTON': 'Consumer',
    
    # Defense/Aerospace
    'HAL': 'Defense', 'BEL': 'Defense', 'BDL': 'Defense',
    'PARAS': 'Defense', 'COCHINSHIP': 'Defense', 'MAZAGON': 'Defense',
    'IDEAFORGE': 'Defense', 'DATAPATTNS': 'Defense',
    
    # Capital Goods
    'SIEMENS': 'Capital Goods', 'ABB': 'Capital Goods', 'CUMMINSIND': 'Capital Goods',
    'THERMAX': 'Capital Goods', 'HONAUT': 'Capital Goods',
}

# NIFTY 50 + key stocks for market analysis
MARKET_WATCHLIST = [
    # NIFTY 50
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY', 'HINDUNILVR', 'ITC', 
    'SBIN', 'BHARTIARTL', 'KOTAKBANK', 'LT', 'AXISBANK', 'ASIANPAINT', 
    'MARUTI', 'TITAN', 'SUNPHARMA', 'BAJFINANCE', 'WIPRO', 'ULTRACEMCO',
    'HCLTECH', 'NTPC', 'POWERGRID', 'TATAMOTORS', 'M&M', 'ADANIENT',
    'TATASTEEL', 'NESTLEIND', 'JSWSTEEL', 'TECHM', 'INDUSINDBK',
    'BAJAJFINSV', 'ONGC', 'ADANIPORTS', 'COALINDIA', 'GRASIM', 'BPCL',
    'DRREDDY', 'BRITANNIA', 'CIPLA', 'DIVISLAB', 'EICHERMOT', 'APOLLOHOSP',
    'HEROMOTOCO', 'TATACONSUM', 'BAJAJ-AUTO', 'SBILIFE', 'HINDALCO', 
    'LTIM', 'HDFCLIFE', 'VEDL',
    
    # Additional key stocks
    'PERSISTENT', 'COFORGE', 'MPHASIS', 'LTTS', 'BANDHANBNK', 'AUBANK',
    'DALMIACEM', 'RAMCOCEM', 'TATAPOWER', 'HAL', 'BEL', 'IDEAFORGE',
    'ZOMATO', 'PAYTM', 'POLICYBZR', 'DLF', 'GODREJPROP', 'OBEROIRLTY',
    'FORTIS', 'MAXHEALTH', 'AUROPHARMA', 'TORNTPHARM', 'FEDERALBNK',
    'PNB', 'BANKBARODA', 'CHOLAFIN', 'SHRIRAMFIN', 'VOLTAS', 'HAVELLS',
    'CROMPTON', 'ABB', 'SIEMENS', 'CUMMINSIND', 'VBL',
]


@dataclass
class MarketStock:
    """Data class for market stock analysis"""
    symbol: str
    ltp: float = 0.0
    open_price: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0  # Previous close
    volume: int = 0
    change_pct: float = 0.0
    sector: str = "Unknown"
    momentum_score: int = 0
    avg_volume: int = 0
    volume_ratio: float = 0.0  # Today volume / avg volume


@dataclass 
class SectorAnalysis:
    """Sector performance analysis"""
    sector: str
    avg_change_pct: float = 0.0
    stocks_count: int = 0
    gainers: int = 0
    losers: int = 0
    top_stocks: List[MarketStock] = field(default_factory=list)


class MarketAgent:
    """Market analysis agent for daily market insights"""
    
    def __init__(self, kite: Optional[KiteConnect] = None, access_token: Optional[str] = None):
        """Initialize with KiteConnect instance or access_token"""
        self.kite = kite
        self._access_token = access_token or os.getenv("ACCESS_TOKEN")
        self._api_key = os.getenv("API_KEY")
        self._connected = False
        self._instruments_cache: List[Dict] = []
        self._last_run: Optional[datetime] = None
        self._cache: Dict[str, Any] = {}
        
    def connect(self) -> bool:
        """Connect to Kite API"""
        if self.kite and self._connected:
            return True
            
        if not self._api_key or not self._access_token:
            logger.warning("API_KEY or ACCESS_TOKEN not configured")
            return False
            
        try:
            if not self.kite:
                self.kite = KiteConnect(api_key=self._api_key)
            self.kite.set_access_token(self._access_token)
            # Validate connection
            self.kite.profile()
            self._connected = True
            logger.info("MarketAgent connected successfully")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def _get_quote_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get quote data for multiple symbols"""
        if not self.connect():
            return {}
            
        try:
            instruments = [f"NSE:{s}" for s in symbols]
            # kite.quote returns OHLC, volume, etc.
            quotes = self.kite.quote(instruments)
            return quotes
        except Exception as e:
            logger.error(f"Error fetching quotes: {e}")
            return {}
    
    def _get_ohlc_data(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get OHLC data for multiple symbols (lighter than quote)"""
        if not self.connect():
            return {}
            
        try:
            instruments = [f"NSE:{s}" for s in symbols]
            ohlc = self.kite.ohlc(instruments)
            return ohlc
        except Exception as e:
            logger.error(f"Error fetching OHLC: {e}")
            return {}
    
    def _get_historical_volume(self, symbol: str, days: int = 20) -> float:
        """Get average volume for past N days"""
        if not self.connect():
            return 0
            
        try:
            # Get instrument token
            if not self._instruments_cache:
                self._instruments_cache = self.kite.instruments("NSE")
            
            token = None
            for inst in self._instruments_cache:
                if inst.get('tradingsymbol') == symbol:
                    token = inst.get('instrument_token')
                    break
            
            if not token:
                return 0
            
            to_date = datetime.now()
            from_date = to_date - timedelta(days=days + 5)  # Extra days for holidays
            
            data = self.kite.historical_data(
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                "day"
            )
            
            if len(data) >= days:
                volumes = [d['volume'] for d in data[-days:]]
                return sum(volumes) / len(volumes)
            return 0
        except Exception as e:
            logger.debug(f"Error fetching historical volume for {symbol}: {e}")
            return 0
    
    def get_sector(self, symbol: str) -> str:
        """Get sector for a symbol"""
        return SECTOR_MAPPING.get(symbol.upper(), "Unknown")
    
    def analyze_market(self, watchlist: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Main analysis function - runs full market analysis
        Returns dict with gainers, losers, heroes, sector analysis
        """
        symbols = watchlist or MARKET_WATCHLIST
        
        logger.info(f"Analyzing {len(symbols)} stocks...")
        
        # Get quote data for all symbols
        quotes = self._get_quote_data(symbols)
        
        if not quotes:
            return {
                "status": "error",
                "message": "Failed to fetch market data. Check connection.",
                "timestamp": datetime.now().isoformat()
            }
        
        # Process all stocks
        stocks: List[MarketStock] = []
        
        for symbol in symbols:
            key = f"NSE:{symbol}"
            if key not in quotes:
                continue
                
            q = quotes[key]
            ohlc = q.get('ohlc', {})
            
            ltp = q.get('last_price', 0)
            open_price = ohlc.get('open', 0)
            high = ohlc.get('high', 0)
            low = ohlc.get('low', 0)
            close = ohlc.get('close', 0)  # Previous close
            volume = q.get('volume', 0)
            
            # Calculate change %
            if close and close > 0:
                change_pct = ((ltp - close) / close) * 100
            else:
                change_pct = 0
            
            stock = MarketStock(
                symbol=symbol,
                ltp=ltp,
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
                change_pct=round(change_pct, 2),
                sector=self.get_sector(symbol)
            )
            
            stocks.append(stock)
        
        if not stocks:
            return {
                "status": "error", 
                "message": "No stock data available",
                "timestamp": datetime.now().isoformat()
            }
        
        # Sort for gainers and losers
        sorted_by_change = sorted(stocks, key=lambda x: x.change_pct, reverse=True)
        
        top_gainers = sorted_by_change[:10]
        top_losers = sorted_by_change[-10:][::-1]  # Reverse to show worst first
        
        # Find market heroes (high momentum characteristics)
        heroes = self._identify_heroes(stocks, quotes)
        
        # Sector analysis
        sector_analysis = self._analyze_sectors(stocks)
        
        # Best performing sector
        best_sector = max(sector_analysis.values(), key=lambda x: x.avg_change_pct) if sector_analysis else None
        
        self._last_run = datetime.now()
        
        return {
            "status": "success",
            "timestamp": self._last_run.isoformat(),
            "total_stocks": len(stocks),
            "market_breadth": {
                "gainers": len([s for s in stocks if s.change_pct > 0]),
                "losers": len([s for s in stocks if s.change_pct < 0]),
                "unchanged": len([s for s in stocks if s.change_pct == 0])
            },
            "top_gainers": [self._stock_to_dict(s) for s in top_gainers],
            "top_losers": [self._stock_to_dict(s) for s in top_losers],
            "market_heroes": [self._stock_to_dict(s) for s in heroes],
            "best_sector": {
                "name": best_sector.sector if best_sector else "N/A",
                "avg_change": best_sector.avg_change_pct if best_sector else 0,
                "stocks_count": best_sector.stocks_count if best_sector else 0,
                "top_5": [self._stock_to_dict(s) for s in (best_sector.top_stocks[:5] if best_sector else [])]
            },
            "all_sectors": {k: self._sector_to_dict(v) for k, v in sector_analysis.items()}
        }
    
    def _identify_heroes(self, stocks: List[MarketStock], quotes: Dict) -> List[MarketStock]:
        """
        Identify 'Market Heroes' - stocks showing exceptional momentum
        Criteria:
        1. Change > 2% (strong move)
        2. Trading near day's high (bullish)
        3. Higher than average volume (interest)
        """
        heroes = []
        
        for stock in stocks:
            # Must be gaining
            if stock.change_pct < 2.0:
                continue
            
            # Trading near high (within 1% of day high)
            if stock.high > 0:
                dist_from_high = ((stock.high - stock.ltp) / stock.high) * 100
                if dist_from_high > 1.5:
                    continue
            
            # Check volume (basic check - volume > 0)
            if stock.volume <= 0:
                continue
            
            # Calculate momentum score
            score = 0
            
            # Change contribution (max 40 points)
            if stock.change_pct >= 5:
                score += 40
            elif stock.change_pct >= 3:
                score += 30
            elif stock.change_pct >= 2:
                score += 20
            
            # Near high contribution (max 30 points)
            if stock.high > 0:
                dist = ((stock.high - stock.ltp) / stock.high) * 100
                if dist < 0.5:
                    score += 30
                elif dist < 1.0:
                    score += 20
                elif dist < 1.5:
                    score += 10
            
            # Range expansion (price moving significantly, max 30 points)
            if stock.close and stock.close > 0:
                range_pct = ((stock.high - stock.low) / stock.close) * 100
                if range_pct >= 4:
                    score += 30
                elif range_pct >= 2.5:
                    score += 20
                elif range_pct >= 1.5:
                    score += 10
            
            stock.momentum_score = score
            
            if score >= 50:  # Minimum threshold
                heroes.append(stock)
        
        # Sort by momentum score and return top 10
        heroes.sort(key=lambda x: x.momentum_score, reverse=True)
        return heroes[:10]
    
    def _analyze_sectors(self, stocks: List[MarketStock]) -> Dict[str, SectorAnalysis]:
        """Analyze performance by sector"""
        sectors: Dict[str, List[MarketStock]] = defaultdict(list)
        
        for stock in stocks:
            if stock.sector and stock.sector != "Unknown":
                sectors[stock.sector].append(stock)
        
        analysis = {}
        
        for sector, sector_stocks in sectors.items():
            if len(sector_stocks) < 2:  # Skip sectors with very few stocks
                continue
                
            changes = [s.change_pct for s in sector_stocks]
            avg_change = sum(changes) / len(changes)
            
            # Sort sector stocks by change
            sector_stocks_sorted = sorted(sector_stocks, key=lambda x: x.change_pct, reverse=True)
            
            analysis[sector] = SectorAnalysis(
                sector=sector,
                avg_change_pct=round(avg_change, 2),
                stocks_count=len(sector_stocks),
                gainers=len([s for s in sector_stocks if s.change_pct > 0]),
                losers=len([s for s in sector_stocks if s.change_pct < 0]),
                top_stocks=sector_stocks_sorted
            )
        
        return analysis
    
    def _stock_to_dict(self, stock: MarketStock) -> Dict:
        """Convert MarketStock to dict for JSON serialization"""
        return {
            "symbol": stock.symbol,
            "ltp": stock.ltp,
            "open": stock.open_price,
            "high": stock.high,
            "low": stock.low,
            "prev_close": stock.close,
            "change_pct": stock.change_pct,
            "volume": stock.volume,
            "sector": stock.sector,
            "momentum_score": stock.momentum_score
        }
    
    def _sector_to_dict(self, sector: SectorAnalysis) -> Dict:
        """Convert SectorAnalysis to dict"""
        return {
            "sector": sector.sector,
            "avg_change_pct": sector.avg_change_pct,
            "stocks_count": sector.stocks_count,
            "gainers": sector.gainers,
            "losers": sector.losers,
            "top_5": [self._stock_to_dict(s) for s in sector.top_stocks[:5]]
        }
    
    def get_quick_summary(self) -> str:
        """Get a quick text summary of market status"""
        result = self.analyze_market()
        
        if result.get("status") != "success":
            return f"❌ Market analysis failed: {result.get('message', 'Unknown error')}"
        
        breadth = result.get("market_breadth", {})
        best = result.get("best_sector", {})
        
        summary = f"""
📊 **Market Summary** ({result.get('timestamp', '')[:16]})

**Breadth**: 🟢 {breadth.get('gainers', 0)} gainers | 🔴 {breadth.get('losers', 0)} losers

**Best Sector**: {best.get('name', 'N/A')} ({best.get('avg_change', 0):+.2f}%)

**Top Gainers**:
"""
        for g in result.get("top_gainers", [])[:5]:
            summary += f"  • {g['symbol']}: ₹{g['ltp']:,.2f} ({g['change_pct']:+.2f}%)\n"
        
        summary += "\n**Top Losers**:\n"
        for l in result.get("top_losers", [])[:5]:
            summary += f"  • {l['symbol']}: ₹{l['ltp']:,.2f} ({l['change_pct']:+.2f}%)\n"
        
        if result.get("market_heroes"):
            summary += "\n**🦸 Market Heroes** (High Momentum):\n"
            for h in result.get("market_heroes", [])[:5]:
                summary += f"  • {h['symbol']}: {h['change_pct']:+.2f}% (Score: {h['momentum_score']})\n"
        
        return summary


# ==================== CONVENIENCE FUNCTIONS ====================

def run_market_analysis(kite: Optional[KiteConnect] = None, access_token: Optional[str] = None) -> Dict:
    """
    Convenience function to run market analysis
    Can be called from UI or CLI
    """
    agent = MarketAgent(kite=kite, access_token=access_token)
    return agent.analyze_market()


def get_market_summary(kite: Optional[KiteConnect] = None, access_token: Optional[str] = None) -> str:
    """Get text summary of market"""
    agent = MarketAgent(kite=kite, access_token=access_token)
    return agent.get_quick_summary()


if __name__ == "__main__":
    # Test run
    print("Running Market Agent analysis...")
    result = run_market_analysis()
    
    if result.get("status") == "success":
        print(f"\nAnalyzed {result['total_stocks']} stocks")
        print(f"Market Breadth: {result['market_breadth']}")
        print(f"\nBest Sector: {result['best_sector']['name']} ({result['best_sector']['avg_change']:+.2f}%)")
        
        print("\nTop 5 Gainers:")
        for g in result['top_gainers'][:5]:
            print(f"  {g['symbol']}: {g['change_pct']:+.2f}%")
        
        print("\nTop 5 Losers:")
        for l in result['top_losers'][:5]:
            print(f"  {l['symbol']}: {l['change_pct']:+.2f}%")
    else:
        print(f"Error: {result.get('message')}")
