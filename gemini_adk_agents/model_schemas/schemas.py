"""
Model Schemas - Pydantic models for data validation
Used across tools and agents for type safety
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum


class AnalysisType(Enum):
    """Types of analysis"""
    SUMMARY = "summary"
    DETAILED = "detailed"
    STATISTICAL = "statistical"
    COMPARATIVE = "comparative"


class ReportFormat(Enum):
    """Report output formats"""
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"


@dataclass
class SearchResult:
    """Web search result"""
    title: str
    url: str
    snippet: str
    source: str = ""
    relevance_score: float = 0.0


@dataclass
class ResearchData:
    """Research data container"""
    topic: str
    query: str
    results: List[SearchResult] = field(default_factory=list)
    summary: str = ""
    sources: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "query": self.query,
            "results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in self.results
            ],
            "summary": self.summary,
            "sources": self.sources,
            "created_at": self.created_at.isoformat(),
            "confidence": self.confidence
        }


@dataclass
class StockData:
    """Stock market data"""
    symbol: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    volume: int = 0
    market_cap: float = 0.0
    sector: str = ""
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "price": self.price,
            "change_pct": self.change_pct,
            "volume": self.volume,
            "market_cap": self.market_cap,
            "sector": self.sector,
            "pe_ratio": self.pe_ratio,
            "dividend_yield": self.dividend_yield
        }


@dataclass
class AnalysisResult:
    """Analysis output"""
    analysis_type: AnalysisType
    timestamp: datetime
    data_summary: Dict[str, Any]
    insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ReportSection:
    """Section in a report"""
    heading: str
    content: str
    subsections: List['ReportSection'] = field(default_factory=list)


@dataclass
class Report:
    """Generated report"""
    title: str
    created_at: datetime
    sections: List[ReportSection]
    format: ReportFormat
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentTask:
    """Task for an agent to execute"""
    task_id: str
    task_type: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    created_at: datetime = field(default_factory=datetime.now)
    deadline: Optional[datetime] = None


@dataclass
class AgentResponse:
    """Response from an agent"""
    task_id: str
    status: str  # success, error, partial
    result: Any = None
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
