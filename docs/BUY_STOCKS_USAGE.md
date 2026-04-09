# Buy Stocks Script - Usage Guide

## Overview

`buy_stocks.py` implements a **budget-based tranche buying strategy** for Zerodha Kite that:
1. Buys stocks in phases using **daily budget allocation**
2. Automatically **resumes from where it left off** if cancelled and re-run
3. Places **GTT OCO** orders (stop-loss + target) after fills
4. Supports **sliced GTT** with graduated SL/Target levels
5. Implements **trailing stops** that lock in profits when stocks surge
6. Can **buy only NEW stocks** from research data (skips existing holdings)
7. Includes production-grade safety features

## Architecture

![Tranche Strategy Architecture](architecture.png)

**Flow Summary:**
1. **Initialization** - Validates credentials and checks market hours
2. **Resume Logic** - Detects existing orders from today to enable crash recovery
3. **Phase 1** - Buys 1 share of each stock at MARKET price (base position)
4. **Phase 2** - Executes 5 hourly tranches, buying portions at LIMIT price (0.2% below LTP)
5. **Completion** - Prints summary and suggests `--protect` for GTT OCO protection

**Command Flows:**
- `--protect` → Single GTT OCO per stock (-10% SL / +20% Target)
- `--protect --sliced` → 3 GTTs per stock with graduated levels
- `--protect --refresh` → Deletes + recreates GTTs with trailing stops
- `--new-stocks` → Compares holdings vs research_data.csv, buys only NEW stocks
- `--gtt-buy` → Places GTT buy orders at -2% and -4% below current price for Top15 (dip accumulation)

---

## Prerequisites

### 1. Environment Variables

Create a `.env` file in the project root:

```env
API_KEY=your_api_key
API_SECRET=your_api_secret
ACCESS_TOKEN=your_daily_access_token
DAILY_BUDGET=100000
```

> **Note:** Access token expires daily. Generate fresh token each morning using `generate_token.py`

### 2. Order Book CSV

Create `order_book.csv` with your buy orders:

```csv
Symbol,Quantity,Price,Transaction,Variety,Product,Order_Type
RELIANCE,10,2450.00,BUY,regular,CNC,LIMIT
TCS,5,3200.00,BUY,regular,CNC,LIMIT
INFY,8,1500.00,BUY,regular,CNC,LIMIT
HDFCBANK,6,1650.00,BUY,regular,CNC,LIMIT
```

| Column | Values | Description |
|--------|--------|-------------|
| `Symbol` | NSE symbol | Stock trading symbol |
| `Transaction` | `BUY` | Only BUY orders processed |
| `Quantity` | Integer | Max shares to buy (cap in budget mode) |
| `Price` | Decimal | Expected price (for LTP drift check) |
| `Product` | `CNC`, `MIS`, `NRML` | CNC for delivery |
| `Variety` | `regular`, `amo` | Order variety |
| `Order_Type` | `MARKET`, `LIMIT` | Order type |

---

## Command Line Usage

```powershell
# Show help
python buy_stocks.py --help

# Dry run (default) - preview without executing orders
python buy_stocks.py

# Live mode - execute real orders
python buy_stocks.py --live

# Set daily budget (default: ₹1,00,000)
python buy_stocks.py --budget 50000

# Use CSV quantities instead of budget-based calculation
python buy_stocks.py --qty-mode

# Update CSV prices with current market LTP
python buy_stocks.py --update-prices

# Protect existing holdings with GTT OCO (skip buying)
python buy_stocks.py --protect

# Sliced GTT OCO - multiple SL/Target levels per stock
python buy_stocks.py --protect --sliced

# Refresh GTTs with trailing stops (based on current LTP)
python buy_stocks.py --protect --refresh --live

# Buy only NEW stocks from research_data.csv
python buy_stocks.py --new-stocks --live

# Place GTT buy orders for dip accumulation (Top15 only, -2%/-4% triggers)
python buy_stocks.py --gtt-buy --live

# Refresh GTT buy orders using latest LTP (deletes existing BUY GTTs for those symbols)
python buy_stocks.py --gtt-buy --refresh --live

# Delete ALL active BUY-side GTTs (safe: does not delete SELL protection GTTs)
python buy_stocks.py --delete-buy-gtts --live

# Use custom order file
python buy_stocks.py --file my_orders.csv

# Combine flags
python buy_stocks.py --budget 200000 --live
```

### CLI Options

