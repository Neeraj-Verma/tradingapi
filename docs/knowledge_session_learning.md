# Knowledge Session: How Trading Happens in Kite Trading Platform V2

This document explains the internal mechanics of the trading system - how decisions are made, orders are placed, and risk is managed.

---

## Table of Contents

1. [System Architecture Overview](#system-architecture-overview)
2. [The Trading Engine: KiteTraderV2](#the-trading-engine-kitetraderv2)
3. [How a Buy Decision is Made](#how-a-buy-decision-is-made)
4. [Risk Management Deep Dive](#risk-management-deep-dive)
5. [Order Types and GTT Explained](#order-types-and-gtt-explained)
6. [Exit Strategies](#exit-strategies)
7. [Data Flow: From Research to Execution](#data-flow-from-research-to-execution)
8. [State Persistence](#state-persistence)
9. [API Rate Limiting](#api-rate-limiting)
10. [Key Algorithms](#key-algorithms)

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Streamlit UI (main_v2.py)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │   Risk   │ │ Holdings │ │  Trade   │ │   Tips   │           │
│  │Dashboard │ │ Analysis │ │  Actions │ │ Research │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
└───────┼────────────┼────────────┼────────────┼──────────────────┘
        │            │            │            │
        └────────────┴─────┬──────┴────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Trading Engine (kite_trader_v2.py)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Config    │  │    Risk     │  │   Order     │              │
│  │  (Budget,   │  │  (Sector,   │  │ Execution   │              │
│  │   Limits)   │  │  Drawdown)  │  │  (Buy/Sell) │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Zerodha Kite API                             │
│  • Holdings  • Orders  • GTT  • Historical Data  • LTP          │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Trading Engine: KiteTraderV2

The `KiteTraderV2` class is the heart of the system. It:

1. **Manages API connection** to Zerodha Kite
2. **Analyzes stocks** using technical indicators
3. **Enforces risk limits** before any trade
4. **Executes orders** (regular and GTT)
5. **Tracks state** (trailing peaks, last buy dates)

### Key Components

```python
class KiteTraderV2:
    def __init__(self, config):
        self.config = config           # Trading configuration
        self.kite = None               # Kite API client
        self._holdings_cache = None    # Cached holdings (60s)
        self._historical_cache = {}    # Historical data cache
        self._analysis_cache = {}      # Stock analysis cache
        self._trailing_peaks = {}      # Peak prices for trailing stops
        self._last_buy_dates = {}      # When each stock was last bought
```

---

## How a Buy Decision is Made

When you click "Run Smart Investment", here's the complete flow:

### Step 1: Load the Stock Universe

```python
orders = self.read_order_book()  # Reads tips_research_data.csv
orders = [o for o in orders if self.is_top15_rank(o.get('rank', ''))]
```

The system reads from `tips_research_data.csv` which contains:
- Symbol, Quantity, Price, Allocation, Rank

Only Top-15 ranked stocks are considered.

### Step 2: Portfolio Health Check

```python
summary = self.get_portfolio_summary()
if summary['current_drawdown'] >= self.config.risk.max_drawdown_limit:
    return {'error': 'Drawdown limit reached'}  # STOP ALL BUYING
```

If portfolio is down >10% from peak, all buying stops.

### Step 3: Analyze Each Stock

For each stock in the universe:

```python
analysis = self.analyze_stock(symbol)
```

This returns:
- `ltp`: Current price
- `dma_50`: 50-day moving average
- `dma_200`: 200-day moving average
- `atr`: Average True Range (volatility)
- `above_50dma`: Is price > 50 DMA?
- `passes_momentum`: Does it pass all momentum filters?

### Step 4: Momentum Filter

```python
if not analysis.passes_momentum:
    detail['status'] = f'SKIP: {analysis.reason}'
    continue  # Skip this stock
```

**Why?** We only buy stocks in uptrends. A stock below its moving average is in a downtrend - buying it is "catching a falling knife".

### Step 5: Risk Limit Check

```python
can_buy, reason = self.check_risk_limits(symbol, buy_value, holdings, summary)
if not can_buy:
    detail['status'] = f'BLOCKED: {reason}'
    continue  # Skip this stock
```

Risk checks include:
1. **Drawdown**: Portfolio not down too much
2. **Sector exposure**: Not too concentrated in one sector
3. **Stocks per sector**: Max 3 stocks per sector
4. **Buy frequency**: Haven't bought this stock in last 7 days

### Step 6: Execute the Buy

```python
qty = max(1, int(stock_budget / analysis.ltp))
qty = min(qty, self.config.max_qty_per_stock)  # Cap at 500

result = self.place_buy_order(symbol, qty, skip_risk_check=True)
```

The order is placed as MARKET order (immediate execution).

### Step 7: Place Protection (GTT OCO)

```python
if result.success:
    self.place_gtt_oco_atr(symbol, qty, analysis.ltp)
```

Immediately after buying, a GTT OCO (Good Till Triggered - One Cancels Other) is placed with:
- **Stop Loss trigger**: Entry - (ATR × 2)
- **Target trigger**: Entry × 1.16 (16% profit)

### Step 8: Update State

```python
# Refresh holdings for accurate next iteration
self._holdings_cache = None
holdings = self.get_holdings(use_cache=False)
summary = self.get_portfolio_summary()

# Update remaining budget
remaining_budget -= actual_buy_value
```

After each buy, state is refreshed to ensure the next stock is evaluated against current portfolio.

---

## Risk Management Deep Dive

### Sector Exposure Calculation

```python
def get_portfolio_summary(self):
    # Calculate value in each sector
    sector_values = {}
    for h in holdings:
        sector = self.get_sector(h['tradingsymbol'])
        value = h['quantity'] * h.get('last_price', h['average_price'])
        sector_values[sector] = sector_values.get(sector, 0) + value
    
    # Calculate exposure percentages
    sector_exposure = {}
    for sector, value in sector_values.items():
        sector_exposure[sector] = value / total_value
```

**Example:**
- Portfolio value: ₹10,00,000
- IT stocks value: ₹3,50,000
- IT exposure: 35% → **Over limit** (max 30%)
- Result: Cannot buy more IT stocks

### Drawdown Calculation

```python
# Track portfolio peak
if total_value > self._portfolio_peak:
    self._portfolio_peak = total_value

# Calculate drawdown
drawdown = (self._portfolio_peak - total_value) / self._portfolio_peak
```

**Example:**
- Portfolio peak: ₹10,00,000
- Current value: ₹9,20,000
- Drawdown: 8% → OK (limit is 10%)

If portfolio drops to ₹8,90,000 (11% drawdown), all buying stops.

### ATR-Based Stop Loss

ATR (Average True Range) measures volatility:

```python
def calculate_atr(self, symbol, period=14):
    for i in range(1, len(data)):
        tr = max(
            high - low,                    # Today's range
            abs(high - prev_close),        # Gap up
            abs(low - prev_close)          # Gap down
        )
        true_ranges.append(tr)
    return sum(recent_tr) / len(recent_tr)  # Average
```

**Stop Loss Formula:**
```python
sl_distance = atr * 2.0  # 2x ATR
sl_pct = sl_distance / ltp

# Clamp between 5% and 15%
sl_pct = max(0.05, min(sl_pct, 0.15))
```

**Example:**
- Stock price: ₹100
- ATR: ₹4 (stock moves ₹4/day on average)
- SL distance: ₹8 (2 × ₹4)
- SL percentage: 8%
- SL trigger price: ₹92

**Why ATR?** A volatile stock that moves ₹10/day needs wider stops than a stable stock that moves ₹2/day.

---

## Order Types and GTT Explained

### Regular Market Order

```python
order_params = {
    'tradingsymbol': symbol,
    'exchange': 'NSE',
    'transaction_type': 'BUY',
    'quantity': qty,
    'order_type': 'MARKET',
    'product': 'CNC',  # Cash and Carry (delivery)
    'variety': 'regular',
}
order_id = self.kite.place_order(**order_params)
```

Executes immediately at current market price.

### GTT (Good Till Triggered)

GTT orders remain active until triggered or manually cancelled.

**Types:**
1. **SINGLE**: One trigger, one order
2. **OCO**: Two triggers, whichever hits first executes

### GTT OCO for Protection

```python
self.kite.place_gtt(
    trigger_type='two-leg',  # OCO
    tradingsymbol=symbol,
    exchange='NSE',
    trigger_values=[sl_trigger, target_trigger],  # [₹92, ₹116]
    last_price=buy_price,
    orders=[
        {  # Stop Loss leg
            'transaction_type': 'SELL',
            'quantity': qty,
            'price': sl_price,  # Limit price (slightly below trigger)
        },
        {  # Target leg
            'transaction_type': 'SELL',
            'quantity': qty,
            'price': target_trigger,
        }
    ]
)
```

**How it works:**
- If price drops to ₹92 → Stop loss triggers, sells at ~₹91
- If price rises to ₹116 → Target triggers, sells at ₹116
- Whichever happens first cancels the other

### GTT Dip Buy

```python
trigger_price = ltp * 0.95  # 5% below current price
self.kite.place_gtt(
    trigger_type='single',
    trigger_values=[trigger_price],
    orders=[{
        'transaction_type': 'BUY',
        'quantity': qty,
        'price': trigger_price * 1.001,
    }]
)
```

Automatically buys if stock dips 5%. Useful for accumulating at lower prices.

---

## Exit Strategies

### 1. Stop Loss (ATR-Based)

Placed immediately after buying via GTT OCO.

### 2. Trailing Stop

**Concept:** After a stock gains 8%+, we "trail" the stop loss behind the peak price.

```python
def check_trailing_stops(self):
    for h in holdings:
        gain_pct = (ltp - avg_price) / avg_price
        
        # Activate trailing after +8%
        if gain_pct >= 0.08:
            # Track peak price
            if symbol not in self._trailing_peaks:
                self._trailing_peaks[symbol] = ltp
            elif ltp > self._trailing_peaks[symbol]:
                self._trailing_peaks[symbol] = ltp
            
            # Check if stop hit
            peak = self._trailing_peaks[symbol]
            trail_trigger = peak * 0.95  # 5% below peak
            
            if ltp <= trail_trigger:
                # SELL - trailing stop hit
```

**Example:**
- Buy at ₹100
- Stock rises to ₹115 (+15%) → Trailing activates, peak = ₹115
- Stock rises to ₹120 → Peak updates to ₹120
- Stock drops to ₹114 (5% below ₹120) → SELL triggered
- Profit locked: ₹14/share (14%) instead of potential loss

### 3. Partial Profit Booking

```python
def check_partial_exits(self):
    for h in holdings:
        gain_pct = (ltp - avg_price) / avg_price
        
        if gain_pct >= 0.10:  # +10% gain
            exit_qty = int(qty * 0.50)  # Sell 50%
            # Execute partial sell
```

**Why?** Books some profit while letting the rest run.

### 4. Sell Negative P&L

Manual action to cut all losing positions:

```python
def sell_negative_holdings(self):
    negative = [h for h in holdings if h.get('pnl', 0) < 0]
    for stock in negative:
        self.sell_stock(stock['tradingsymbol'], stock['quantity'])
```

---

## Data Flow: From Research to Execution

```
┌─────────────────┐
│ deep_search     │  AI researches stocks, news, fundamentals
│ agent           │
└────────┬────────┘
         │ writes
         ▼
┌─────────────────┐
│ research_data   │  Raw research: Symbol, Rank, Notes
│ .csv            │
└────────┬────────┘
         │ reads
         ▼
┌─────────────────┐
│ tips_research   │  Fetches live prices, calculates quantities
│ agent           │  using DAILY_BUDGET
└────────┬────────┘
         │ writes
         ▼
┌─────────────────┐
│ tips_research   │  Ready to trade: Symbol, Qty, Price, Rank
│ _data.csv       │
└────────┬────────┘
         │ reads
         ▼
┌─────────────────┐
│ KiteTraderV2    │  Applies risk filters, executes orders
│ .read_order_book│
└────────┬────────┘
         │ calls
         ▼
┌─────────────────┐
│ Zerodha Kite    │  Actual order execution
│ API             │
└─────────────────┘
```

---

## State Persistence

The system persists state across restarts:

### 1. Trailing Peaks (`data/trailing_peaks.json`)

```json
{
  "HDFCBANK": 1725.50,
  "TCS": 4250.00
}
```

Records peak prices for trailing stops.

### 2. Last Buy Dates (`data/last_buy_dates.json`)

```json
{
  "HDFCBANK": "2026-03-20T10:30:45",
  "RELIANCE": "2026-03-18T09:15:22"
}
```

Enforces minimum 7 days between re-buying same stock.

### 3. Audit Log (`data/audit_log.jsonl`)

```json
{"timestamp": "2026-03-23T09:30:00", "event": "buy_executed", "symbol": "HDFCBANK", "qty": 5}
{"timestamp": "2026-03-23T09:30:01", "event": "gtt_placed", "symbol": "HDFCBANK", "sl": 1610, "target": 1740}
{"timestamp": "2026-03-23T09:30:05", "event": "investment_blocked", "symbol": "TCS", "reason": "Sector IT at 32%"}
```

Complete audit trail of all decisions.

---

## API Rate Limiting

Kite API limits requests. The system handles this:

### Throttling

```python
self._historical_call_delay = 0.35  # 350ms between calls

def _throttle_historical_call(self):
    elapsed = (datetime.now() - self._last_historical_call).total_seconds()
    if elapsed < self._historical_call_delay:
        time.sleep(self._historical_call_delay - elapsed)
```

### Exponential Backoff

```python
def with_backoff(self, fn, *args, retries=3, base=0.5):
    for attempt in range(retries):
        try:
            return fn(*args)
        except Exception as e:
            if 'too many requests' in str(e).lower():
                wait = 2.0 * (2 ** attempt)  # 2s, 4s, 8s
            else:
                wait = base * (2 ** attempt)  # 0.5s, 1s, 2s
            time.sleep(wait)
```

### Caching

```python
# Holdings cached for 60 seconds
if use_cache and self._holdings_cache_time:
    age = (datetime.now() - self._holdings_cache_time).total_seconds()
    if age < 60:
        return self._holdings_cache

# Instruments cached for 24 hours
# Historical data cached per symbol/days combination
```

---

## Key Algorithms

### Quantity Calculation

```python
stock_budget = min(per_stock_budget, remaining_daily_budget)
qty = max(1, int(stock_budget / ltp))
qty = min(qty, max_qty_per_stock)  # Cap at 500

actual_value = qty * ltp
```

**Example:**
- Budget: ₹10,000
- Stock price: ₹35
- Raw qty: 10000 / 35 = 285
- Capped: min(285, 500) = 285
- Actual value: 285 × ₹35 = ₹9,975

### DMA Calculation

```python
def calculate_dma(self, symbol, period):
    data = self.get_historical_data(symbol, period + 10)
    closes = [d['close'] for d in data[-period:]]
    return sum(closes) / len(closes)
```

Simple moving average of closing prices.

### Sector Mapping

```python
SECTOR_MAPPING = {
    'HDFCBANK': 'Banking',
    'TCS': 'IT',
    'RELIANCE': 'Energy',
    # ... ~150 stocks mapped
}

def get_sector(self, symbol):
    return SECTOR_MAPPING.get(symbol.upper(), "Unknown")
```

Static mapping since Kite API doesn't provide sector data.

---

## Summary: The Complete Trade Lifecycle

```
1. RESEARCH      → deep_search_agent creates research_data.csv
2. UNIVERSE      → tips_research_agent creates tips_research_data.csv with live prices
3. CONNECT       → User connects to Kite API
4. ANALYZE       → System checks portfolio health (drawdown, sectors)
5. FILTER        → Each stock checked for momentum (DMA) and risk limits
6. EXECUTE       → Market order placed for qualifying stocks
7. PROTECT       → GTT OCO placed with ATR-based stop loss
8. TRACK         → State persisted (trailing peaks, buy dates)
9. MONITOR       → Trailing stops and partial exits checked periodically
10. EXIT         → Automatic (GTT triggers) or manual (Sell Negative P&L)
```

---

## Questions for Self-Study

1. Why do we refresh holdings after each buy in `run_simple_investment`?
2. What happens if a stock's sector is "Unknown"?
3. Why is ATR-based SL better than fixed percentage SL?
4. What's the difference between GTT OCO and regular stop loss order?
5. Why do we enforce 7-day gap between re-buying same stock?

---

*This document is part of the Kite Trading Platform V2 knowledge base.*
