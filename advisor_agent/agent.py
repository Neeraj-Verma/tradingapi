"""Advisor Agent - Analyzes stock rationale and provides recommendations

Goal:
- Read `data/tips_research_data.csv`
- Analyze each stock's Rationale in detail
- Update the Recommendation column with intelligent analysis
- Write back updated CSV

Run:
  adk run advisor_agent

Then prompt:
  Analyze all stocks and update recommendations based on rationale.

Recommendations:
- STRONG BUY: Excellent fundamentals, strong growth, positive momentum
- BUY: Good fundamentals, solid growth prospects
- ACCUMULATE: Decent stock, good to add on dips
- HOLD: Mixed signals, maintain position but don't add
- REDUCE: Weak outlook, consider partial exit
- SELL: Poor fundamentals, exit recommended
"""

from __future__ import annotations

import csv
import os
import re
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
        load_dotenv(dotenv_path=src_env, override=False)
    if root_env.exists():
        load_dotenv(dotenv_path=root_env, override=False)


_load_env()


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


def read_tips_csv() -> dict[str, Any]:
    """Tool: read `data/tips_research_data.csv` and return all rows."""
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "data" / "tips_research_data.csv"

    if not csv_path.exists():
        return {"status": "error", "message": f"File not found: {csv_path}", "rows": []}

    rows: list[dict[str, Any]] = []
    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return {"status": "success", "path": str(csv_path), "rows": rows, "count": len(rows)}
    except Exception as e:
        return {"status": "error", "message": str(e), "rows": []}


