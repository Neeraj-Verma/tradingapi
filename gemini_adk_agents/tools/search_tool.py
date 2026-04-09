"""
Search Tool - Web search functionality for ADK agents
Supports multiple search backends (Serper, Tavily, etc.)
"""

import os
import json
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class SearchResult:
    """Search result data class"""
    title: str
    url: str
    snippet: str
    source: str = ""


def web_search(query: str, num_results: int = 10) -> str:
    """
    Search the web for information.
    
    Args:
        query: The search query string
        num_results: Number of results to return (default: 10)
        
    Returns:
        JSON string with search results containing title, url, and snippet for each result
    """
    # Try Serper API first
    serper_key = os.getenv("SERPER_API_KEY")
    if serper_key:
        return _serper_search(query, num_results, serper_key)
    
    # Try Tavily API
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        return _tavily_search(query, num_results, tavily_key)
    
    # Fallback: Return mock data for development
    return json.dumps({
        "status": "mock",
        "message": "No search API configured. Set SERPER_API_KEY or TAVILY_API_KEY in .env",
        "query": query,
        "results": [
            {
                "title": f"Mock result for: {query}",
                "url": "https://example.com",
                "snippet": "This is a mock search result. Configure a search API for real results."
            }
        ]
    }, indent=2)


def _serper_search(query: str, num_results: int, api_key: str) -> str:
    """Search using Serper API"""
    try:
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": query,
            "num": num_results
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        for item in data.get("organic", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "serper"
            })
        
        return json.dumps({
            "status": "success",
            "query": query,
            "results": results
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "query": query
        }, indent=2)


def _tavily_search(query: str, num_results: int, api_key: str) -> str:
    """Search using Tavily API"""
    try:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": num_results,
            "include_answer": True
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        results = []
        
        for item in data.get("results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "source": "tavily"
            })
        
        return json.dumps({
            "status": "success",
            "query": query,
            "answer": data.get("answer", ""),
            "results": results
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "query": query
        }, indent=2)


def get_webpage_content(url: str, max_chars: int = 10000) -> str:
    """
    Fetch and extract text content from a webpage.
    
    Args:
        url: The URL to fetch
        max_chars: Maximum characters to return (default: 10000)
        
    Returns:
        JSON string with the webpage content and metadata
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Try to extract text (basic implementation)
        content = response.text
        
        # Basic HTML tag removal (for production, use BeautifulSoup)
        import re
        # Remove script and style elements
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', ' ', content)
        # Clean up whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        
        # Truncate if needed
        if len(content) > max_chars:
            content = content[:max_chars] + "... [truncated]"
        
        return json.dumps({
            "status": "success",
            "url": url,
            "content_length": len(content),
            "content": content
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "url": url,
            "message": str(e)
        }, indent=2)


if __name__ == "__main__":
    # Test the tools
    print("Testing web_search...")
    result = web_search("Python programming best practices", 5)
    print(result)
