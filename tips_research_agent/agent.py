"""Tips Research Data Agent

Goal:
- Read `data/research_data.csv`
- Fetch live market prices (uses Zerodha Kite LTP if configured)
- Recompute Allocation/Quantity/TargetValue based on DAILY_BUDGET
- Write `data/tips_research_data.csv` in the same format

Run:
  adk run tips_research_agent

Then prompt:
  Generate tips_research_data.csv for Top15 using DAILY_BUDGET.

Notes:
- This agent is designed to ONLY operate on symbols present in research_data.csv.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google.adk.agents import Agent


def _load_env() -> None:
    """Load env from `src/.env` then project-root `.env` if present."""
    root = Path(__file__).resolve().parents[1]
    src_env = root / "src" / ".env"
    root_env = root / ".env"

    if src_env.exists():
        # First load (non-overriding) so existing shell env can take precedence.
        load_dotenv(dotenv_path=src_env, override=False)
        # If required keys are still missing/blank, override from src/.env.
        if not (os.getenv("API_KEY") or "").strip() or not (os.getenv("ACCESS_TOKEN") or "").strip():
            load_dotenv(dotenv_path=src_env, override=True)
    if root_env.exists():
        load_dotenv(dotenv_path=root_env, override=False)


_load_env()


def _rank_within_top_n(rank: str, top_n: int) -> bool:
    if not top_n or top_n <= 0:
        return True
    if not rank:
        return True

    s = str(rank).strip()
    if not s:
        return True

    if s.isdigit():
        try:
            return int(s) <= top_n
        except Exception:
            return True

    m = re.match(r"^top\s*(\d+)$", s, flags=re.I)
    if m:
        return int(m.group(1)) <= top_n

    m = re.match(r"^next\s*(\d+)$", s, flags=re.I)
    if m:
        k = int(m.group(1))
        upper = 5 + k
        return upper <= top_n

    return True


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return default
    try:
        return float(s)
    except Exception:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def read_holdings_csv() -> dict[str, dict[str, Any]]:
    """Read holdings.csv and return a dict keyed by symbol with holdings data."""
    root = Path(__file__).resolve().parents[1]
    holdings_path = root / "data" / "holdings.csv"
    
    holdings_map: dict[str, dict[str, Any]] = {}
    
    if not holdings_path.exists():
        return holdings_map
    
    try:
        with holdings_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Handle both "Instrument" and "Symbol" column names
                symbol = (row.get("Instrument") or row.get("Symbol") or "").strip().upper()
                if not symbol:
                    continue
                
                qty = _safe_int(row.get("Qty.") or row.get("Qty") or row.get("Quantity"), 0)
                avg_cost = _safe_float(row.get("Avg. cost") or row.get("Avg_Cost") or row.get("AvgCost"), 0.0)
                ltp = _safe_float(row.get("LTP") or row.get("Price"), 0.0)
                invested = _safe_float(row.get("Invested") or row.get("Investment"), 0.0)
                cur_val = _safe_float(row.get("Cur. val") or row.get("Current_Value"), 0.0)
                pnl = _safe_float(row.get("P&L") or row.get("PnL"), 0.0)
                pnl_pct = _safe_float(row.get("Net chg.") or row.get("Net_Chg") or row.get("PnL_Pct"), 0.0)
                day_chg = _safe_float(row.get("Day chg.") or row.get("Day_Chg"), 0.0)
                
                holdings_map[symbol] = {
                    "holding_qty": qty,
                    "avg_cost": round(avg_cost, 2),
                    "invested": round(invested, 2),
                    "cur_val": round(cur_val, 2),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "day_chg": round(day_chg, 2),
                }
    except Exception:
        pass
    
    return holdings_map


def read_previous_tips_csv() -> dict[str, Any]:
    """Read previous tips_research_data.csv and return rows + symbols.
    
    This allows the tips agent to preserve previous analysis and rationale
    while updating prices and technical indicators.
    """
    root = Path(__file__).resolve().parents[1]
    tips_path = root / "data" / "tips_research_data.csv"
    
    if not tips_path.exists():
        return {"status": "not_found", "rows": [], "symbols": []}
    
    rows: list[dict[str, Any]] = []
    symbols: list[str] = []
    
    try:
        with tips_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                
                # Extract the original rationale (before technical sections)
                rationale = row.get("Rationale") or ""
                # Try to extract just the fundamental analysis part
                if "【FUNDAMENTAL ANALYSIS】" in rationale:
                    # Extract between FUNDAMENTAL ANALYSIS and next section
                    start = rationale.find("【FUNDAMENTAL ANALYSIS】") + len("【FUNDAMENTAL ANALYSIS】")
                    end = rationale.find("【", start)
                    if end > start:
                        original_rationale = rationale[start:end].strip()
                    else:
                        original_rationale = rationale[start:].strip()
                else:
                    original_rationale = rationale
                
                rows.append({
                    "Symbol": symbol,
                    "Quantity": _safe_int(row.get("Quantity"), 0),
                    "Price": _safe_float(row.get("Price"), 0.0),
                    "Transaction": row.get("Transaction") or "BUY",
                    "Variety": row.get("Variety") or "regular",
                    "Product": row.get("Product") or "CNC",
                    "Order_Type": row.get("Order_Type") or "LIMIT",
                    "Rank": row.get("Rank") or "",
                    "Allocation": _safe_float(row.get("Allocation"), 0.0),
                    "TargetValue": _safe_float(row.get("TargetValue"), 0.0),
                    "Rationale": original_rationale,  # Preserve original rationale
                })
                symbols.append(symbol)
        
        # de-dupe symbols, preserve order
        seen = set()
        uniq = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        
        return {"status": "success", "path": str(tips_path), "rows": rows, "symbols": uniq, "count": len(uniq)}
    except Exception as e:
        return {"status": "error", "message": str(e), "rows": [], "symbols": []}


def _build_detailed_rationale(
    *,
    symbol: str,
    original_rationale: str,
    price: float,
    dma50: float,
    dma200: float,
    rsi14: float,
    dma_trend: str,
    momentum_score: int,
    rank: str,
    recommendation: str,
    holding_qty: int = 0,
    avg_cost: float = 0.0,
    pnl: float = 0.0,
    pnl_pct: float = 0.0,
) -> str:
    """Build a comprehensive rationale combining fundamental and technical analysis.
    
    This detailed rationale provides the advisor agent with sufficient context
    to make informed recommendations.
    """
    parts: list[str] = []
    
    # === SECTION 1: FUNDAMENTAL ANALYSIS ===
    parts.append("【FUNDAMENTAL ANALYSIS】")
    if original_rationale and original_rationale.strip():
        parts.append(original_rationale.strip())
    else:
        parts.append(f"No detailed fundamental data available for {symbol}.")
    
    # === SECTION 2: CURRENT HOLDINGS ===
    parts.append("")
    parts.append("【CURRENT HOLDINGS】")
    if holding_qty > 0:
        holdings_lines: list[str] = []
        holdings_lines.append(f"Holding Qty: {holding_qty} shares")
        holdings_lines.append(f"Avg Cost: ₹{avg_cost:.2f}")
        holdings_lines.append(f"Current Price: ₹{price:.2f}")
        holdings_lines.append(f"P&L: ₹{pnl:+,.2f} ({pnl_pct:+.2f}%)")
        
        # Position assessment
        if pnl_pct >= 20:
            holdings_lines.append("→ SIGNIFICANT PROFIT: Consider partial profit booking")
        elif pnl_pct >= 10:
            holdings_lines.append("→ GOOD PROFIT: Hold with trailing stop-loss")
        elif pnl_pct >= 0:
            holdings_lines.append("→ MARGINAL PROFIT: Monitor closely")
        elif pnl_pct >= -10:
            holdings_lines.append("→ SMALL LOSS: Evaluate averaging down if fundamentals strong")
        elif pnl_pct >= -20:
            holdings_lines.append("→ MODERATE LOSS: Review thesis, avoid averaging without conviction")
        else:
            holdings_lines.append("→ DEEP LOSS: Consider exit if fundamentals deteriorated")
        
        parts.append(" | ".join(holdings_lines))
    else:
        parts.append("No existing position - Fresh entry opportunity")
    
    # === SECTION 3: TECHNICAL ANALYSIS ===
    parts.append("")
    parts.append("【TECHNICAL ANALYSIS】")
    
    # Price vs Moving Averages
    tech_lines: list[str] = []
    
    # Current Price Context
    tech_lines.append(f"Current Price: ₹{price:.2f}")
    
    # 50 DMA Analysis
    if dma50 > 0:
        pct_from_50dma = ((price - dma50) / dma50) * 100
        direction_50 = "above" if price > dma50 else "below"
        tech_lines.append(f"50-Day Moving Average: ₹{dma50:.2f} (Price is {abs(pct_from_50dma):.1f}% {direction_50} 50DMA)")
        if price > dma50:
            tech_lines.append("  → Short-term trend: BULLISH (trading above 50DMA)")
        else:
            tech_lines.append("  → Short-term trend: BEARISH (trading below 50DMA)")
    
    # 200 DMA Analysis
    if dma200 > 0:
        pct_from_200dma = ((price - dma200) / dma200) * 100
        direction_200 = "above" if price > dma200 else "below"
        tech_lines.append(f"200-Day Moving Average: ₹{dma200:.2f} (Price is {abs(pct_from_200dma):.1f}% {direction_200} 200DMA)")
        if price > dma200:
            tech_lines.append("  → Long-term trend: BULLISH (trading above 200DMA)")
        else:
            tech_lines.append("  → Long-term trend: BEARISH (trading below 200DMA)")
    
    # Golden Cross / Death Cross
    if dma50 > 0 and dma200 > 0:
        if dma_trend == "BULLISH":
            tech_lines.append("DMA Crossover: GOLDEN CROSS (50DMA > 200DMA) - Bullish signal indicating potential uptrend")
        else:
            tech_lines.append("DMA Crossover: DEATH CROSS (50DMA < 200DMA) - Bearish signal indicating potential downtrend")
    
    # RSI Analysis
    tech_lines.append(f"RSI(14): {rsi14:.1f}")
    if rsi14 >= 70:
        tech_lines.append("  → RSI Signal: OVERBOUGHT (RSI >= 70) - Stock may be overvalued, potential pullback risk")
    elif rsi14 <= 30:
        tech_lines.append("  → RSI Signal: OVERSOLD (RSI <= 30) - Stock may be undervalued, potential bounce opportunity")
    elif rsi14 >= 50:
        tech_lines.append("  → RSI Signal: BULLISH MOMENTUM (RSI 50-70) - Moderate buying pressure")
    else:
        tech_lines.append("  → RSI Signal: BEARISH MOMENTUM (RSI 30-50) - Moderate selling pressure")
    
    parts.append(" | ".join(tech_lines))
    
    # === SECTION 3: MOMENTUM SUMMARY ===
    parts.append("")
    parts.append("【MOMENTUM SUMMARY】")
    
    momentum_desc = []
    if momentum_score >= 3:
        momentum_desc.append(f"Overall Momentum Score: {momentum_score}/4 (STRONG BULLISH)")
        momentum_desc.append("Multiple bullish signals aligned - price above both DMAs with bullish crossover and positive RSI momentum")
    elif momentum_score >= 1:
        momentum_desc.append(f"Overall Momentum Score: {momentum_score}/4 (MODERATE BULLISH)")
        momentum_desc.append("Some bullish signals present but not fully aligned")
    elif momentum_score >= 0:
        momentum_desc.append(f"Overall Momentum Score: {momentum_score}/4 (NEUTRAL)")
        momentum_desc.append("Mixed signals - no clear directional bias in technicals")
    else:
        momentum_desc.append(f"Overall Momentum Score: {momentum_score}/4 (BEARISH)")
        momentum_desc.append("Technical indicators suggest downward pressure - price below key averages with oversold/overbought conditions")
    
    parts.append(" | ".join(momentum_desc))
    
    # === SECTION 4: RANK & POSITION CONTEXT ===
    parts.append("")
    parts.append("【PORTFOLIO CONTEXT】")
    rank_context = f"Research Rank: {rank}" if rank else "Research Rank: Not specified"
    parts.append(f"{rank_context} | Initial Recommendation: {recommendation}")
    
    # === SECTION 5: ADVISOR GUIDANCE ===
    parts.append("")
    parts.append("【ADVISOR GUIDANCE】")
    
    guidance_lines: list[str] = []
    
    # Key factors to consider
    if rsi14 <= 30 and dma_trend == "BEARISH":
        guidance_lines.append("CAUTION: Stock is oversold but in bearish trend - may indicate falling knife scenario. Wait for trend reversal confirmation.")
    elif rsi14 >= 70 and dma_trend == "BULLISH":
        guidance_lines.append("CAUTION: Stock is overbought despite bullish trend - consider partial profit booking or tighter stop-loss.")
    elif dma_trend == "BULLISH" and momentum_score >= 2:
        guidance_lines.append("FAVORABLE: Technical setup is bullish with multiple confirming signals. Good entry opportunity on dips.")
    elif dma_trend == "BEARISH" and momentum_score <= 0:
        guidance_lines.append("UNFAVORABLE: Technical setup is bearish. Consider reducing exposure or waiting for trend reversal.")
    else:
        guidance_lines.append("NEUTRAL: Mixed technical signals. Position sizing should be conservative.")
    
    # Price level guidance
    if dma50 > 0 and dma200 > 0:
        key_support = min(dma50, dma200)
        key_resistance = max(dma50, dma200)
        guidance_lines.append(f"Key Support: ₹{key_support:.2f} | Key Resistance: ₹{key_resistance:.2f}")
    
    parts.append(" | ".join(guidance_lines))
    
    # Combine all parts
    return " ".join(parts)


def _extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = re.findall(r"https?://[^\s\)\]\}<>\"']+", text, flags=re.I)
    out: list[str] = []
    for u in urls:
        u = u.strip().rstrip(".,;:")
        if u and u not in out:
            out.append(u)
    return out


def _split_source_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        parts = [str(x) for x in value]
    else:
        parts = re.split(r"[\s,;]+", str(value).strip())

    urls: list[str] = []
    for p in parts:
        urls.extend(_extract_urls(p))
    # de-dupe
    seen = set()
    uniq: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def generate_todays_reco_csvs(
    *,
    symbols: list[str],
    exchange: str = "NSE",
    output_buy: str = "data/buy_research_todays_reco.csv",
    output_sell: str = "data/sell_research_todays_reco.csv",
) -> dict[str, Any]:
    """Create/update today's 1-line BUY and SELL recommendation CSVs.

    Logic:
    - BUY: symbol with the highest % change vs previous close
    - SELL: symbol with the lowest % change vs previous close

    Data source:
    - Zerodha Kite `ohlc()` response (last_price + ohlc.close)
    """
    # Reload env in case src/.env was updated after module import (e.g., Streamlit connect)
    _load_env()

    repo_root = Path(__file__).resolve().parents[1]

    def _write_error_csvs(message: str) -> dict[str, Any]:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        buy_path = (repo_root / output_buy).resolve()
        sell_path = (repo_root / output_sell).resolve()
        buy_path.parent.mkdir(parents=True, exist_ok=True)
        sell_path.parent.mkdir(parents=True, exist_ok=True)
        header = ["GeneratedAt", "Symbol", "Transaction", "Price", "ChangePct", "Exchange", "Reason"]

        with buy_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerow(
                {
                    "GeneratedAt": ts,
                    "Symbol": "",
                    "Transaction": "BUY",
                    "Price": "",
                    "ChangePct": "",
                    "Exchange": exchange,
                    "Reason": f"ERROR: {message}",
                }
            )

        with sell_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerow(
                {
                    "GeneratedAt": ts,
                    "Symbol": "",
                    "Transaction": "SELL",
                    "Price": "",
                    "ChangePct": "",
                    "Exchange": exchange,
                    "Reason": f"ERROR: {message}",
                }
            )

        return {
            "status": "error",
            "message": message,
            "buy_path": str(buy_path),
            "sell_path": str(sell_path),
        }

    api_key = os.getenv("API_KEY", "").strip()
    access_token = os.getenv("ACCESS_TOKEN", "").strip()
    if not api_key or not access_token:
        return _write_error_csvs("Missing API_KEY/ACCESS_TOKEN for computing top gainer/loser")

    try:
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        uniq_symbols: list[str] = []
        seen = set()
        for s in symbols or []:
            s = str(s).strip().upper()
            if s and s not in seen:
                seen.add(s)
                uniq_symbols.append(s)

        if not uniq_symbols:
            return _write_error_csvs("No symbols provided")

        instruments = [f"{exchange}:{s}" for s in uniq_symbols]
        data = kite.ohlc(instruments)

        changes: list[dict[str, Any]] = []
        for s in uniq_symbols:
            key = f"{exchange}:{s}"
            quote = data.get(key)
            if not isinstance(quote, dict):
                continue
            last_price = _safe_float(quote.get("last_price"), 0.0)
            close = _safe_float((quote.get("ohlc") or {}).get("close"), 0.0)
            change_pct: Optional[float] = None
            if close > 0 and last_price > 0:
                change_pct = ((last_price - close) / close) * 100.0

            if last_price <= 0 or change_pct is None:
                continue

            changes.append(
                {
                    "symbol": s,
                    "exchange": exchange,
                    "last_price": last_price,
                    "close": close,
                    "change_pct": float(change_pct),
                }
            )

        if not changes:
            return _write_error_csvs("No quote data to compute gainers/losers")

        top_gainer = max(changes, key=lambda x: x.get("change_pct", float("-inf")))
        top_loser = min(changes, key=lambda x: x.get("change_pct", float("inf")))

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        buy_path = (repo_root / output_buy).resolve()
        sell_path = (repo_root / output_sell).resolve()
        buy_path.parent.mkdir(parents=True, exist_ok=True)
        sell_path.parent.mkdir(parents=True, exist_ok=True)

        buy_header = ["GeneratedAt", "Symbol", "Transaction", "Price", "ChangePct", "Exchange", "Reason"]
        sell_header = ["GeneratedAt", "Symbol", "Transaction", "Price", "ChangePct", "Exchange", "Reason"]

        with buy_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=buy_header)
            w.writeheader()
            w.writerow(
                {
                    "GeneratedAt": ts,
                    "Symbol": top_gainer["symbol"],
                    "Transaction": "BUY",
                    "Price": round(float(top_gainer["last_price"]), 2),
                    "ChangePct": round(float(top_gainer["change_pct"]), 2),
                    "Exchange": exchange,
                    "Reason": "Top gainer vs previous close (fallback when sources missing)",
                }
            )

        with sell_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=sell_header)
            w.writeheader()
            w.writerow(
                {
                    "GeneratedAt": ts,
                    "Symbol": top_loser["symbol"],
                    "Transaction": "SELL",
                    "Price": round(float(top_loser["last_price"]), 2),
                    "ChangePct": round(float(top_loser["change_pct"]), 2),
                    "Exchange": exchange,
                    "Reason": "Top loser vs previous close (fallback when sources missing)",
                }
            )

        return {
            "status": "success",
            "buy_path": str(buy_path),
            "sell_path": str(sell_path),
            "top_gainer": top_gainer,
            "top_loser": top_loser,
            "universe_count": len(uniq_symbols),
        }
    except Exception as e:
        return _write_error_csvs(str(e))


@dataclass
class TipsRunResult:
    status: str
    message: str
    input_path: str
    output_path: str
    symbols: list[str]
    daily_budget: float
    total_allocation: float


def read_research_data_csv(top_n_rank: Optional[int] = None) -> dict[str, Any]:
    """Tool: read `data/research_data.csv` and return rows + symbols."""
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "data" / "research_data.csv"

    if not csv_path.exists():
        return {"status": "error", "message": f"File not found: {csv_path}", "path": str(csv_path), "rows": [], "symbols": []}

    rows: list[dict[str, Any]] = []
    symbols: list[str] = []

    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
                if not symbol:
                    continue

                if top_n_rank is not None:
                    rank = (row.get("Rank") or row.get("rank") or "").strip()
                    if not _rank_within_top_n(rank, int(top_n_rank)):
                        continue

                rows.append(row)
                symbols.append(symbol)

        # de-dupe, preserve order
        seen = set()
        uniq = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                uniq.append(s)

        return {"status": "success", "path": str(csv_path), "rows": rows, "symbols": uniq, "count": len(uniq)}
    except Exception as e:
        return {"status": "error", "message": str(e), "path": str(csv_path), "rows": [], "symbols": []}


def fetch_live_prices(symbols: list[str], exchange: str = "NSE") -> dict[str, Any]:
    """Tool: fetch live LTP for symbols.

    Uses Zerodha Kite (kiteconnect) if API_KEY and ACCESS_TOKEN are available.
    Falls back to empty map on failure.
    """
    # Reload env in case src/.env was updated after module import
    _load_env()

    api_key = os.getenv("API_KEY", "").strip()
    access_token = os.getenv("ACCESS_TOKEN", "").strip()

    if not api_key or not access_token:
        return {"status": "error", "message": "Missing API_KEY/ACCESS_TOKEN for Kite LTP", "ltp": {}}

    try:
        from kiteconnect import KiteConnect

        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        instruments = [f"{exchange}:{s}" for s in symbols]
        data = kite.ltp(instruments)

        # Build tick size map once so we can round prices to valid ticks.
        tick_map: dict[str, float] = {}
        try:
            instruments = kite.instruments(exchange)
            for inst in instruments:
                ts = (inst.get('tradingsymbol') or '').strip().upper()
                tick = inst.get('tick_size', None)
                if ts and tick is not None:
                    tick_map[ts] = float(tick)
        except Exception:
            tick_map = {}

        def round_to_tick(price: float, tick: float) -> float:
            if tick <= 0:
                return price
            return round(round(price / tick) * tick, 10)

        ltp_map: dict[str, float] = {}
        for s in symbols:
            key = f"{exchange}:{s}"
            if key in data and isinstance(data[key], dict):
                p = float(data[key].get("last_price", 0.0) or 0.0)
                tick = float(tick_map.get(s, 0.0) or 0.0)
                ltp_map[s] = round_to_tick(p, tick) if tick else p

        return {"status": "success", "ltp": ltp_map, "count": len(ltp_map)}
    except Exception as e:
        return {"status": "error", "message": str(e), "ltp": {}}


def fetch_technical_indicators(symbols: list[str], exchange: str = "NSE") -> dict[str, Any]:
    """Tool: fetch technical indicators (50 DMA, 200 DMA, RSI) for symbols.
    
    Uses Zerodha Kite historical data API.
    Returns dict with symbol -> {dma50, dma200, rsi14, above_dma50, above_dma200, dma_trend}
    """
    _load_env()
    
    api_key = os.getenv("API_KEY", "").strip()
    access_token = os.getenv("ACCESS_TOKEN", "").strip()
    
    if not api_key or not access_token:
        return {"status": "error", "message": "Missing API_KEY/ACCESS_TOKEN", "indicators": {}}
    
    try:
        from kiteconnect import KiteConnect
        from datetime import datetime, timedelta
        import time
        
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        
        # Get instrument tokens
        instruments = kite.instruments(exchange)
        token_map: dict[str, int] = {}
        for inst in instruments:
            ts = (inst.get('tradingsymbol') or '').strip().upper()
            token = inst.get('instrument_token')
            if ts and token:
                token_map[ts] = int(token)
        
        indicators: dict[str, dict[str, Any]] = {}
        
        to_date = datetime.now()
        from_date = to_date - timedelta(days=365)  # 1 year for 200 DMA
        
        for symbol in symbols:
            token = token_map.get(symbol)
            if not token:
                indicators[symbol] = {"error": "Token not found"}
                continue
            
            try:
                # Throttle to avoid rate limit (3 req/sec)
                time.sleep(0.35)
                
                # Fetch daily historical data
                hist = kite.historical_data(
                    instrument_token=token,
                    from_date=from_date,
                    to_date=to_date,
                    interval="day"
                )
                
                if not hist or len(hist) < 50:
                    indicators[symbol] = {"error": "Insufficient data"}
                    continue
                
                closes = [float(h.get("close", 0)) for h in hist]
                current_price = closes[-1] if closes else 0
                
                # Calculate 50 DMA
                dma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else 0
                
                # Calculate 200 DMA
                dma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else 0
                
                # Calculate RSI (14 period)
                rsi14 = 50.0  # default
                if len(closes) >= 15:
                    gains = []
                    losses = []
                    for i in range(-14, 0):
                        change = closes[i] - closes[i - 1]
                        if change > 0:
                            gains.append(change)
                            losses.append(0)
                        else:
                            gains.append(0)
                            losses.append(abs(change))
                    avg_gain = sum(gains) / 14
                    avg_loss = sum(losses) / 14
                    if avg_loss > 0:
                        rs = avg_gain / avg_loss
                        rsi14 = 100 - (100 / (1 + rs))
                    else:
                        rsi14 = 100.0
                
                # DMA signals
                above_dma50 = current_price > dma50 if dma50 > 0 else None
                above_dma200 = current_price > dma200 if dma200 > 0 else None
                
                # Trend (Golden Cross / Death Cross)
                if dma50 > 0 and dma200 > 0:
                    if dma50 > dma200:
                        dma_trend = "BULLISH"  # Golden cross
                    else:
                        dma_trend = "BEARISH"  # Death cross
                else:
                    dma_trend = "NEUTRAL"
                
                # Momentum score
                momentum_score = 0
                if above_dma50:
                    momentum_score += 1
                if above_dma200:
                    momentum_score += 1
                if dma_trend == "BULLISH":
                    momentum_score += 1
                if rsi14 > 50:
                    momentum_score += 1
                if rsi14 > 70:
                    momentum_score -= 1  # Overbought
                if rsi14 < 30:
                    momentum_score -= 1  # Oversold
                
                indicators[symbol] = {
                    "dma50": round(dma50, 2),
                    "dma200": round(dma200, 2),
                    "rsi14": round(rsi14, 2),
                    "above_dma50": above_dma50,
                    "above_dma200": above_dma200,
                    "dma_trend": dma_trend,
                    "momentum_score": momentum_score,
                }
                
            except Exception as e:
                indicators[symbol] = {"error": str(e)[:50]}
        
        return {"status": "success", "indicators": indicators, "count": len(indicators)}
    except Exception as e:
        return {"status": "error", "message": str(e), "indicators": {}}


def generate_tips_research_data_csv(
    *,
    top_n_rank: Optional[int] = None,
    daily_budget: Optional[float] = None,
    per_stock_budget: Optional[float] = None,
    max_qty_per_stock: Optional[int] = None,
    output_file: str = "data/tips_research_data.csv",
    include_all_holdings: bool = True,
    use_previous_tips: bool = True,
) -> dict[str, Any]:
    """Tool: create `tips_research_data.csv` using live prices + DAILY_BUDGET.

    Data Priority (starting with holdings):
    1. Current holdings from holdings.csv - always included first
    2. Previous tips_research_data.csv - preserve existing rationale/ranks
    3. research_data.csv - for new stocks not in above sources
    
    Allocation rule:
    - Holdings get priority allocation based on their rank
    - New buys allocated equally within remaining budget

    Price:
    - Uses live LTP if available, else uses CSV Price.
    """
    # Reload env in case src/.env was updated after module import
    _load_env()

    root = Path(__file__).resolve().parents[1]
    
    # === STEP 1: Load current holdings (highest priority) ===
    holdings_map = read_holdings_csv()
    
    # === STEP 2: Load previous tips OR research data ===
    rows: list[dict[str, Any]] = []
    symbols: list[str] = []
    source_used = "none"
    
    # Try previous tips first
    if use_previous_tips:
        prev_tips = read_previous_tips_csv()
        if prev_tips.get("status") == "success" and prev_tips.get("rows"):
            rows = prev_tips["rows"]
            symbols = prev_tips["symbols"]
            source_used = "previous_tips"
    
    # Fall back to research_data.csv if no previous tips
    if not rows:
        input_data = read_research_data_csv(top_n_rank=top_n_rank)
        if input_data.get("status") == "success":
            rows = input_data["rows"]
            symbols = input_data["symbols"]
            source_used = "research_data"
    
    # === STEP 3: Merge holdings into rows (holdings first priority) ===
    existing_symbols = set(s.upper() for s in symbols)
    holdings_added = 0
    
    if include_all_holdings and holdings_map:
        for h_symbol, h_data in holdings_map.items():
            if h_data.get("holding_qty", 0) > 0 and h_symbol not in existing_symbols:
                # Add holding stock with data from holdings
                rows.append({
                    "Symbol": h_symbol,
                    "Quantity": 0,  # Will be recalculated
                    "Price": 0,  # Will be fetched live
                    "Transaction": "BUY",
                    "Variety": "regular",
                    "Product": "CNC",
                    "Order_Type": "LIMIT",
                    "Rank": "HOLDING",  # Mark as holding-only stock
                    "Allocation": 0,  # Lower priority for new buys
                    "TargetValue": 0,
                    "Rationale": f"Existing holding: {h_data.get('holding_qty')} shares @ ₹{h_data.get('avg_cost', 0):.2f} avg cost. P&L: ₹{h_data.get('pnl', 0):,.2f} ({h_data.get('pnl_pct', 0):.2f}%)",
                })
                symbols.append(h_symbol)
                holdings_added += 1

    if not rows:
        return {"status": "error", "message": "No rows found after filtering", "symbols": []}

    if daily_budget is None:
        daily_budget = _safe_float(os.getenv("DAILY_BUDGET", "100000"), 100000.0)
    
    if per_stock_budget is None:
        per_stock_budget = _safe_float(os.getenv("PER_STOCK_DAILY_BUDGET", "10000"), 10000.0)
    
    if max_qty_per_stock is None:
        max_qty_per_stock = int(_safe_float(os.getenv("MAX_QTY_PER_STOCK", "500"), 500))

    prices = fetch_live_prices(symbols)
    ltp_map: dict[str, float] = prices.get("ltp", {}) if prices.get("status") == "success" else {}
    ltp_status = prices.get("status")
    ltp_error = prices.get("message") if prices.get("status") != "success" else ""

    # Fetch technical indicators (50 DMA, 200 DMA, RSI)
    tech_data = fetch_technical_indicators(symbols)
    tech_map: dict[str, dict[str, Any]] = tech_data.get("indicators", {}) if tech_data.get("status") == "success" else {}

    input_allocs = []
    for r in rows:
        input_allocs.append(_safe_float(r.get("Allocation") or r.get("allocation"), 0.0))
    total_input_alloc = sum(input_allocs)

    weights: list[float]
    if total_input_alloc > 0:
        weights = [a / total_input_alloc for a in input_allocs]
    else:
        weights = [1.0 / len(rows)] * len(rows)

    header = [
        "Symbol",
        "Quantity",
        "Price",
        "Holding_Qty",
        "Avg_Cost",
        "Holding_Value",
        "PnL",
        "PnL_Pct",
        "DMA50",
        "DMA200",
        "RSI14",
        "DMA_Trend",
        "Momentum_Score",
        "Transaction",
        "Variety",
        "Product",
        "Order_Type",
        "Rank",
        "Recommendation",
        "Allocation",
        "TargetValue",
        "Rationale",
    ]

    output_path = root / output_file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out_rows: list[dict[str, Any]] = []
    total_alloc = 0.0

    for r, w in zip(rows, weights):
        symbol = (r.get("Symbol") or r.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        live_price = float(ltp_map.get(symbol, 0.0) or 0.0)
        csv_price = _safe_float(r.get("Price") or r.get("price"), 0.0)
        price = live_price if live_price > 0 else csv_price

        # Get technical indicators for this symbol
        tech = tech_map.get(symbol, {})
        dma50 = tech.get("dma50", 0)
        dma200 = tech.get("dma200", 0)
        rsi14 = tech.get("rsi14", 50)
        dma_trend = tech.get("dma_trend", "N/A")
        momentum_score = tech.get("momentum_score", 0)

        # Get holdings data for this symbol
        holding = holdings_map.get(symbol, {})
        holding_qty = holding.get("holding_qty", 0)
        avg_cost = holding.get("avg_cost", 0.0)
        holding_value = round(holding_qty * price, 2) if holding_qty > 0 else 0.0
        pnl = holding.get("pnl", 0.0)
        pnl_pct = holding.get("pnl_pct", 0.0)

        # Calculate allocation (capped to per_stock_budget)
        alloc = float(daily_budget) * float(w)
        alloc = min(alloc, per_stock_budget)  # Cap to per-stock budget
        
        # Calculate quantity (capped to max_qty_per_stock)
        qty = int(alloc / price) if price > 0 else 0
        qty = min(qty, max_qty_per_stock)  # Cap to max qty
        
        target_value = float(qty) * float(price)

        total_alloc += min(alloc, target_value)  # Use actual allocated amount

        # Determine recommendation based on rank, technicals, and holdings
        rank_str = str(r.get("Rank") or "").lower()
        
        # Start with rank-based recommendation
        if any(x in rank_str for x in ["top5", "top 5"]):
            base_recommendation = "STRONG BUY"
        elif any(x in rank_str for x in ["next5", "next 5", "top10", "top 10"]):
            base_recommendation = "BUY"
        elif any(x in rank_str for x in ["top15", "top 15"]):
            base_recommendation = "BUY"
        elif any(x in rank_str for x in ["top25", "top 25", "top30", "top 30"]):
            base_recommendation = "ACCUMULATE"
        elif "holding" in rank_str:
            # For holding-only stocks (not in research), base recommendation on technicals
            if momentum_score >= 3:
                base_recommendation = "HOLD"  # Strong momentum, keep holding
            elif momentum_score >= 1:
                base_recommendation = "HOLD"
            elif momentum_score >= 0:
                base_recommendation = "REVIEW"  # Neutral, review position
            else:
                base_recommendation = "REDUCE"  # Weak momentum, consider reducing
        else:
            base_recommendation = "REVIEW"
        
        # Adjust based on technicals
        recommendation = base_recommendation
        if dma_trend == "BEARISH" and momentum_score < 0:
            # Downgrade if bearish technicals
            if recommendation == "STRONG BUY":
                recommendation = "BUY"
            elif recommendation == "BUY":
                recommendation = "ACCUMULATE"
            elif recommendation == "ACCUMULATE":
                recommendation = "HOLD"
            elif recommendation == "HOLD":
                recommendation = "REDUCE"
        elif dma_trend == "BULLISH" and momentum_score >= 2:
            # Upgrade if strong bullish technicals
            if recommendation == "REDUCE":
                recommendation = "HOLD"
            elif recommendation == "HOLD":
                recommendation = "ACCUMULATE"
            elif recommendation == "ACCUMULATE":
                recommendation = "BUY"
            elif recommendation == "BUY":
                recommendation = "STRONG BUY"
        
        # For holding stocks with significant losses, suggest review
        if holding_qty > 0 and pnl_pct <= -15:
            if recommendation not in ["SELL", "REDUCE"]:
                recommendation = "REVIEW"  # Deep loss needs review

        out = {
            "Symbol": symbol,
            "Quantity": qty,
            "Price": round(price, 2),
            "Holding_Qty": holding_qty,
            "Avg_Cost": avg_cost,
            "Holding_Value": holding_value,
            "PnL": pnl,
            "PnL_Pct": pnl_pct,
            "DMA50": dma50,
            "DMA200": dma200,
            "RSI14": rsi14,
            "DMA_Trend": dma_trend,
            "Momentum_Score": momentum_score,
            "Transaction": (r.get("Transaction") or "BUY"),
            "Variety": (r.get("Variety") or "regular"),
            "Product": (r.get("Product") or "CNC"),
            "Order_Type": (r.get("Order_Type") or "LIMIT"),
            "Rank": (r.get("Rank") or ""),
            "Recommendation": recommendation,
            "Allocation": int(alloc),
            "TargetValue": int(target_value),
            "Rationale": _build_detailed_rationale(
                symbol=symbol,
                original_rationale=r.get("Rationale") or "",
                price=price,
                dma50=dma50,
                dma200=dma200,
                rsi14=rsi14,
                dma_trend=dma_trend,
                momentum_score=momentum_score,
                rank=r.get("Rank") or "",
                recommendation=recommendation,
                holding_qty=holding_qty,
                avg_cost=avg_cost,
                pnl=pnl,
                pnl_pct=pnl_pct,
            ),
        }
        out_rows.append(out)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(out_rows)

    return {
        "status": "success",
        "source": source_used,
        "output": str(output_path),
        "symbols": symbols,
        "count": len(out_rows),
        "from_previous_tips": source_used == "previous_tips",
        "holdings_added": holdings_added,
        "daily_budget": float(daily_budget),
        "per_stock_budget": float(per_stock_budget),
        "max_qty_per_stock": int(max_qty_per_stock),
        "total_allocation": int(total_alloc),
        "price_source": "kite_ltp" if ltp_map else "csv_price",
        "ltp_status": ltp_status,
        "ltp_error": ltp_error,
    }


def get_allowed_research_sources() -> dict[str, Any]:
    """Tool: load the curated allowlist of research sources.

    Extracts URLs/domains from `src/research_sources.py`.
    """
    repo_root = Path(__file__).resolve().parents[1]
    src_file = repo_root / "src" / "research_sources.py"
    if not src_file.exists():
        return {"status": "error", "message": f"Missing file: {src_file}", "urls": [], "domains": []}

    text = src_file.read_text(encoding="utf-8")
    urls = re.findall(r"https?://[^\"'\s\]]+", text)

    norm_urls: list[str] = []
    for u in urls:
        u = u.strip()
        if not u:
            continue
        if not u.endswith("/"):
            u += "/"
        if u not in norm_urls:
            norm_urls.append(u)

    domains: list[str] = []
    for u in norm_urls:
        m = re.match(r"^https?://([^/]+)/", u)
        if m:
            d = m.group(1).lower()
            if d not in domains:
                domains.append(d)

    return {"status": "success", "urls": norm_urls, "domains": domains, "count": len(domains)}


def build_site_restricted_query(query: str, max_sites: int = 6) -> dict[str, Any]:
    """Tool: build a Google query restricted to curated sources via `site:`."""
    sources = get_allowed_research_sources()
    if sources.get("status") != "success":
        return {"status": "error", "message": sources.get("message", "Unable to load sources"), "query": query}

    domains: list[str] = sources.get("domains", [])
    if not domains:
        return {"status": "error", "message": "No allowlisted domains found", "query": query}

    max_sites = max(1, int(max_sites))
    picked = domains[:max_sites]
    sites_clause = " OR ".join([f"site:{d}" for d in picked])
    return {"status": "success", "query": f"{query} ({sites_clause})", "domains": picked}


def write_tips_research_report_md(
    *,
    top_n_rank: Optional[int] = None,
    daily_budget: Optional[float] = None,
    tips_csv_path: str = "data/tips_research_data.csv",
    output_md: str = "data/tips_research_report.md",
) -> dict[str, Any]:
    """Tool: write a tips research report markdown under `data/`.

    Important:
    - This implementation intentionally does NOT do live web search.
      The GenAI API currently rejects mixing the `google_search` tool with
      normal function tools in a single agent run.
    - The report is built from the generated tips CSV + the existing
      rationales/fields in `data/research_data.csv`.
    """
    # Reload env in case src/.env was updated after module import
    _load_env()

    repo_root = Path(__file__).resolve().parents[1]

    if daily_budget is None:
        daily_budget = _safe_float(os.getenv("DAILY_BUDGET", "100000"), 100000.0)

    tips_path = repo_root / tips_csv_path
    if not tips_path.exists():
        return {"status": "error", "message": f"tips CSV not found: {tips_path}"}

    tips_rows: list[dict[str, Any]] = []
    with tips_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tips_rows.append(row)

    if not tips_rows:
        return {"status": "error", "message": "tips CSV is empty", "path": str(tips_path)}

    rd = read_research_data_csv(top_n_rank=top_n_rank)
    if rd.get("status") != "success":
        return {"status": "error", "message": "Failed to read research_data.csv", "details": rd}

    research_rows: list[dict[str, Any]] = rd.get("rows", [])
    research_by_symbol: dict[str, dict[str, Any]] = {}
    for r in research_rows:
        s = (r.get("Symbol") or r.get("symbol") or "").strip().upper()
        if s and s not in research_by_symbol:
            research_by_symbol[s] = r

    total_alloc = 0.0
    total_target = 0.0
    for r in tips_rows:
        total_alloc += _safe_float(r.get("Allocation"), 0.0)
        total_target += _safe_float(r.get("TargetValue"), 0.0)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filt = f"Top{top_n_rank}" if top_n_rank else "All"

    allow = get_allowed_research_sources()
    allow_domains: list[str] = []
    if allow.get("status") == "success":
        allow_domains = list(allow.get("domains", []) or [])

    md: list[str] = []
    md.append("# Tips Research Report\n\n")
    md.append(f"Generated at: **{ts}**\n\n")
    md.append(f"Universe filter: **{filt}**\n\n")
    md.append(f"Daily budget (input): **₹{float(daily_budget):,.2f}**\n\n")
    md.append(f"Tips CSV: `{tips_path}`\n\n")

    md.append("## What This Report Captures\n\n")
    md.append(
        "For each ticker in the generated tips CSV, this report captures:\n\n"
        "- **Position plan**: quantity, price used, allocation, target value (qty × price)\n"
        "- **Rank / bucket**: the `Rank` field used for Top-N filtering\n"
        "- **Investment thesis**: the `Rationale` carried over from `data/research_data.csv`\n"
        "- **Sources / traceability**: URLs if provided in `data/research_data.csv` (recommended), plus the curated allowlist domains\n\n"
        "Note: This tips agent does not fetch new web content during execution (tooling constraint). "
        "If you want fresh grounded web citations, run `deep_search_agent` separately.\n\n"
    )
    md.append("## Summary\n\n")
    md.append(f"- Rows: {len(tips_rows)}\n")
    md.append(f"- Sum Allocation: ₹{total_alloc:,.2f}\n")
    md.append(f"- Sum TargetValue: ₹{total_target:,.2f}\n\n")

    md.append("## Tips Table\n\n")
    md.append("| Symbol | Rank | Qty | Price | Allocation | TargetValue |\n")
    md.append("|---|---:|---:|---:|---:|---:|\n")
    for r in tips_rows:
        sym = (r.get("Symbol") or "").strip().upper()
        qty = _safe_int(r.get("Quantity"), 0)
        price = _safe_float(r.get("Price"), 0.0)
        alloc = _safe_float(r.get("Allocation"), 0.0)
        tv = _safe_float(r.get("TargetValue"), 0.0)
        rank = (r.get("Rank") or "").strip()
        md.append(f"| {sym} | {rank} | {qty} | {price:.2f} | {alloc:.2f} | {tv:.2f} |\n")
    md.append("\n")

    md.append("## Per-Symbol Notes\n\n")

    # Decide whether we need the momentum fallback.
    missing_sources_symbols: list[str] = []
    for r in tips_rows:
        sym = (r.get("Symbol") or "").strip().upper()
        src = research_by_symbol.get(sym, {})
        source_field = (
            src.get("Sources")
            or src.get("Source")
            or src.get("Source_URL")
            or src.get("Source_URLs")
            or src.get("sources")
            or src.get("source")
        )
        urls = _split_source_field(source_field)
        if not urls:
            rationale = (src.get("Rationale") or src.get("rationale") or "").strip()
            urls = _extract_urls(rationale)
        if not urls:
            missing_sources_symbols.append(sym)

    reco: dict[str, Any] = {}
    if missing_sources_symbols:
        # Use the full tips universe as the momentum universe.
        tips_symbols = [(r.get("Symbol") or "").strip().upper() for r in tips_rows if (r.get("Symbol") or "").strip()]
        reco = generate_todays_reco_csvs(symbols=tips_symbols)

    for r in tips_rows:
        sym = (r.get("Symbol") or "").strip().upper()
        md.append(f"### {sym}\n\n")
        md.append("**Key Facts**\n\n")
        md.append(f"- Rank: **{(r.get('Rank') or '').strip() or 'N/A'}**\n")
        md.append(f"- Quantity: **{_safe_int(r.get('Quantity'), 0)}**\n")
        md.append(f"- Price used: **₹{_safe_float(r.get('Price'), 0.0):,.2f}**\n")
        md.append(f"- Allocation: **₹{_safe_float(r.get('Allocation'), 0.0):,.2f}**\n")
        md.append(f"- Target value (qty×price): **₹{_safe_float(r.get('TargetValue'), 0.0):,.2f}**\n")

        src = research_by_symbol.get(sym, {})
        rationale = (src.get("Rationale") or src.get("rationale") or "").strip()

        md.append("\n**Important Information (Thesis)**\n\n")
        if rationale:
            md.append(rationale + "\n\n")
        else:
            md.append("(No rationale found for this symbol in research_data.csv)\n\n")

        md.append("**Sources (recommended: add URLs in research_data.csv)**\n\n")
        # Optional columns users may add without breaking existing flows.
        source_field = (
            src.get("Sources")
            or src.get("Source")
            or src.get("Source_URL")
            or src.get("Source_URLs")
            or src.get("sources")
            or src.get("source")
        )
        urls = _split_source_field(source_field)
        if not urls and rationale:
            urls = _extract_urls(rationale)

        if urls:
            for u in urls[:12]:
                md.append(f"- {u}\n")
            if len(urls) > 12:
                md.append(f"- (+{len(urls) - 12} more)\n")
            md.append("\n")
        else:
            md.append("- (No source URLs found in `research_data.csv` for this symbol.)\n")
            if reco.get("status") == "success":
                md.append("- Fallback momentum reco CSVs generated:\n")
                md.append(f"  - BUY: `{Path(reco['buy_path']).name}` (top gainer: {reco['top_gainer']['symbol']}, {reco['top_gainer']['change_pct']:.2f}%)\n")
                md.append(f"  - SELL: `{Path(reco['sell_path']).name}` (top loser: {reco['top_loser']['symbol']}, {reco['top_loser']['change_pct']:.2f}%)\n\n")
            else:
                md.append(
                    "- Tip: Add a `Sources` column (URLs) in `research_data.csv` OR ensure Kite API credentials are set to compute today's top gainer/loser fallback.\n\n"
                )

    md.append("## Source Policy\n\n")
    md.append(
        "This report is generated from the existing `data/research_data.csv` rationales and the computed tips CSV. "
        "It does not fetch new web sources during the run (to keep the agent compatible with the current GenAI tool constraints).\n\n"
    )
    if allow_domains:
        md.append("Curated research domains (allowlist):\n\n")
        md.append("- " + "\n- ".join(allow_domains[:50]) + "\n\n")
    else:
        md.append("Curated research domains (allowlist): (not available)\n\n")

    md.append("## Next Step (Optional)\n\n")
    md.append(
        "If you want a fresh grounded web research report with citations, run `adk run deep_search_agent` for the same symbol set "
        "and save the output into `data/` as needed.\n"
    )

    return write_markdown_file(output_md, "".join(md))


def write_markdown_file(path: str, content: str) -> dict[str, Any]:
    """Tool: write a markdown file under the repo's `data/` folder.

    Safety:
    - Only allows paths like `data/<name>.md`
    """
    repo_root = Path(__file__).resolve().parents[1]
    p = Path(path)
    if p.is_absolute() or ".." in p.parts:
        return {"status": "error", "message": "Only relative paths under data/ are allowed"}

    if not p.parts or p.parts[0] != "data" or not str(p).lower().endswith(".md"):
        return {"status": "error", "message": "Path must be under data/ and end with .md"}

    out = (repo_root / p).resolve()
    data_dir = (repo_root / "data").resolve()
    if data_dir not in out.parents:
        return {"status": "error", "message": "Invalid output path"}

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content or "", encoding="utf-8")
    return {"status": "success", "path": str(out), "bytes": len(content or "")}


def write_tips_generation_audit_md(
    *,
    top_n_rank: Optional[int] = None,
    daily_budget: Optional[float] = None,
    tips_csv_path: str = "data/tips_research_data.csv",
    output_md: str = "data/tips_research_generation.md",
    preview_rows: int = 25,
) -> dict[str, Any]:
    """Tool: write an audit/traceability markdown for the generated tips CSV.

    This is *not* chain-of-thought. It records inputs, parameters, and outputs.
    """
    # Reload env in case src/.env was updated after module import
    _load_env()

    repo_root = Path(__file__).resolve().parents[1]

    if daily_budget is None:
        daily_budget = _safe_float(os.getenv("DAILY_BUDGET", "100000"), 100000.0)

    in_path = repo_root / "data" / "research_data.csv"
    tips_path = repo_root / tips_csv_path

    if not tips_path.exists():
        return {"status": "error", "message": f"tips CSV not found: {tips_path}"}

    # Load tips rows for summary
    tips_rows: list[dict[str, Any]] = []
    with tips_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tips_rows.append(row)

    total_target_value = 0.0
    total_allocation = 0.0
    for r in tips_rows:
        total_allocation += _safe_float(r.get("Allocation"), 0.0)
        total_target_value += _safe_float(r.get("TargetValue"), 0.0)

    api_key_present = bool((os.getenv("API_KEY") or "").strip())
    access_token_present = bool((os.getenv("ACCESS_TOKEN") or "").strip())

    # Validate that Kite LTP is actually usable (token can expire even if present).
    kite_usable = False
    kite_note = ""
    if api_key_present and access_token_present and tips_rows:
        try:
            sample_symbol = (tips_rows[0].get("Symbol") or "").strip().upper()
            if sample_symbol:
                probe = fetch_live_prices([sample_symbol])
                if probe.get("status") == "success" and (probe.get("count") or 0) > 0:
                    kite_usable = True
                else:
                    kite_note = probe.get("message") or "Kite LTP not usable"
        except Exception as e:
            kite_note = str(e)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filt = f"Top{top_n_rank}" if top_n_rank else "All"
    md_lines = []
    md_lines.append(f"# Tips CSV Generation Audit\n")
    md_lines.append(f"Generated at: **{ts}**\n")
    md_lines.append(f"Filter: **{filt}**\n")
    md_lines.append(f"Daily budget: **₹{float(daily_budget):,.2f}**\n")
    md_lines.append(f"Input: `{in_path}`\n")
    md_lines.append(f"Output: `{tips_path}`\n")
    if kite_usable:
        md_lines.append("Live price source: **Kite LTP** (available)\n")
    else:
        extra = f" (reason: {kite_note})" if kite_note else ""
        md_lines.append(f"Live price source: **Kite LTP** (NOT available - fell back to CSV prices){extra}\n")
    md_lines.append(
        f"Kite creds: API_KEY={'yes' if api_key_present else 'no'}, ACCESS_TOKEN={'yes' if access_token_present else 'no'}\n"
    )
    md_lines.append("\n## Output Summary\n")
    md_lines.append(f"- Rows written: {len(tips_rows)}\n")
    md_lines.append(f"- Sum Allocation: ₹{total_allocation:,.2f}\n")
    md_lines.append(f"- Sum TargetValue (qty*price): ₹{total_target_value:,.2f}\n")
    md_lines.append("\n## Preview (first rows)\n")
    md_lines.append("```csv\n")
    # Reprint header + a few rows from file
    with tips_path.open("r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i == 0 or i <= int(preview_rows):
                md_lines.append(line.rstrip("\n") + "\n")
            else:
                break
    md_lines.append("```\n")

    return write_markdown_file(output_md, "".join(md_lines))


root_agent = Agent(
    name="tips_research_agent",
    model="gemini-2.5-flash",
    description="Generates tips_research_data.csv from research_data.csv using live prices and DAILY_BUDGET.",
    instruction=(
        "You generate a new CSV file `data/tips_research_data.csv` based on `data/research_data.csv`. "
        "You MUST only use symbols present in research_data.csv.\n\n"
        "When the user asks to generate/update the tips file:\n"
        "1) Call `read_research_data_csv` (optionally with top_n_rank like 15).\n"
        "2) Call `generate_tips_research_data_csv` using DAILY_BUDGET (or user-provided budget).\n"
        "3) Call `write_tips_generation_audit_md` to create `data/tips_research_generation.md`.\n"
        "4) Call `write_tips_research_report_md` to create `data/tips_research_report.md`.\n"
        "5) Reply with a short status message including paths to: tips CSV, generation audit MD, research report MD. "
        "Also include whether live prices were used by printing `price_source` from step (2). "
        "If `price_source` is `csv_price`, include `ltp_error` and tell the user the ACCESS_TOKEN likely needs refresh.\n\n"
        "Do not output the CSV or markdown contents in chat unless explicitly asked." 
    ),
    tools=[
        read_research_data_csv,
        fetch_live_prices,
        fetch_technical_indicators,
        generate_tips_research_data_csv,
        write_tips_generation_audit_md,
        get_allowed_research_sources,
        write_tips_research_report_md,
        write_markdown_file,
    ],
)