| Flag | Description |
|------|-------------|
| `--help` | Show help message |
| `--live` | Execute real orders (overrides DRY_RUN) |
| `--budget AMOUNT` | Daily budget in INR (default: ₹1,00,000) |
| `--qty-mode` | Use CSV quantities instead of budget-based |
| `--protect` | Only place GTT OCO on existing holdings |
| `--sliced` | Use sliced GTT OCO (multiple SL/Target levels) |
| `--refresh` | Delete existing GTTs and recreate with trailing stops |
| `--new-stocks` | Buy 1 share each of NEW stocks from research_data.csv |
| `--gtt-buy` | Place GTT buy orders at -2%/-4% below current price (Top15 only) |
| `--delete-buy-gtts` | Delete ALL active BUY-side GTTs (does not touch SELL protection GTTs) |
| `--file FILE` | Use custom CSV file (default: order_book.csv) |
| `--update-prices` | Fetch current LTP and update CSV |

---

## Strategy Modes

### Budget Mode (Default)

Quantities are calculated based on budget allocation:

```
Daily Budget: ₹1,00,000
├── Phase 1 (base): ₹10,000 (10%)
│   └── 1 share of each @ MARKET
└── Phase 2: ₹90,000 (90%)
    ├── Tranche 1: ₹18,000 → qty = budget / LTP
    ├── Tranche 2: ₹18,000
    ├── Tranche 3: ₹18,000
    ├── Tranche 4: ₹18,000
    └── Tranche 5: ₹18,000
```

**Per Stock Calculation:**
```
qty_to_buy = (tranche_budget / num_stocks) / current_LTP
Example: (₹22,500 / 19 stocks) / ₹264 = 4 shares of ONGC
```

### Quantity Mode (`--qty-mode`)

Uses quantities from CSV directly:
- Phase 1: 1 share each @ MARKET
- Phase 2: Remaining qty ÷ tranches remaining

---

## Idempotent Re-runs (Resume Feature)

If you cancel the script and re-run it, it will **automatically resume** from where it left off:

1. **Checks today's orders** - Fetches all BUY orders placed today
2. **Initializes tracker** - Pre-populates with already-filled quantities
3. **Shows resume status** - Displays what was already bought
4. **Skips completed stocks** - Only places orders for remaining quantity
5. **Smart tranche skip** - Jumps to appropriate tranche based on progress

**Example Re-run Output:**
```
📋 RESUMING FROM PREVIOUS RUN:
------------------------------------------------------------
   RELIANCE          5/18   bought,   13 remaining
   TCS               3/6    bought,    3 remaining
   INFY              7/14   bought,    7 remaining
------------------------------------------------------------
⏭️  Progress 45% - resuming at tranche 2
```

---

## Strategy Details

### Phase 1: Base Price Orders (9:15 AM)
- Buys **1 share** of each stock at **MARKET** price
- Establishes actual fill price for stop-loss calculation
- Places GTT OCO immediately after fill

### Phase 2: Tranche Orders (Hourly)
- **5 tranches** at 1-hour intervals
- Each tranche buys **20%** of remaining quantity
- Uses **LIMIT** orders at **0.2% below LTP**
- Cancels pending unfilled orders before placing new ones

### Stop-Loss Protection
After each fill, places **GTT OCO** (Good Till Triggered - One Cancels Other):
- **Stop-Loss:** 10% below fill price (with 5% execution buffer)
- **Target:** 20% above fill price

---

## Configuration

Edit these constants in `buy_stocks.py`:

```python
# Mode
DRY_RUN = True                    # Set False for live trading

# Budget-Based Strategy (NEW)
USE_BUDGET_MODE = True            # True = budget-based, False = CSV qty
DAILY_BUDGET = 100000             # ₹1 lakh daily budget
BASE_BUDGET_PERCENT = 0.10        # 10% for Phase 1 base orders

# Tranche Settings
TRANCHE_COUNT = 5                 # Number of hourly tranches
TRANCHE_SIZE = 0.20               # 20% per tranche (qty mode only)
TRANCHE_INTERVAL = 3600           # 1 hour between tranches
LTP_DISCOUNT = 0.998              # Limit price = 99.8% of LTP

# Stop-Loss
STOP_LOSS_ENABLED = False         # Recommend False during buying
STOP_LOSS_PERCENT = 0.10          # 10% stop-loss
TARGET_PERCENT = 0.20             # 20% target
SL_EXECUTION_BUFFER = 0.05        # 5% gap-down buffer
USE_GTT = True                    # Use GTT (persists across sessions)
USE_OCO = True                    # Use OCO (SL + Target combo)

# Risk Controls
MAX_BUDGET = 500000               # Maximum total investment cap
MAX_LTP_DRIFT = 0.03              # Skip if LTP drifted >3% from CSV
DEFAULT_TICK = 0.05               # NSE tick size

# Market Hours
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 29
```