def analyze_single_stock(
    symbol: str,
    rationale: str,
    rank: str,
    price: float,
    quantity: int,
    dma50: float = 0,
    dma200: float = 0,
    rsi14: float = 50,
    dma_trend: str = "N/A",
    momentum_score: int = 0,
) -> dict[str, Any]:
    """Tool: Analyze a single stock and return recommendation.
    
    The agent should call this for each stock, providing:
    - symbol: Stock symbol
    - rationale: The detailed rationale/thesis from research
    - rank: The rank (Top5, Next5, Top15, etc.)
    - price: Current price
    - quantity: Planned quantity
    - dma50: 50-day moving average
    - dma200: 200-day moving average  
    - rsi14: 14-period RSI
    - dma_trend: BULLISH/BEARISH/NEUTRAL
    - momentum_score: Technical momentum score (-2 to +4)
    
    Returns analysis with recommended action.
    """
    analysis = {
        "symbol": symbol,
        "rank": rank,
        "price": price,
        "quantity": quantity,
        "dma50": dma50,
        "dma200": dma200,
        "rsi14": rsi14,
        "dma_trend": dma_trend,
        "momentum_score": momentum_score,
        "rationale_summary": rationale[:200] + "..." if len(rationale) > 200 else rationale,
    }
    
    # Extract key metrics from rationale
    rationale_lower = rationale.lower()
    
    # Positive signals from rationale
    positive_signals = []
    if re.search(r"pat\s*\+\d+", rationale_lower) or "profit" in rationale_lower and "+" in rationale:
        positive_signals.append("Profit growth")
    if re.search(r"rev(enue)?\s*\+\d+", rationale_lower):
        positive_signals.append("Revenue growth")
    if "strong" in rationale_lower:
        positive_signals.append("Strong fundamentals")
    if "growth" in rationale_lower:
        positive_signals.append("Growth story")
    if "beat" in rationale_lower or "upgrade" in rationale_lower:
        positive_signals.append("Beat/Upgrade")
    if "momentum" in rationale_lower:
        positive_signals.append("Positive momentum")
    if "dividend" in rationale_lower:
        positive_signals.append("Dividend play")
    if "leader" in rationale_lower or "franchise" in rationale_lower:
        positive_signals.append("Market leader")
    
    # Technical positive signals
    if dma_trend == "BULLISH":
        positive_signals.append("Bullish DMA (50>200)")
    if price > dma50 > 0:
        positive_signals.append("Above 50 DMA")
    if price > dma200 > 0:
        positive_signals.append("Above 200 DMA")
    if 50 < rsi14 < 70:
        positive_signals.append("RSI healthy (50-70)")
    if momentum_score >= 2:
        positive_signals.append(f"Strong momentum ({momentum_score})")
    
    # Negative signals from rationale
    negative_signals = []
    if re.search(r"pat\s*-\d+", rationale_lower) or ("profit" in rationale_lower and "-" in rationale):
        negative_signals.append("Profit decline")
    if re.search(r"rev(enue)?\s*-\d+", rationale_lower):
        negative_signals.append("Revenue decline")
    if "weak" in rationale_lower:
        negative_signals.append("Weak outlook")
    if "decline" in rationale_lower or "down" in rationale_lower:
        negative_signals.append("Declining metrics")
    if "risk" in rationale_lower or "volatile" in rationale_lower:
        negative_signals.append("High risk")
    if "pressure" in rationale_lower:
        negative_signals.append("Margin pressure")
    if "turnaround" in rationale_lower or "speculative" in rationale_lower:
        negative_signals.append("Speculative bet")
    if "bankrupt" in rationale_lower or "near-bankrupt" in rationale_lower:
        negative_signals.append("Bankruptcy risk")
    
    # Technical negative signals
    if dma_trend == "BEARISH":
        negative_signals.append("Bearish DMA (50<200)")
    if price < dma50 > 0:
        negative_signals.append("Below 50 DMA")
    if price < dma200 > 0:
        negative_signals.append("Below 200 DMA")
    if rsi14 > 70:
        negative_signals.append("RSI overbought (>70)")
    if rsi14 < 30:
        negative_signals.append("RSI oversold (<30)")
    if momentum_score <= -1:
        negative_signals.append(f"Weak momentum ({momentum_score})")
    
    analysis["positive_signals"] = positive_signals
    analysis["negative_signals"] = negative_signals
    analysis["positive_count"] = len(positive_signals)
    analysis["negative_count"] = len(negative_signals)
    
    # Score calculation (fundamental + technical)
    score = len(positive_signals) - len(negative_signals)
    
    # Rank bonus
    rank_lower = rank.lower()
    if "top5" in rank_lower or "top 5" in rank_lower:
        score += 2
    elif "next5" in rank_lower or "top10" in rank_lower:
        score += 1
    elif "top25" in rank_lower or "top30" in rank_lower:
        score -= 1
    
    # Technical bonus/penalty
    score += momentum_score  # Add technical momentum
    
    analysis["score"] = score
    
    # Determine recommendation
    if score >= 3:
        recommendation = "STRONG BUY"
        action = "Aggressively accumulate"
    elif score >= 1:
        recommendation = "BUY"
        action = "Add to portfolio"
    elif score == 0:
        recommendation = "ACCUMULATE"
        action = "Buy on dips"
    elif score >= -1:
        recommendation = "HOLD"
        action = "Maintain position"
    elif score >= -2:
        recommendation = "REDUCE"
        action = "Consider partial exit"
    else:
        recommendation = "SELL"
        action = "Exit position"
    
    analysis["recommendation"] = recommendation
    analysis["action"] = action
    
    return {"status": "success", "analysis": analysis}


def update_recommendations(updates: list[dict[str, str]]) -> dict[str, Any]:
    """Tool: Update recommendations in tips_research_data.csv
    
    Args:
        updates: List of {"symbol": "XXX", "recommendation": "BUY"} dicts
    """
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "data" / "tips_research_data.csv"

    if not csv_path.exists():
        return {"status": "error", "message": f"File not found: {csv_path}"}

    # Read existing rows
    rows: list[dict[str, Any]] = []
    fieldnames: list[str] = []
    try:
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                rows.append(row)
    except Exception as e:
        return {"status": "error", "message": f"Read error: {e}"}

    # Build update map
    update_map = {u["symbol"].upper(): u["recommendation"] for u in updates}
    
    # Update rows
    updated_count = 0
    for row in rows:
        symbol = (row.get("Symbol") or "").strip().upper()
        if symbol in update_map:
            row["Recommendation"] = update_map[symbol]
            updated_count += 1
    
    # Write back
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return {
            "status": "success",
            "path": str(csv_path),
            "updated_count": updated_count,
            "total_rows": len(rows),
        }
    except Exception as e:
        return {"status": "error", "message": f"Write error: {e}"}


