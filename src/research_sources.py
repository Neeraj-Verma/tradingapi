"""Curated website sources for deep stock research.

This module intentionally contains only a static allowlist of sources
(plus a small helper) so other modules can import it without side effects.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse


RESEARCH_SOURCE_URLS: list[str] = [
    "https://www.moneycontrol.com/",
    "https://www.screener.in/",
    "https://kite.zerodha.com/",
    "https://groww.in/",
    "https://www.tickertape.in/",
    "https://economictimes.indiatimes.com/",
    "https://www.nseindia.com/",
    "https://www.bseindia.com/",
    "https://chartink.com/",
    "https://trendlyne.com/",
    "https://stockedge.com/",
    "https://www.livemint.com/",
    "https://in.investing.com/",
    "https://upstox.com/",
    "https://www.angelone.in/",
    "https://dhan.co/",
    "https://fyers.in/",
    "https://www.mcxlive.org/",
    "https://www.sebi.gov.in/",
    "https://www.niftyindices.com/",
]


# Wildcard-style URL patterns (useful for domain/path allowlisting).
# Example: "https://www.nseindia.com/*"
RESEARCH_SOURCE_GLOB_URLS: list[str] = [
    url.rstrip("/") + "/*" for url in RESEARCH_SOURCE_URLS
]


# Common sections/paths across finance sites that typically contain:
# - stock/company pages, financial performance, results, and filings
# - news, corporate actions, and analyst/brokerage coverage
# - buy/sell ideas and recommendations
RESEARCH_PATH_HINTS: list[str] = [
    "news",
    "markets",
    "stocks",
    "equities",
    "company",
    "companies",
    "quote",
    "share-price",
    "price",
    "financials",
    "fundamentals",
    "results",
    "earnings",
    "quarter",
    "balance-sheet",
    "cash-flow",
    "profit-loss",
    "ratios",
    "valuation",
    "analysis",
    "research",
    "brokerage",
    "recommendation",
    "ratings",
    "buy",
    "sell",
    "technical",
    "charts",
    "corporate-actions",
    "dividend",
    "bonus",
    "split",
    "announcements",
    "press-release",
    "filings",
]


def build_research_topic_globs(
    topics: list[str] | None = None,
    base_urls: list[str] | None = None,
) -> list[str]:
    """Build URL glob patterns like `https://example.com/news*` for each base URL.

    Notes:
    - These are not guaranteed to be valid pages for every site; they are intended
      as *hints* to focus crawling/search toward likely relevant sections.
    - Prefer using domains for strict allowlisting; use topic globs for scoring.
    """

    topics = topics or RESEARCH_PATH_HINTS
    base_urls = base_urls or RESEARCH_SOURCE_URLS
    patterns: list[str] = []

    for base in base_urls:
        base = base if base.endswith("/") else base + "/"
        for topic in topics:
            topic = topic.strip().lstrip("/")
            if not topic:
                continue

            # urljoin handles cases where base may be a subdomain or include a path.
            # We add a trailing * wildcard for prefix matching.
            patterns.append(urljoin(base, topic) + "*")

    # Stable order + de-dup
    return list(dict.fromkeys(patterns))


def research_source_domains(urls: list[str] | None = None) -> list[str]:
    """Return hostname domains for the given URLs (defaults to RESEARCH_SOURCE_URLS)."""

    urls = urls or RESEARCH_SOURCE_URLS
    domains: list[str] = []
    for url in urls:
        hostname = urlparse(url).hostname
        if hostname and hostname not in domains:
            domains.append(hostname)
    return domains


RESEARCH_SOURCE_DOMAINS: list[str] = research_source_domains()