---

## Safety Features

| Feature | Description |
|---------|-------------|
| **Dry Run Mode** | Default mode - no real orders placed |
| **Budget Cap** | Aborts if total exceeds `MAX_BUDGET` |
| **Real-time Budget** | Tracks actual spent, warns at 95% usage |
| **Market Hours Guard** | Blocks live execution outside 9:15-3:29 |
| **Kill Switch** | Create `KILL_SWITCH_ON` file or set env var to halt |
| **LTP Drift Check** | Skips stock if price moved >3% from CSV |
| **Idempotent Re-runs** | Resumes from where left off if re-run |
| **Order Sync** | Syncs with broker holdings before each tranche |
| **Credential Validation** | Verifies API credentials before starting |
| **GTT Idempotency** | Skips stocks with existing active GTT orders |
| **Tick Rounding** | Prices rounded to NSE 0.05 tick size |
| **API Backoff** | Automatic retry with exponential backoff |
| **Duplicate Detection** | Warns about duplicate symbols in CSV |

### Emergency Stop

To halt the script mid-execution:

```powershell
# Option 1: Create kill switch file
New-Item -Path "KILL_SWITCH_ON" -ItemType File

# Option 2: Set environment variable
$env:KILL_SWITCH = "1"
```

---

## Typical Daily Workflow

```powershell
# 1. Morning: Generate fresh access token
python generate_token.py

# 2. Update prices with current LTP
python buy_stocks.py --update-prices

# 3. Test with dry run
python buy_stocks.py --budget 100000

# 4. Review output, then go live
python buy_stocks.py --budget 100000 --live
# Type 'CONFIRM' when prompted

# 5. If cancelled mid-way, simply re-run (auto-resumes)
python buy_stocks.py --budget 100000 --live

# 6. End of day: Protect holdings with GTT OCO
python buy_stocks.py --protect --live

# 7. Days later: Refresh GTTs with trailing stops (if stocks have gained)
python buy_stocks.py --protect --refresh --live

# 8. When research data updates: Buy only NEW stock recommendations
python buy_stocks.py --new-stocks --live
```

---

## Output Example (Budget Mode)

```
============================================================
ZERODHA KITE - TRANCHE BUYING STRATEGY
============================================================

📅 Started at: 2026-03-16 09:15:00

📋 Found 19 stocks in order_book.csv
💰 Total investment required: ₹406,315.75

------------------------------------------------------------
📊 TRANCHE STRATEGY:
------------------------------------------------------------
  💵 MODE: BUDGET-BASED (Daily: ₹100,000)
  Phase 1: ₹10,000 for base orders (10% of budget)
  Phase 2: 5 tranches × ₹18,000 each
  Per Stock: ~₹947/stock/tranche
  Limit Price: 0.2% below LTP
  Interval: 60 minutes between tranches
  Stop Loss: 10% below | Target: 20% above (GTT OCO)
------------------------------------------------------------

Symbol          Total Qty      Price        Total
--------------------------------------------------
RELIANCE               10    2450.00     24500.00
TCS                     5    3200.00     16000.00
...
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: kiteconnect` | Run `pip install kiteconnect python-dotenv` |
| `Invalid credentials` | Regenerate access token with `generate_token.py` |
| `GTT order rejected` | Check if TPIN authorization is done for the day |
| `Price rejected` | Ensure price is in valid tick (0.05 increments) |
| `Budget exceeded` | Reduce budget with `--budget` or increase `MAX_BUDGET` |
| `Market is closed` | Script blocks live execution outside 9:15-3:29 IST |
| `LTP drifted >3%` | Run `--update-prices` to refresh CSV prices |
| `Already complete` | All orders done in previous run, use `--protect` |
| `Duplicate symbol` | Remove duplicates from CSV file |

---

## Related Scripts

| Script | Purpose |
|--------|---------|
| `generate_token.py` | Generate daily access token |
| `test_buy_stocks.py` | Test buy 1 share, fetch LTP |
| `sell_negative_stocks.py` | Sell stocks with negative P&L |
| `show_losses.py` | Display current portfolio losses |
| `todays_order_losses.py` | Show today's order P&L |

---

## Advanced Features

### Sliced GTT OCO (`--protect --sliced`)

Creates **multiple GTTs per stock** with graduated SL/Target levels:

