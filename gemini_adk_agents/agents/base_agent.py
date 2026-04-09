"""
Base Agent Class for Gemini ADK Agents
Provides common functionality for all agents
"""

import os
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path

from google.adk.agents import Agent
from google.adk.tools import Tool


@dataclass
class AgentConfig:
    """Configuration for Gemini ADK Agent"""
    name: str
    model: str = "gemini-2.0-flash"
    description: str = ""
    instruction: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 8192
    tools: List[Callable] = field(default_factory=list)
    sub_agents: List[Any] = field(default_factory=list)
    
    @classmethod
    def from_env(cls, name: str, **kwargs) -> "AgentConfig":
        """Create config from environment variables"""
        return cls(
            name=name,
            model=os.getenv("ADK_MODEL", "gemini-2.0-flash"),
            temperature=float(os.getenv("ADK_TEMPERATURE", "0.7")),
            max_output_tokens=int(os.getenv("ADK_MAX_OUTPUT_TOKENS", "8192")),
            **kwargs
        )


class BaseGeminiAgent:
    """
    Base class for building Gemini ADK agents
    
    Usage:
        class MyAgent(BaseGeminiAgent):
            def __init__(self):
                config = AgentConfig(
                    name="my_agent",
                    description="My custom agent",
                    instruction="You are a helpful assistant..."
                )
                super().__init__(config)
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self._agent: Optional[Agent] = None
    
    @property
    def agent(self) -> Agent:
        """Get or create the ADK Agent instance"""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent
    
    def _create_agent(self) -> Agent:
        """Create the ADK Agent with configuration"""
        agent_kwargs = {
            "name": self.config.name,
            "model": self.config.model,
            "description": self.config.description,
            "instruction": self.config.instruction,
        }
        
        if self.config.tools:
            agent_kwargs["tools"] = self.config.tools
        
        if self.config.sub_agents:
            agent_kwargs["sub_agents"] = self.config.sub_agents
        
        return Agent(**agent_kwargs)
    
    def add_tool(self, tool: Callable) -> None:
        """Add a tool to the agent"""
        self.config.tools.append(tool)
        self._agent = None  # Reset to recreate with new tool
    
    def add_sub_agent(self, sub_agent: Any) -> None:
        """Add a sub-agent"""
        self.config.sub_agents.append(sub_agent)
        self._agent = None
    
    def get_agent(self) -> Agent:
        """Get the underlying ADK Agent for use with adk run"""
        return self.agent
