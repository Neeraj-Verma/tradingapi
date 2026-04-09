"""
Analyst Agent - ADK Agent for data analysis and insights
Uses Gemini for intelligent analysis and recommendations
"""

import os
from pathlib import Path
from typing import Dict, Any

from google.adk.agents import Agent

# Import tools
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.data_tool import load_research_data, analyze_data, generate_report


# Load system prompt
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "system_prompts" / "analyst_agent.md").read_text(encoding="utf-8")


# Create the ADK Agent
analyst_agent = Agent(
    name="analyst_agent",
    model=os.getenv("ADK_MODEL", "gemini-2.0-flash"),
    description="Analysis agent that processes data and generates insights",
    instruction=SYSTEM_PROMPT,
    tools=[
        load_research_data,
        analyze_data,
        generate_report,
    ],
)


# For programmatic use
def run_analysis(data_file: str) -> Dict[str, Any]:
    """
    Run analysis on data
    
    Args:
        data_file: Path to data file
        
    Returns:
        Dict with analysis results
    """
    return {
        "agent": "analyst_agent",
        "data_file": data_file,
        "status": "Use 'adk run analyst_agent' to start"
    }


if __name__ == "__main__":
    print(f"Analyst Agent: {analyst_agent.name}")
    print(f"Model: {analyst_agent.model}")
    print(f"Tools: {[t.__name__ for t in analyst_agent.tools]}")
