"""ADK Deep Search agent (Vertex AI + Google Search grounding).

Run with:
  adk run deep_search_agent
or (dev UI):
  adk web --no-reload

Vertex AI setup (recommended):
  gcloud auth application-default login
  set GOOGLE_GENAI_USE_VERTEXAI=TRUE
  set GOOGLE_CLOUD_PROJECT=your-project
  set GOOGLE_CLOUD_LOCATION=us-central1

(You can also put those in `deep_search_agent/.env`.)
"""

from google.adk.agents import Agent
from google.adk.tools import google_search

import csv
import re
from pathlib import Path
from typing import Any, Optional


def get_allowed_research_sources() -> dict[str, Any]:
  """Return the curated allowlist of research sources.

  Reads `src/research_sources.py` and extracts the https base URLs from the
  `RESEARCH_SOURCE_URLS` list.
  """
  repo_root = Path(__file__).resolve().parents[1]
  src_file = repo_root / "src" / "research_sources.py"
  if not src_file.exists():
    return {
      "status": "error",
      "message": f"Missing file: {src_file}",
      "urls": [],
      "domains": [],
    }

  text = src_file.read_text(encoding="utf-8")
  urls = re.findall(r"https?://[^\"'\s\]]+", text)

  # Normalize + stable de-dup
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

  return {
    "status": "success",
    "urls": norm_urls,
    "domains": domains,
    "count": len(domains),
  }


def build_site_restricted_query(query: str, max_sites: int = 6) -> dict[str, Any]:
  """Build a Google query restricted to the curated domains.

  Returns a query string like:
    <query> (site:a.com OR site:b.com ...)
  """
  sources = get_allowed_research_sources()
  if sources.get("status") != "success":
    return {"status": "error", "message": sources.get("message", "Unable to load sources"), "query": query}

  domains: list[str] = sources.get("domains", [])
  if not domains:
    return {"status": "error", "message": "No domains found", "query": query}

  max_sites = max(1, int(max_sites))
  picked = domains[:max_sites]
  sites_clause = " OR ".join([f"site:{d}" for d in picked])
  q = f"{query} ({sites_clause})"

  return {"status": "success", "query": q, "domains": picked}


def _rank_within_top_n(rank: str, top_n: int) -> bool:
  """Return True if a rank value falls within Top-N.

  Supports:
  - Numeric ranks: "1", "15"
  - Labels: "Top5", "Top10", "Top15", "Top25"
  - Labels: "Next5" (treated as ranks 6-10)
  """
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


def read_research_data_csv(top_n_rank: Optional[int] = None, max_rows: Optional[int] = None) -> dict[str, Any]:
  """Read `data/research_data.csv` and return the stock universe.

  Args:
    top_n_rank: Optional Top-N filter (e.g. 15 => include Top15 + Next5 only if it falls within Top15).
    max_rows: Optional cap on returned rows.

  Returns:
    dict: status + file path + rows + symbols.
  """
  repo_root = Path(__file__).resolve().parents[1]
  csv_path = repo_root / "data" / "research_data.csv"

  if not csv_path.exists():
    return {
      "status": "error",
      "message": f"File not found: {csv_path}",
      "path": str(csv_path),
      "symbols": [],
      "rows": [],
    }

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

        if max_rows is not None and len(rows) >= int(max_rows):
          break

    # Preserve order but de-duplicate
    seen = set()
    symbols_unique: list[str] = []
    for s in symbols:
      if s not in seen:
        seen.add(s)
        symbols_unique.append(s)

    return {
      "status": "success",
      "path": str(csv_path),
      "count": len(symbols_unique),
      "symbols": symbols_unique,
      "rows": rows,
    }
  except Exception as e:
    return {
      "status": "error",
      "message": str(e),
      "path": str(csv_path),
      "symbols": [],
      "rows": [],
    }


root_agent = Agent(
    name="deep_search_agent",
    model="gemini-2.5-flash",
    description="Deep research agent that uses Google Search grounding and produces a sourced report.",
    instruction=(
      "You are a deep research agent for Indian stocks (NSE/BSE). Use Google Search when needed to get up-to-date facts. "
      "Always include sources (URLs) for factual claims.\n\n"
      "--- SOURCE POLICY (STRICT) ---\n"
      "You MUST use and cite only the curated allowlist of websites from `src/research_sources.py`.\n"
      "Before doing web research, call `get_allowed_research_sources` to obtain allowed domains.\n"
      "When you need to search, call `build_site_restricted_query` and pass its `query` to the `google_search` tool.\n"
      "If a search result is outside the allowlist, ignore it and search again with stricter `site:` filtering.\n\n"
      "--- OUTPUT MODES ---\n"
      "A) Research report mode (default):\n"
      "When the user asks about an Indian stock (NSE/BSE), produce a structured report:\n"
      "1) Executive summary (2-4 bullets)\n"
      "2) Business overview (what it does, segments)\n"
      "3) Recent news (last 30-90 days) with dates\n"
      "4) Financial highlights (latest quarter/year; include numbers only if sourced)\n"
      "5) Valuation/peer context (only if sourced)\n"
      "6) Key risks (3-7 bullets)\n"
      "7) Catalysts (3-7 bullets)\n"
      "8) Monitoring checklist (what to track next)\n\n"
      "If you cannot find reliable sources for a section, say so explicitly instead of guessing.\n\n"
      "B) Order-book CSV mode (only when the user explicitly asks for an order book / CSV / order_book.csv output):\n"
      "Return ONLY a CSV (no markdown, no explanation) with this exact header:\n"
      "Symbol,Quantity,Price,Transaction,Variety,Product,Order_Type,Rank,Allocation,TargetValue,Rationale\n"
      "Rules for CSV mode:\n"
      "- Each row is one BUY idea. Default: Transaction=BUY, Variety=regular, Product=CNC, Order_Type=LIMIT.\n"
      "- Price must be a numeric INR price (prefer the latest LTP/price from a reliable source; if not found, use the best sourced approximation and state the limitation in Rationale).\n"
      "- Allocation is numeric INR amount. TargetValue = Quantity * Price.\n"
      "- Quantity = floor(Allocation / Price) as an integer.\n"
      "- Rank should be one of: Top5, Top10, Top15, etc.\n"
      "- Rationale must be short (1-2 clauses) and include bracketed source markers like [1], [2].\n"
      "- After the CSV rows, add a final line: Sources," 
      "followed by a semicolon-separated list of numbered sources like: [1]=https://...; [2]=https://...\n"
      "- Never invent financial numbers. If a metric can’t be sourced, omit it."
      "\n\n"
      "C) Research-data universe mode (only when the user asks to analyze stocks from research_data.csv):\n"
      "- Call the tool `read_research_data_csv` to load the list of symbols (optionally filtered by Top-N rank).\n"
      "- Then, do web-grounded research ONLY for those symbols (do not add new symbols).\n"
      "- If the user asks for a CSV output, follow CSV mode rules and only include symbols from the tool output."
    ),
    tools=[google_search, read_research_data_csv, get_allowed_research_sources, build_site_restricted_query],
)
