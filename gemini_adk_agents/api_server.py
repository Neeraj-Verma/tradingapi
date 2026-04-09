"""
API Server for Gemini ADK Agents
Exposes agents via REST API for remote access
Deploy to Cloud Run, Cloud Functions, or any server
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import tools
from tools.search_tool import web_search, get_webpage_content
from tools.data_tool import save_research_data, load_research_data, analyze_data, generate_report

# Try to import Gemini
try:
    from llm.gemini_config import get_gemini_model, GeminiConfig
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("Gemini not available")

# Try to import Vertex AI
try:
    from llm.vertex_config import get_vertex_model, VertexConfig
    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False
    logger.warning("Vertex AI not available")


# ==================== PYDANTIC MODELS ====================

class ResearchRequest(BaseModel):
    """Request for research task"""
    query: str = Field(..., description="Research query or topic")
    num_results: int = Field(default=10, description="Number of search results")
    save_results: bool = Field(default=True, description="Save results to file")


class AnalysisRequest(BaseModel):
    """Request for analysis task"""
    data: Dict[str, Any] = Field(..., description="Data to analyze")
    analysis_type: str = Field(default="summary", description="Type of analysis")


class ReportRequest(BaseModel):
    """Request for report generation"""
    title: str = Field(..., description="Report title")
    sections: List[Dict[str, str]] = Field(..., description="Report sections")
    output_format: str = Field(default="markdown", description="Output format")


class ChatRequest(BaseModel):
    """Request for chat interaction"""
    message: str = Field(..., description="User message")
    system_prompt: Optional[str] = Field(default=None, description="System instruction")
    model: str = Field(default=os.getenv("ADK_MODEL", "gemini-2.5-flash"), description="Model to use")
    use_vertex: bool = Field(default=False, description="Use Vertex AI instead of direct API")


class AgentResponse(BaseModel):
    """Standard agent response"""
    status: str
    result: Any = None
    error: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ==================== API KEY SECURITY ====================

API_KEY = os.getenv("API_SECRET_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Verify API key for protected endpoints"""
    # If no API_SECRET_KEY is set, allow all requests (for development)
    if not API_KEY:
        return True
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return True


# ==================== FASTAPI APP ====================

app = FastAPI(
    title="Gemini ADK Agents API",
    description="REST API for AI agents powered by Google Gemini and Vertex AI",
    version="1.0.0",
)

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== HEALTH CHECK ====================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Gemini ADK Agents API",
        "status": "running",
        "version": "1.0.0",
        "endpoints": ["/health", "/research", "/analyze", "/report", "/chat"],
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "gemini_available": GEMINI_AVAILABLE,
        "vertex_available": VERTEX_AVAILABLE,
        "timestamp": datetime.now().isoformat(),
    }


# ==================== RESEARCH AGENT ====================

@app.post("/research", response_model=AgentResponse, dependencies=[Depends(verify_api_key)])
async def run_research(request: ResearchRequest):
    """
    Run research agent to search and gather information
    
    - **query**: Topic or question to research
    - **num_results**: Number of search results to fetch
    - **save_results**: Whether to save results to file
    """
    try:
        logger.info(f"Research request: {request.query}")
        
        # Perform web search
        search_results = web_search(request.query, request.num_results)
        results_data = json.loads(search_results)
        
        # Save if requested
        if request.save_results and results_data.get("status") == "success":
            filename = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            save_research_data(results_data, filename)
        
        return AgentResponse(
            status="success",
            result=results_data,
        )
    except Exception as e:
        logger.error(f"Research error: {e}")
        return AgentResponse(
            status="error",
            error=str(e),
        )


# ==================== ANALYSIS AGENT ====================

@app.post("/analyze", response_model=AgentResponse, dependencies=[Depends(verify_api_key)])
async def run_analysis(request: AnalysisRequest):
    """
    Run analysis agent on provided data
    
    - **data**: Data dictionary to analyze
    - **analysis_type**: summary, detailed, or statistical
    """
    try:
        logger.info(f"Analysis request: {request.analysis_type}")
        
        analysis_result = analyze_data(request.data, request.analysis_type)
        results_data = json.loads(analysis_result)
        
        return AgentResponse(
            status="success",
            result=results_data,
        )
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return AgentResponse(
            status="error",
            error=str(e),
        )


# ==================== REPORT GENERATION ====================

@app.post("/report", response_model=AgentResponse, dependencies=[Depends(verify_api_key)])
async def generate_report_endpoint(request: ReportRequest):
    """
    Generate a formatted report
    
    - **title**: Report title
    - **sections**: List of {heading, content} sections
    - **output_format**: markdown or json
    """
    try:
        logger.info(f"Report request: {request.title}")
        
        report_result = generate_report(
            request.title,
            request.sections,
            request.output_format,
        )
        results_data = json.loads(report_result)
        
        return AgentResponse(
            status="success",
            result=results_data,
        )
    except Exception as e:
        logger.error(f"Report error: {e}")
        return AgentResponse(
            status="error",
            error=str(e),
        )


# ==================== CHAT WITH GEMINI ====================

