"""
Cloud API Client for Gemini ADK Agents
Connects to the deployed Cloud Run service for AI-powered research
"""

import os
import requests
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CloudAPIConfig:
    """Configuration for Cloud API"""
    base_url: str = "https://gemini-adk-agents-vpunjpdcba-uc.a.run.app"
    api_key: str = ""
    timeout: int = 60
    
    @classmethod
    def from_env(cls) -> "CloudAPIConfig":
        return cls(
            base_url=os.getenv("CLOUD_API_URL", "https://gemini-adk-agents-vpunjpdcba-uc.a.run.app"),
            api_key=os.getenv("CLOUD_API_KEY", "kite-agents-2026-secure-key"),
            timeout=int(os.getenv("CLOUD_API_TIMEOUT", "60")),
        )


class CloudAPIClient:
    """Client for interacting with deployed Gemini ADK Agents API"""
    
    def __init__(self, config: Optional[CloudAPIConfig] = None):
        self.config = config or CloudAPIConfig.from_env()
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-Key": self.config.api_key,
            "Content-Type": "application/json"
        })
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to API"""
        url = f"{self.config.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.config.timeout)
        
        try:
            response = self._session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            return {"status": "error", "error": "Request timed out"}
        except requests.exceptions.ConnectionError:
            return {"status": "error", "error": "Connection failed - check internet/API URL"}
        except requests.exceptions.HTTPError as e:
            return {"status": "error", "error": f"HTTP {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health status"""
        return self._request("GET", "/health")
    
    def research(self, query: str, num_results: int = 10, save_results: bool = False) -> Dict[str, Any]:
        """
        Run research agent for stock/market analysis
        
        Args:
            query: Research query (e.g., "HDFC Bank stock analysis")
            num_results: Number of search results to fetch
            save_results: Whether to save results on server
            
        Returns:
            Research results with web search data
        """
        return self._request("POST", "/research", json={
            "query": query,
            "num_results": num_results,
            "save_results": save_results
        })
    
    def chat(self, message: str, system_prompt: Optional[str] = None, 
             model: str = "gemini-2.0-flash", use_vertex: bool = False) -> Dict[str, Any]:
        """
        Chat with Gemini AI for analysis and recommendations
        
        Args:
            message: User message/question
            system_prompt: Optional system instruction
            model: Model to use
            use_vertex: Use Vertex AI instead of direct API
            
        Returns:
            AI response
        """
        return self._request("POST", "/chat", json={
            "message": message,
            "system_prompt": system_prompt,
            "model": model,
            "use_vertex": use_vertex
        })
    
    def analyze(self, data: Dict[str, Any], analysis_type: str = "summary") -> Dict[str, Any]:
        """
        Analyze data using AI
        
        Args:
            data: Data to analyze
            analysis_type: Type of analysis (summary, detailed, statistical)
            
        Returns:
            Analysis results
        """
        return self._request("POST", "/analyze", json={
            "data": data,
            "analysis_type": analysis_type
        })
    
    def generate_report(self, title: str, sections: List[Dict[str, str]], 
                        output_format: str = "markdown") -> Dict[str, Any]:
        """
        Generate formatted report
        
        Args:
            title: Report title
            sections: List of {heading, content} sections
            output_format: Output format (markdown, json)
            
        Returns:
            Generated report
        """
        return self._request("POST", "/report", json={
            "title": title,
            "sections": sections,
            "output_format": output_format
        })
    
    # ==================== STOCK RESEARCH HELPERS ====================
    
    def research_stock(self, symbol: str) -> Dict[str, Any]:
        """Research a specific stock"""
        query = f"{symbol} NSE stock analysis technical fundamentals news today"
        return self.research(query, num_results=10)
    
    def get_stock_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Get AI sentiment analysis for a stock"""
        # First get research data
        research = self.research_stock(symbol)
        
        if research.get("status") != "success":
            return research
        
        # Then ask AI to analyze sentiment
        research_text = str(research.get("result", {}))[:3000]  # Limit context
        
        prompt = f"""Analyze the following research data for {symbol} and provide:
1. Overall sentiment (BULLISH/BEARISH/NEUTRAL)
2. Key positive factors (bullet points)
3. Key risks (bullet points)
4. Short-term outlook (1-2 weeks)
5. Recommendation (BUY/HOLD/SELL/AVOID)

Research data:
{research_text}

Provide a concise analysis."""

        return self.chat(prompt)
    
    def get_sector_analysis(self, sector: str) -> Dict[str, Any]:
        """Get AI analysis for a sector"""
        query = f"Indian stock market {sector} sector analysis outlook 2024"
        research = self.research(query, num_results=8)
        
        if research.get("status") != "success":
            return research
        
        research_text = str(research.get("result", {}))[:3000]
        
        prompt = f"""Analyze the {sector} sector based on this research:
{research_text}

Provide:
1. Sector trend (UP/DOWN/SIDEWAYS)
2. Key drivers
3. Top 3 stocks to watch
4. Risks to monitor"""

        return self.chat(prompt)
    
    def get_market_overview(self) -> Dict[str, Any]:
        """Get daily market overview"""
        query = "Indian stock market today NSE Nifty Sensex analysis"
        research = self.research(query, num_results=8)
        
        if research.get("status") != "success":
            return research
        
        research_text = str(research.get("result", {}))[:3000]
        
        prompt = f"""Based on today's market data:
{research_text}

Provide a brief market overview:
1. Market sentiment (Bullish/Bearish/Neutral)
2. Key levels for Nifty
3. Sectors to watch
4. Trading strategy for today"""

        return self.chat(prompt)
    
    def analyze_tips_stocks(self, stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze multiple stocks from tips research data
        
        Args:
            stocks: List of stock dicts with Symbol, Price, Rank, etc.
            
        Returns:
            AI analysis with recommendations
        """
        # Format stocks for analysis
        stock_summary = "\n".join([
            f"- {s.get('Symbol')}: ₹{s.get('Price', 0):.2f}, Rank: {s.get('Rank', 'N/A')}, "
            f"DMA50: {s.get('DMA50', 'N/A')}, RSI: {s.get('RSI14', 'N/A')}"
            for s in stocks[:20]  # Limit to top 20
        ])
        
        prompt = f"""Analyze these stocks from my trading research:

{stock_summary}

For each stock, provide:
1. Quick assessment (1 line)
2. Recommendation: BUY / HOLD / AVOID
3. Priority: HIGH / MEDIUM / LOW

Then summarize:
- Top 5 buys for today
- Stocks to avoid
- Overall portfolio strategy"""

        return self.chat(prompt)


# Singleton instance
_client: Optional[CloudAPIClient] = None


def get_cloud_client() -> CloudAPIClient:
    """Get or create cloud API client singleton"""
    global _client
    if _client is None:
        _client = CloudAPIClient()
    return _client
