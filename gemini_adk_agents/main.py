"""
Gemini ADK Agents - Main Entry Point
Run agents using Google ADK with Gemini/Vertex AI
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment
load_dotenv(PROJECT_ROOT / ".env")

from agents.research_agent import research_agent
from agents.analyst_agent import analyst_agent


def main():
    """Main entry point for running agents"""
    print("=" * 50)
    print("Gemini ADK Agents")
    print("=" * 50)
    
    # List available agents
    agents = {
        "1": ("Research Agent", research_agent),
        "2": ("Analyst Agent", analyst_agent),
    }
    
    print("\nAvailable Agents:")
    for key, (name, _) in agents.items():
        print(f"  {key}. {name}")
    
    print("\nTo run agents via ADK CLI:")
    print("  adk run research_agent")
    print("  adk run analyst_agent")
    
    print("\nOr import and use programmatically:")
    print("  from agents.research_agent import research_agent")


if __name__ == "__main__":
    main()