```
Default Slices:
├── Slice 1 (30% qty): SL -5%,  Target +10%  → Book early profits
├── Slice 2 (40% qty): SL -8%,  Target +15%  → Moderate risk/reward
└── Slice 3 (30% qty): SL -10%, Target +20%  → Let winners run
```

**Benefits:**
- Partial profit booking at different levels
- Only 30% exits at first SL, rest has wider buffer
- ⚠️ Uses 3 GTTs per stock (100 GTT limit per account)

```powershell
python buy_stocks.py --protect --sliced --live
```

### Trailing Stop (`--protect --refresh`)

Refreshes existing GTTs with **trailing stop logic**:

- If stock **LTP > original target**, uses LTP as new base
- Locks in profits by shifting SL upward

**Example:**
```
KIRLOSENG:
  Avg Price: ₹1,066
  Original Target: ₹1,279 (+20%)
  Current LTP: ₹1,502 (+41%)
  
  OLD GTT (no trailing): SL = ₹959 (-10% of avg)
  NEW GTT (trailing):    SL = ₹1,352 (-10% of LTP) → Locks in +27%
```

```powershell
# First time: creates normal GTTs
python buy_stocks.py --protect --live

# Later: refresh with trailing stops
python buy_stocks.py --protect --refresh --live
```

### Buy New Stocks (`--new-stocks`)

Compares `research_data.csv` with current holdings and buys **only NEW stocks**:

1. Fetches current holdings from Kite
2. Reads research_data.csv (40 stocks)
3. Finds new symbols not already owned
4. Checks for today's existing orders (idempotency)
5. Places Phase 1 orders (1 share each at MARKET)

```powershell
# Dry run - see what would be bought
python buy_stocks.py --new-stocks

# Live execution
python buy_stocks.py --new-stocks --live
```

**Example Output:**
```
SCANNING FOR NEW STOCKS IN RESEARCH DATA
======================================================================
Current Holdings: 35 stocks
Research Data: 40 stocks

Already Own: 20 stocks
New Stocks: 20 stocks

Symbol           Price      Rank
----------------------------------------
HDFCBANK        817.00     Top5
RELIANCE       1380.00     Top5
BHARTIARTL    1798.00     Top5
...
```

### GTT Order Types Summary

| Mode | SL | Target | GTTs Used |
|------|----|----|----------|
| `--protect` | -10% of avg | +20% of avg | 1 per stock |
| `--protect --sliced` | -5%/-8%/-10% graduated | +10%/+15%/+20% graduated | 3 per stock |
| `--protect --refresh` | -10% of LTP (if LTP > target) | +20% of LTP | 1 per stock |
| `--protect --refresh --sliced` | All above with trailing | All above with trailing | 3 per stock |

### GTT Buy Orders (`--gtt-buy`)

Places **GTT buy orders** to accumulate Top15 stocks on dips:

```
Strategy: Buy when price drops
├── Trigger 1 (-2%):  60% of quantity → First dip buy
└── Trigger 2 (-4%): 40% of quantity → Deeper dip buy
```

**Configuration** (in buy_stocks.py):
```python
GTT_BUY_LOWER_PERCENT = 0.02  # 2% below current price
GTT_BUY_UPPER_PERCENT = 0.04  # 4% below current price
GTT_BUY_QTY_LOWER = 0.60      # 60% qty at lower trigger
GTT_BUY_QTY_UPPER = 0.40      # 40% qty at upper trigger
```

**Example:**
```
RELIANCE @ ₹1,380 (current LTP)
├── GTT Buy 1: Trigger @ ₹1,352 (-2%)  → Buy 6 shares
└── GTT Buy 2: Trigger @ ₹1,325 (-4%) → Buy 4 shares
```

**Usage:**
```powershell
# Dry run - see what GTT buys would be placed
python buy_stocks.py --gtt-buy

# Live execution
python buy_stocks.py --gtt-buy --live

# Refresh (delete existing BUY-side GTTs for these symbols and recreate using latest LTP)
python buy_stocks.py --gtt-buy --refresh --live
```

**Quantity calculation (budget-based):**
- Default behavior uses **budget sizing**: `qty = floor(budget_per_stock / LTP)`
- If your CSV has an `Allocation` column (like `research_data.csv`), it is treated as a **weight** to split your total `--budget` across symbols
- Otherwise it falls back to splitting `--budget` equally across all symbols (and applies `--per-stock-budget` cap)
- Use `--qty-mode` to force using the CSV `Quantity` instead

⚠️ **Note:** Each stock uses 1–2 GTT slots (depending on quantity split; Zerodha limit: 100 active GTTs per account)
