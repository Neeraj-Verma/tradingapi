# Kite Trading Platform V2 - Risk-Managed Edition

A sophisticated automated trading platform for Zerodha Kite with built-in portfolio risk controls, momentum filters, and intelligent order management.

## Features

- **Portfolio Risk Controls**: Sector exposure limits, drawdown protection, position sizing
- **Momentum Filters**: 50/200-day moving average checks before buying
- **ATR-Based Stop Loss**: Volatility-adjusted stop losses for each stock
- **Trailing Stops**: Lock in profits on big winners
- **Partial Profit Booking**: Automatically book partial profits at targets
- **Daily Budget Enforcement**: Never exceed your daily investment limit
- **Audit Logging**: Complete decision trail in JSON format
- **Tips Research Agent**: AI-powered stock universe management

---

## Quick Start

### 1. Setup Environment

```bash
# Clone and enter the project
cd kite

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Credentials

Create `src/.env` with your Zerodha API credentials:

```env
API_KEY=your_api_key
API_SECRET=your_api_secret
ACCESS_TOKEN=your_access_token

# Budget Settings
DAILY_BUDGET=100000
PER_STOCK_DAILY_BUDGET=10000
MAX_QTY_PER_STOCK=500

# Risk Settings
MAX_SECTOR_EXPOSURE=0.30
MAX_DRAWDOWN_LIMIT=0.10
MAX_STOCKS_PER_SECTOR=3

# Stop Loss & Target
STOP_LOSS_PERCENT=0.08
TARGET_PERCENT=0.16

# GTT Settings
GTT_BUY_BUDGET_PER_STOCK=10000
```

### 3. Launch the Dashboard

```bash
streamlit run src/main_v2.py
```

Open `http://localhost:8501` in your browser.

---

## Trading Workflow

### Step 1: Connect to Kite

1. Enter your **Access Token** in the sidebar (or click "Generate" to get a new one)
2. Click **Connect**
3. You'll see "✅ Connected as [Your Name]"

> **Note**: Access tokens expire daily. Generate a new one each trading day.

### Step 2: Review Your Portfolio (Risk Dashboard Tab)

Before trading, check your portfolio health:

| Metric | What It Means |
|--------|---------------|
| **Drawdown** | Current loss from portfolio peak. Trading pauses if > limit |
| **Sector Exposure** | % of portfolio in each sector. Diversification check |
| **Momentum Health** | How many stocks are below their 50-day average |
| **Trailing Candidates** | Stocks with >8% gain eligible for trailing stops |

### Step 3: Prepare Your Stock Universe (Tips Research Tab)

1. Go to **📰 Tips Research** tab
2. Review the current `tips_research_data.csv`
3. Set your **Daily Budget** and **Top N Stocks**
4. Click **🚀 Generate Tips CSV** to update with live prices

This creates a ranked list of stocks to buy based on your research data.

### Step 4: Execute Smart Investment (Trade Tab)

1. Go to **🎯 Trade** tab
2. Review the **Order Book** section (shows Top15 stocks)
3. Toggle **Live Mode** ON in sidebar (⚠️ Real orders!)
4. Click **🚀 Run Smart Investment**

The system will:
- Analyze each stock for momentum (DMA checks)
- Check risk limits (sector, drawdown)
- Buy stocks that pass all filters
- Place ATR-based stop loss protection (GTT OCO)
- Track spending against daily budget

### Step 5: Protect Your Holdings

After buying, ensure all holdings have stop losses:

1. Click **🛡️ Protect All Holdings**
2. This places GTT OCO orders with ATR-based stop losses

### Step 6: Monitor & Exit

**Trailing Stops** (for winners):
- Click **📈 Check Trailing Stops** to see stocks eligible
- The system tracks peak prices after +8% gain
- Sells if price drops 5% from peak

**Partial Exits** (book profits):
- Click **💰 Check Partial Exits**
- Sells 50% of position when stock gains 10%+

**Sell Negative P&L**:
- Click **🔴 Sell Negative P&L** to cut losses on all losing positions

---

