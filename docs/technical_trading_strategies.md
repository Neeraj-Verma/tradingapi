# Technical Trading Strategies Guide

A comprehensive guide to the trading strategies, technical indicators, and risk management concepts used in this platform. This document explains the **"why"** behind each decision.

---

## Table of Contents

1. [Fundamental Trading Philosophy](#fundamental-trading-philosophy)
2. [Technical Indicators](#technical-indicators)
3. [Entry Strategies](#entry-strategies)
4. [Exit Strategies](#exit-strategies)
5. [Risk Management](#risk-management)
6. [Position Sizing](#position-sizing)
7. [Portfolio Construction](#portfolio-construction)
8. [Order Types](#order-types)
9. [Market Psychology](#market-psychology)
10. [Glossary](#glossary)

---

## Fundamental Trading Philosophy

### Trend Following

This platform follows a **trend-following** approach rather than contrarian trading.

**Core Principle**: *"The trend is your friend until it ends."*

| Approach | Description | Risk |
|----------|-------------|------|
| **Trend Following** ✓ | Buy stocks in uptrends, avoid downtrends | Miss bottoms, but avoid falling knives |
| **Contrarian** ✗ | Buy when others sell, "buy the dip" | Can catch falling knives |

**Why Trend Following?**
- Statistically, stocks in uptrends tend to continue up (momentum effect)
- Reduces emotional decision-making
- Aligns with institutional money flow
- Easier to manage risk with defined stop losses

### Systematic Over Discretionary

The platform uses **rule-based systematic trading** rather than gut-feel discretionary trading.

**Benefits:**
- Removes emotional bias (fear, greed)
- Consistent execution
- Backtestable
- Scalable

---

## Technical Indicators

### 1. Moving Averages (DMA)

A **Moving Average** smooths out price data to identify trends.

#### Simple Moving Average (SMA)

```
50 DMA = Sum of last 50 closing prices ÷ 50
```

#### Why 50-Day and 200-Day?

| Period | Significance | Used For |
|--------|--------------|----------|
| **50 DMA** | Medium-term trend | Entry filter, short-term trend confirmation |
| **200 DMA** | Long-term trend | Bull/bear market identification |

**The 50 DMA Rule:**
- Price > 50 DMA → Stock is in **uptrend** → BUY eligible
- Price < 50 DMA → Stock is in **downtrend** → AVOID

**Why?**
- Institutional investors often use 50/200 DMA as decision points
- Creates self-fulfilling support/resistance
- Filters out stocks in distribution phase

#### Golden Cross & Death Cross

| Pattern | Definition | Signal |
|---------|------------|--------|
| **Golden Cross** | 50 DMA crosses above 200 DMA | Bullish (buy signal) |
| **Death Cross** | 50 DMA crosses below 200 DMA | Bearish (sell signal) |

### 2. Average True Range (ATR)

ATR measures **volatility** - how much a stock typically moves in a day.

#### Calculation

```
True Range = MAX of:
  1. Current High - Current Low
  2. |Current High - Previous Close|
  3. |Current Low - Previous Close|

ATR = Average of True Range over N days (typically 14)
```

#### Why ATR Matters

**Problem with Fixed % Stop Loss:**
- Stock A: Moves ₹2/day, ₹100 price → 8% SL = ₹8 → 4 days of movement
- Stock B: Moves ₹8/day, ₹100 price → 8% SL = ₹8 → 1 day of movement

Stock B will get stopped out by normal volatility!

**Solution: ATR-Based Stop Loss**
- SL = 2 × ATR (gives 2 days of "breathing room")
- Volatile stocks get wider stops
- Stable stocks get tighter stops

#### ATR Multiple Selection

| ATR Multiple | Use Case | Risk Level |
|--------------|----------|------------|
| 1.0× | Very tight, day trading | High (frequent stops) |
| 1.5× | Swing trading | Medium |
| **2.0×** ✓ | Position trading | **Balanced** |
| 3.0× | Long-term investing | Low (wider stops) |

---

## Entry Strategies

### Momentum Entry

**Concept**: Buy stocks that are already going up.

**Filters Applied:**
1. Price > 50 DMA (confirmed uptrend)
2. Optionally: Price > 200 DMA (strong bull market)

**Why Not Buy at Support?**
- Support levels break more often than they hold
- Buying at support = betting on reversal = contrarian
- Momentum entry = confirmation that buyers are in control

### Dip Buying (GTT Accumulation)

**Concept**: Set orders to buy on temporary pullbacks within an uptrend.

**Rules:**
1. Stock must already be in uptrend (above DMA)
2. Set buy order 5% below current price
3. If triggered, you're buying a pullback, not a breakdown

**Risk**: Dip could turn into collapse. That's why:
- Momentum filter prevents dip-buying downtrending stocks
- Position sizing limits exposure

---

## Exit Strategies

### 1. Stop Loss (Capital Protection)

**Purpose**: Limit maximum loss per trade.

**Types:**

| Type | Description | Pros | Cons |
|------|-------------|------|------|
| **Fixed %** | Always 8% below entry | Simple | Doesn't account for volatility |
| **ATR-Based** ✓ | 2× ATR below entry | Adapts to volatility | More complex |
| **Chart-Based** | Below support level | Technical validity | Subjective |

**Why ATR-Based?**

Imagine two stocks both at ₹100:
- Stock A: ATR = ₹2 → SL at ₹96 (4%)
- Stock B: ATR = ₹6 → SL at ₹88 (12%)

Stock B is more volatile, so it needs more room to breathe.

### 2. Trailing Stop (Profit Protection)

**Problem**: Fixed stop loss doesn't protect profits.

**Solution**: Move stop loss up as price rises.

#### How Trailing Stop Works

1. **Activation**: Wait for +8% gain (confirms winner)
2. **Track Peak**: Record highest price reached
3. **Trail**: Set stop at 5% below peak
4. **Exit**: Sell if price drops 5% from peak

**Example:**
```
Buy at ₹100
Price rises to ₹110 (+10%) → Trailing activates, Peak = ₹110
Price rises to ₹120 → Peak updates to ₹120, Trail stop = ₹114
Price rises to ₹125 → Peak updates to ₹125, Trail stop = ₹118.75
Price drops to ₹118 → SELL triggered

Result: 18% profit locked (vs potential full round-trip to ₹100)
```

**Why 8% Activation?**
- Filters out small fluctuations
- Ensures stock has proven itself a winner
- Reduces whipsaw exits

**Why 5% Trail Distance?**
- Tight enough to lock significant profits
- Loose enough to avoid premature exit on minor pullbacks

### 3. Partial Profit Booking

**Concept**: Sell part of position at a target, let rest run.

**Rules:**
- At +10% gain: Sell 50% of position
- Remaining 50% rides with trailing stop

**Why?**
- *"You can't go broke taking profits"*
- Reduces psychological pressure
- Guarantees some profit even if stock reverses
- Lets winners run with house money

### 4. Target Exit (GTT OCO)

**OCO = One Cancels Other**

Two orders placed simultaneously:
1. **Stop Loss** at -8% (or ATR-based)
2. **Target** at +16%

Whichever triggers first cancels the other.

**Risk/Reward Ratio:**
```
Reward = 16%
Risk = 8%
R:R = 2:1
```

This means: Even if you're right only 40% of the time, you'll be profitable.

---

## Risk Management

### 1. Position Sizing

**Never risk more than you can afford to lose on a single trade.**

#### Fixed Rupee Amount Method (Used Here)

```
Position Size = Per-Stock Budget ÷ Stock Price
```

**Example:**
- Budget per stock: ₹10,000
- Stock price: ₹500
- Position: 20 shares

**Why Fixed Amount?**
- Simple to implement
- Ensures diversification (many positions)
- Limits damage from any single failure

#### Alternative: Percent Risk Method

```
Position Size = (Account × Risk %) ÷ (Entry - Stop Loss)
```

**Example:**
- Account: ₹10,00,000
- Risk: 1% = ₹10,000
- Entry: ₹100, Stop: ₹92
- Risk per share: ₹8
- Position: ₹10,000 ÷ ₹8 = 1,250 shares

### 2. Daily Budget Cap

**Rule**: Never invest more than X% of capital in a single day.

**Why?**
- Prevents all-in on a single day's ideas
- Spreads entries across time (time diversification)
- Reduces impact of market-wide gap downs

### 3. Drawdown Protection

**Drawdown** = Peak-to-trough decline in portfolio value.

```
Drawdown % = (Peak Value - Current Value) ÷ Peak Value
```

**Rule**: Stop all buying when drawdown exceeds 10%.

**Why?**
- Preserves capital for recovery
- Prevents revenge trading
- Forces reflection on what's not working

**Recovery Math:**
| Drawdown | Required Gain to Recover |
|----------|--------------------------|
| 10% | 11.1% |
| 20% | 25% |
| 30% | 42.9% |
| 50% | 100% |

As losses compound, recovery becomes exponentially harder.

### 4. Sector Concentration Limit

**Rule**: Maximum 30% of portfolio in any single sector.

**Why?**
- Sector correlation: Stocks in same sector move together
- A single sector crisis (e.g., IT slowdown) won't devastate portfolio
- Forced diversification

**Example:**
- Portfolio: ₹10,00,000
- IT stocks: ₹2,80,000 (28%)
- Trying to buy TCS (IT): BLOCKED
- Reason: Would push IT to >30%

### 5. Buy Frequency Control

**Rule**: Minimum 7 days between buying the same stock.

**Why?**
- Prevents emotional averaging down
- Forces patience
- Avoids overconcentration in "favorite" stocks

---

## Portfolio Construction

### Diversification Principles

| Dimension | Implementation |
|-----------|----------------|
| **Sector** | Max 30% per sector, max 3 stocks per sector |
| **Stock** | Max ₹10,000 per stock initially |
| **Time** | Spread buys over days/weeks |

### Position Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| Max stocks per sector | 3 | Prevents over-concentration |
| Max shares per stock | 500 | Handles low-price stocks |
| Min days between re-buy | 7 | Prevents over-trading |

---

## Order Types

### 1. Market Order

**Definition**: Buy/sell immediately at current market price.

**Pros**: Guaranteed execution
**Cons**: May get worse price in volatile markets (slippage)

**Use When**: Speed matters more than exact price.

### 2. Limit Order

**Definition**: Buy/sell only at specified price or better.

**Pros**: Price control
**Cons**: May not execute if price doesn't reach limit

**Use When**: Price precision matters, stock is liquid.

### 3. GTT (Good Till Triggered)

**Definition**: Order that remains active until price trigger is hit.

**Types:**
- **Single**: One trigger → one order
- **OCO**: Two triggers → whichever hits first executes

**Why GTT?**
- Set and forget
- No need to monitor continuously
- Automated discipline

### 4. CNC vs MIS

| Type | Full Form | Purpose |
|------|-----------|---------|
| **CNC** | Cash and Carry | Delivery trading (hold overnight) |
| **MIS** | Margin Intraday Square-off | Intraday only (auto-squared off) |

This platform uses **CNC** for long-term position trading.

---

## Market Psychology

### Why Technical Rules Work

Technical analysis works because **enough people believe it works**.

- When price approaches 200 DMA, many traders watch
- They place buy orders, creating support
- Self-fulfilling prophecy

### Emotional Biases (And How Rules Overcome Them)

| Bias | Description | Platform's Solution |
|------|-------------|---------------------|
| **Fear** | Selling too early, not buying dips | Trailing stops lock profits automatically |
| **Greed** | Holding too long, over-concentrating | Partial exits, sector limits |
| **Hope** | Holding losers, hoping for recovery | Automatic stop losses (GTT) |
| **Confirmation** | Only seeing supporting data | Rule-based: DMA doesn't lie |
| **Recency** | Overweighting recent events | 50/200 DMA smooth out noise |

### The Importance of Systematic Trading

**Discretionary**: "This stock looks good, I'll buy more"
**Systematic**: "Stock passes DMA filter and risk checks = Buy"

Systematic removes the "I feel" from trading.

---

## Glossary

| Term | Definition |
|------|------------|
| **ATR** | Average True Range - measures daily volatility |
| **DMA** | Daily Moving Average - trend indicator |
| **Drawdown** | Peak-to-trough portfolio decline |
| **GTT** | Good Till Triggered - persistent order |
| **LTP** | Last Traded Price - current market price |
| **OCO** | One Cancels Other - paired orders |
| **R:R** | Risk-Reward Ratio |
| **SL** | Stop Loss - maximum loss limit |
| **Trailing Stop** | Stop that moves up with price |
| **Uptrend** | Series of higher highs and higher lows |
| **Downtrend** | Series of lower highs and lower lows |
| **Support** | Price level where buying emerges |
| **Resistance** | Price level where selling emerges |
| **Momentum** | Rate of price change |
| **Volatility** | Degree of price variation |
| **Position Sizing** | How much to invest per trade |
| **Sector Rotation** | Money moving between industry sectors |
| **Whipsaw** | False signal causing premature exit |

---

## Key Takeaways

1. **Trade with the trend**, not against it (DMA filters)
2. **Let winners run**, cut losers short (trailing stops + stop loss)
3. **Diversify** across sectors and stocks
4. **Size positions** appropriately (never risk too much)
5. **Use rules**, not emotions
6. **Protect capital** first, profits second
7. **Compound** gains over time through discipline

---

## Further Reading

- *"Trend Following"* by Michael Covel
- *"Trade Your Way to Financial Freedom"* by Van Tharp
- *"Market Wizards"* by Jack Schwager
- *"Technical Analysis of the Financial Markets"* by John Murphy

---

*This document is part of the Kite Trading Platform V2 knowledge base.*
