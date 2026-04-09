"""
Research Agent - ADK Agent for web research and information gathering
Uses Gemini for intelligent research synthesis
"""

import os
from pathlib import Path
from typing import Dict, Any

from google.adk.agents import Agent

# Import tools
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.search_tool import web_search, get_webpage_content
from tools.data_tool import save_research_data, load_research_data


# Load system prompt
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "system_prompts" / "research_agent.md").read_text(encoding="utf-8")


# Create the ADK Agent
research_agent = Agent(
    name="research_agent",
    model=os.getenv("ADK_MODEL", "gemini-2.0-flash"),
    description="Research agent that searches the web and synthesizes information",
    instruction=SYSTEM_PROMPT,
    tools=[
        web_search,
        get_webpage_content,
        save_research_data,
        load_research_data,
    ],
)


# For programmatic use
def run_research(query: str) -> Dict[str, Any]:
    """
    Run research on a query
    
    Args:
        query: Research query/topic
        
    Returns:
        Dict with research results
    """
    # This would be called via ADK runner
    # adk run research_agent
    return {
        "agent": "research_agent",
        "query": query,
        "status": "Use 'adk run research_agent' to start"
    }


if __name__ == "__main__":
    print(f"Research Agent: {research_agent.name}")
    print(f"Model: {research_agent.model}")
    print(f"Tools: {[t.__name__ for t in research_agent.tools]}")