## Risk Controls Explained

### Sector Exposure Limit
- **Default**: 30% max in any single sector
- **Why**: Prevents over-concentration in one industry
- **Example**: If IT stocks = 28%, won't buy more IT stocks

### Drawdown Protection
- **Default**: 10% max drawdown
- **Why**: Stops buying when portfolio is in deep loss
- **Behavior**: Smart Investment pauses until portfolio recovers

### Momentum Filter (DMA)
- **50 DMA**: Stock must be above 50-day moving average
- **200 DMA**: Optional stricter filter
- **Why**: Avoids catching falling knives

### ATR-Based Stop Loss
- **Formula**: SL = ATR × 2.0 (configurable)
- **Range**: Clamped between 5% and 15%
- **Why**: Volatile stocks get wider stops, stable stocks get tighter stops

### Buy Frequency Control
- **Default**: 7 days between re-buying same stock
- **Why**: Prevents over-trading and averaging down too fast
- **Persisted**: Survives app restarts

---

## Configuration Reference

### Sidebar Controls

| Control | Description |
|---------|-------------|
| **Live Mode** | OFF = Dry run (no real orders), ON = Real trading |
| **Max Sector Exposure** | Maximum % allowed in one sector |
| **Max Drawdown Limit** | Stop buying threshold |
| **Max Stocks/Sector** | Max positions per sector |
| **Require > 50 DMA** | Only buy stocks above 50-day average |
| **Require > 200 DMA** | Stricter momentum filter |
| **Use ATR-Based SL** | Dynamic stop loss based on volatility |
| **Enable Trailing Stop** | Trail stops on winners |
| **Enable Partial Exit** | Book partial profits |
| **Daily Budget** | Total daily investment cap |
| **Per-Stock Budget** | Max investment per stock |
| **Max Qty/Stock** | Cap shares per stock (for cheap stocks) |

---

## File Structure

```
kite/
├── src/
│   ├── main_v2.py           # Streamlit UI
│   ├── kite_trader_v2.py    # Trading engine
│   └── .env                 # Credentials & config
├── data/
│   ├── tips_research_data.csv    # Stock universe (auto-generated)
│   ├── research_data.csv         # Source research data
│   ├── trailing_peaks.json       # Trailing stop tracking
│   ├── last_buy_dates.json       # Buy frequency tracking
│   └── audit_log.jsonl           # Decision audit trail
└── tips_research_agent/
    └── agent.py             # AI agent for tips generation
```

---

## Agents

### tips_research_agent

Generates `tips_research_data.csv` from research data with live prices.

**Via UI**: Tips Research tab → Generate Tips CSV

**Via CLI**:
```bash
echo "Generate tips_research_data.csv for Top15 using DAILY_BUDGET." | adk run tips_research_agent
```

### deep_search_agent

Researches stocks and updates `research_data.csv`.

```bash
adk run deep_search_agent
```

---

## Troubleshooting

### "Too many requests" warnings
- **Cause**: Kite API rate limiting
- **Fix**: Already handled with throttling (350ms between calls). Restart if persistent.

### Access token expired
- **Cause**: Tokens expire daily at 6 AM
- **Fix**: Click "Generate" in sidebar to get new token

### "Drawdown limit reached"
- **Cause**: Portfolio down more than 10%
- **Fix**: Wait for recovery or increase `MAX_DRAWDOWN_LIMIT`

### Stocks showing "Unknown" sector
- **Cause**: Stock not in sector mapping
- **Fix**: Add to `SECTOR_MAPPING` in `kite_trader_v2.py`

---

## Safety Tips

1. **Always start in Dry Run mode** - Verify behavior before going live
2. **Set conservative budgets** - Start with smaller daily budgets
3. **Check Risk Dashboard first** - Ensure portfolio health before trading
4. **Review audit logs** - Check `data/audit_log.jsonl` for decisions
5. **Don't override risk limits** - They exist for a reason
6. **Monitor trailing stops manually** - Automation isn't perfect

---

## License

For personal use only. Not financial advice. Trade at your own risk.