def generate_advisor_report(
    analyses: list[dict[str, Any]],
    output_md: str = "data/advisor_report.md",
) -> dict[str, Any]:
    """Tool: Generate advisor report markdown with all analyses."""
    root = Path(__file__).resolve().parents[1]
    
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Count by recommendation
    reco_counts: dict[str, int] = {}
    for a in analyses:
        r = a.get("recommendation", "UNKNOWN")
        reco_counts[r] = reco_counts.get(r, 0) + 1
    
    md = []
    md.append("# Advisor Agent Report\n\n")
    md.append(f"Generated at: **{ts}**\n\n")
    md.append(f"Total stocks analyzed: **{len(analyses)}**\n\n")
    
    md.append("## Recommendation Summary\n\n")
    md.append("| Recommendation | Count |\n")
    md.append("|----------------|-------|\n")
    for r in ["STRONG BUY", "BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL"]:
        if r in reco_counts:
            md.append(f"| {r} | {reco_counts[r]} |\n")
    md.append("\n")
    
    md.append("## Stock-by-Stock Analysis\n\n")
    
    # Group by recommendation
    for reco in ["STRONG BUY", "BUY", "ACCUMULATE", "HOLD", "REDUCE", "SELL"]:
        stocks = [a for a in analyses if a.get("recommendation") == reco]
        if not stocks:
            continue
        
        md.append(f"### {reco}\n\n")
        for a in stocks:
            symbol = a.get("symbol", "?")
            rank = a.get("rank", "?")
            score = a.get("score", 0)
            action = a.get("action", "")
            pos = a.get("positive_signals", [])
            neg = a.get("negative_signals", [])
            dma50 = a.get("dma50", 0)
            dma200 = a.get("dma200", 0)
            rsi14 = a.get("rsi14", 50)
            dma_trend = a.get("dma_trend", "N/A")
            momentum = a.get("momentum_score", 0)
            
            md.append(f"**{symbol}** (Rank: {rank}, Score: {score})\n\n")
            md.append(f"- Action: {action}\n")
            md.append(f"- Technicals: DMA50={dma50}, DMA200={dma200}, RSI={rsi14}, Trend={dma_trend}, Momentum={momentum}\n")
            if pos:
                md.append(f"- ✅ Positives: {', '.join(pos)}\n")
            if neg:
                md.append(f"- ⚠️ Concerns: {', '.join(neg)}\n")
            md.append("\n")
    
    # Write file
    out_path = root / output_md
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(md), encoding="utf-8")
    
    return {"status": "success", "path": str(out_path), "analyses_count": len(analyses)}


root_agent = Agent(
    name="advisor_agent",
    model="gemini-2.5-flash",
    description="Analyzes stock rationale and technicals to provide BUY/HOLD/SELL recommendations.",
    instruction=(
        "You are a stock advisor agent. Your job is to analyze the Rationale AND technical indicators "
        "for each stock and provide intelligent recommendations.\n\n"
        "When asked to analyze stocks:\n"
        "1) Call `read_tips_csv` to get all stocks from tips_research_data.csv\n"
        "2) For EACH stock, call `analyze_single_stock` with ALL parameters:\n"
        "   - symbol, rationale, rank, price, quantity\n"
        "   - dma50, dma200, rsi14, dma_trend, momentum_score (from CSV columns)\n"
        "3) Collect all analyses and call `update_recommendations` with the list of symbol+recommendation\n"
        "4) Call `generate_advisor_report` to create data/advisor_report.md\n"
        "5) Reply with summary: how many stocks analyzed, recommendation distribution\n\n"
        "Technical indicator guidelines:\n"
        "- DMA50/DMA200: Price above = bullish, below = bearish\n"
        "- DMA_Trend: BULLISH (50>200 golden cross), BEARISH (50<200 death cross)\n"
        "- RSI14: >70 overbought (caution), <30 oversold (opportunity), 50-70 healthy\n"
        "- Momentum_Score: +2 to +4 strong buy, 0 to +1 neutral, -1 to -2 weak\n\n"
        "Recommendation guidelines:\n"
        "- STRONG BUY: Excellent fundamentals + bullish technicals + Top5 rank\n"
        "- BUY: Good fundamentals + positive technicals\n"
        "- ACCUMULATE: Decent stock, good to add on dips\n"
        "- HOLD: Mixed signals or overbought\n"
        "- REDUCE: Weak outlook, bearish technicals\n"
        "- SELL: Poor fundamentals + death cross + declining metrics\n"
    ),
    tools=[
        read_tips_csv,
        analyze_single_stock,
        update_recommendations,
        generate_advisor_report,
    ],
)