@app.post("/chat", response_model=AgentResponse, dependencies=[Depends(verify_api_key)])
async def chat_with_gemini(request: ChatRequest):
    """
    Chat with Gemini model directly
    
    - **message**: User message to send
    - **system_prompt**: Optional system instruction
    - **model**: Model to use (gemini-2.0-flash, etc.)
    - **use_vertex**: Use Vertex AI instead of direct API
    """
    try:
        logger.info(f"Chat request: {request.message[:50]}...")
        
        if request.use_vertex:
            if not VERTEX_AVAILABLE:
                raise HTTPException(status_code=503, detail="Vertex AI not available")
            
            config = VertexConfig(
                model_name=request.model,
                system_instruction=request.system_prompt,
            )
            model = get_vertex_model(config)
        else:
            if not GEMINI_AVAILABLE:
                raise HTTPException(status_code=503, detail="Gemini API not available")
            
            config = GeminiConfig(
                model_name=request.model,
                system_instruction=request.system_prompt,
            )
            model = get_gemini_model(config)
        
        # Generate response
        response = model.generate_content(request.message)
        
        return AgentResponse(
            status="success",
            result={
                "model": request.model,
                "response": response.text,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return AgentResponse(
            status="error",
            error=str(e),
        )


# ==================== RESEARCH SOURCES ====================

RESEARCH_SOURCE_DOMAINS = [
    "moneycontrol.com",
    "screener.in",
    "tickertape.in",
    "economictimes.indiatimes.com",
    "nseindia.com",
    "bseindia.com",
    "trendlyne.com",
    "stockedge.com",
    "livemint.com",
    "investing.com",
]


# ==================== TIPS RESEARCH AGENT ====================

class TipsResearchRequest(BaseModel):
    """Request for tips research"""
    stocks: List[Dict[str, Any]] = Field(..., description="List of stocks with Symbol, Price, Rank etc.")
    max_stocks: int = Field(default=10, description="Max stocks to analyze")
    search_per_stock: int = Field(default=5, description="Number of search results per stock")


@app.post("/tips-research", response_model=AgentResponse, dependencies=[Depends(verify_api_key)])
async def run_tips_research(request: TipsResearchRequest):
    """
    Research stocks from tips data using web search and AI analysis
    
    - **stocks**: List of stock dicts with Symbol, Price, Rank, etc.
    - **max_stocks**: Maximum number of stocks to analyze
    - **search_per_stock**: Number of search results to fetch per stock
    
    Returns AI-generated recommendations with rationale for each stock.
    """
    try:
        logger.info(f"Tips research request: {len(request.stocks)} stocks, max {request.max_stocks}")
        
        if not GEMINI_AVAILABLE:
            raise HTTPException(status_code=503, detail="Gemini API not available")
        
        stocks_to_analyze = request.stocks[:request.max_stocks]
        research_results = []
        
        # Build site restriction for search
        site_filter = " OR ".join([f"site:{domain}" for domain in RESEARCH_SOURCE_DOMAINS[:5]])
        
        for stock in stocks_to_analyze:
            symbol = stock.get("Symbol", "UNKNOWN")
            price = stock.get("Price", 0)
            rank = stock.get("Rank", "N/A")
            
            logger.info(f"Researching {symbol}...")
            
            # Search for stock news and analysis
            search_query = f"{symbol} NSE stock analysis news recommendation ({site_filter})"
            
            try:
                search_result = web_search(search_query, num_results=request.search_per_stock)
                search_data = json.loads(search_result) if isinstance(search_result, str) else search_result
                
                # Extract snippets from search results
                snippets = []
                if search_data.get("status") == "success":
                    for r in search_data.get("results", [])[:request.search_per_stock]:
                        snippets.append(f"- {r.get('title', '')}: {r.get('snippet', '')}")
                
                research_context = "\n".join(snippets) if snippets else "No research data found"
                
            except Exception as e:
                logger.warning(f"Search failed for {symbol}: {e}")
                research_context = "Search failed"
            
            research_results.append({
                "symbol": symbol,
                "price": price,
                "rank": rank,
                "research_context": research_context,
            })
        
        # Generate AI recommendations using Gemini
        stocks_summary = "\n\n".join([
            f"**{r['symbol']}** (₹{r['price']}, Rank: {r['rank']})\nResearch:\n{r['research_context']}"
            for r in research_results
        ])
        
        analysis_prompt = f"""You are a stock market analyst. Based on the research data below, provide investment recommendations.

## Stocks to Analyze:
{stocks_summary}

## Your Task:
For each stock, provide:
1. **Sentiment**: BULLISH / BEARISH / NEUTRAL
2. **Rationale**: 2-3 key points from the research
3. **Recommendation**: BUY / HOLD / SELL / AVOID
4. **Risk Level**: LOW / MEDIUM / HIGH

Finally, provide:
- **Top 3 Picks**: Best stocks to buy now with reasons
- **Stocks to Avoid**: Any stocks with red flags
- **Overall Market View**: Brief market sentiment

Format as clear markdown."""

        config = GeminiConfig(
            model_name=os.getenv("ADK_MODEL", "gemini-2.5-flash"),
            system_instruction="You are an expert Indian stock market analyst. Provide actionable recommendations.",
        )
        model = get_gemini_model(config)
        response = model.generate_content(analysis_prompt)
        
        return AgentResponse(
            status="success",
            result={
                "stocks_analyzed": len(research_results),
                "research_data": research_results,
                "ai_recommendations": response.text,
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tips research error: {e}")
        return AgentResponse(
            status="error",
            error=str(e),
        )


# ==================== LOAD DATA ====================

@app.get("/data/{filename}", response_model=AgentResponse)
async def get_data_file(filename: str):
    """Load a data file by name"""
    try:
        data_result = load_research_data(filename)
        results_data = json.loads(data_result)
        return AgentResponse(
            status=results_data.get("status", "success"),
            result=results_data,
        )
    except Exception as e:
        return AgentResponse(
            status="error",
            error=str(e),
        )


# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting API server on {host}:{port}")
    
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG_MODE", "false").lower() == "true",
    )
