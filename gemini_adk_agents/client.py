"""
Gemini ADK Agents - Python Client SDK
Use this to call the deployed API from any machine

Usage:
    from client import GeminiAgentClient
    
    client = GeminiAgentClient("https://your-service-url.run.app")
    
    # Research
    result = client.research("AI trends 2024")
    
    # Chat
    response = client.chat("Hello!")
    
    # Analyze
    analysis = client.analyze({"data": [1, 2, 3]})
"""

import os
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import requests


@dataclass
class AgentResponse:
    """Response from agent API"""
    status: str
    result: Any = None
    error: Optional[str] = None
    timestamp: str = ""
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AgentResponse":
        return cls(
            status=data.get("status", "unknown"),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", ""),
        )


class GeminiAgentClient:
    """
    Client for Gemini ADK Agents API
    
    Example:
        client = GeminiAgentClient("https://gemini-adk-agents-xxx.run.app")
        result = client.research("stock market trends")
        print(result.result)
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        identity_token: Optional[str] = None,
        timeout: int = 60,
    ):
        """
        Initialize client
        
        Args:
            base_url: Service URL (e.g., https://gemini-adk-agents-xxx.run.app)
            api_key: Optional API key for authentication
            identity_token: Optional GCP identity token for IAM auth
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.identity_token = identity_token
        self.timeout = timeout
        self._session = requests.Session()
    
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers"""
        headers = {"Content-Type": "application/json"}
        
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        if self.identity_token:
            headers["Authorization"] = f"Bearer {self.identity_token}"
        
        return headers
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
    ) -> AgentResponse:
        """Make HTTP request"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = self._session.get(
                    url,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                )
            else:
                response = self._session.post(
                    url,
                    headers=self._get_headers(),
                    json=data,
                    timeout=self.timeout,
                )
            
            response.raise_for_status()
            return AgentResponse.from_dict(response.json())
            
        except requests.exceptions.Timeout:
            return AgentResponse(status="error", error="Request timed out")
        except requests.exceptions.HTTPError as e:
            return AgentResponse(status="error", error=f"HTTP error: {e}")
        except Exception as e:
            return AgentResponse(status="error", error=str(e))
    
    # ==================== API METHODS ====================
    
    def health(self) -> Dict[str, Any]:
        """Check service health"""
        response = self._request("GET", "/health")
        if response.status == "error":
            return {"status": "error", "error": response.error}
        return response.result if response.result else {"status": response.status}
    
    def research(
        self,
        query: str,
        num_results: int = 10,
        save_results: bool = True,
    ) -> AgentResponse:
        """
        Run research agent
        
        Args:
            query: Research topic or question
            num_results: Number of search results to fetch
            save_results: Whether to save results to file
            
        Returns:
            AgentResponse with research results
        """
        return self._request("POST", "/research", {
            "query": query,
            "num_results": num_results,
            "save_results": save_results,
        })
    
    def analyze(
        self,
        data: Dict[str, Any],
        analysis_type: str = "summary",
    ) -> AgentResponse:
        """
        Run analysis agent
        
        Args:
            data: Data to analyze
            analysis_type: Type of analysis (summary, detailed, statistical)
            
        Returns:
            AgentResponse with analysis results
        """
        return self._request("POST", "/analyze", {
            "data": data,
            "analysis_type": analysis_type,
        })
    
    def generate_report(
        self,
        title: str,
        sections: List[Dict[str, str]],
        output_format: str = "markdown",
    ) -> AgentResponse:
        """
        Generate a report
        
        Args:
            title: Report title
            sections: List of {heading, content} dicts
            output_format: Output format (markdown or json)
            
        Returns:
            AgentResponse with report
        """
        return self._request("POST", "/report", {
            "title": title,
            "sections": sections,
            "output_format": output_format,
        })
    
    def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        use_vertex: bool = False,
    ) -> AgentResponse:
        """
        Chat with Gemini
        
        Args:
            message: User message
            system_prompt: Optional system instruction
            model: Model to use
            use_vertex: Use Vertex AI instead of direct API
            
        Returns:
            AgentResponse with chat response
        """
        return self._request("POST", "/chat", {
            "message": message,
            "system_prompt": system_prompt,
            "model": model,
            "use_vertex": use_vertex,
        })
    
    def get_data(self, filename: str) -> AgentResponse:
        """
        Get a data file
        
        Args:
            filename: Name of the file to retrieve
            
        Returns:
            AgentResponse with file data
        """
        return self._request("GET", f"/data/{filename}")


# ==================== CONVENIENCE FUNCTIONS ====================

def create_client(
    url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> GeminiAgentClient:
    """
    Create a client with environment defaults
    
    Uses GEMINI_AGENT_URL and GEMINI_AGENT_API_KEY env vars if not provided
    """
    base_url = url or os.getenv("GEMINI_AGENT_URL")
    key = api_key or os.getenv("GEMINI_AGENT_API_KEY")
    
    if not base_url:
        raise ValueError("base_url required. Set GEMINI_AGENT_URL env var or pass url parameter")
    
    return GeminiAgentClient(base_url, api_key=key)


# ==================== CLI ====================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Gemini ADK Agents Client")
    parser.add_argument("--url", required=True, help="Service URL")
    parser.add_argument("--action", choices=["health", "research", "chat"], default="health")
    parser.add_argument("--query", help="Query for research or chat")
    
    args = parser.parse_args()
    
    client = GeminiAgentClient(args.url)
    
    if args.action == "health":
        print(json.dumps(client.health(), indent=2))
    
    elif args.action == "research":
        if not args.query:
            print("--query required for research")
        else:
            result = client.research(args.query)
            print(f"Status: {result.status}")
            print(json.dumps(result.result, indent=2))
    
    elif args.action == "chat":
        if not args.query:
            print("--query required for chat")
        else:
            result = client.chat(args.query)
            print(f"Status: {result.status}")
            if result.result:
                print(f"Response: {result.result.get('response', '')}")
