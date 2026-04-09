"""
Gemini Configuration - Direct Gemini API access
For use cases that don't require Vertex AI features
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


@dataclass
class GeminiConfig:
    """Configuration for Gemini models"""
    
    # Model selection
    model_name: str = "gemini-2.0-flash"
    
    # Generation parameters
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 8192
    
    # Safety settings
    safety_settings: Optional[Dict[str, str]] = None
    
    # System instruction
    system_instruction: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "GeminiConfig":
        """Create config from environment variables"""
        return cls(
            model_name=os.getenv("ADK_MODEL", "gemini-2.0-flash"),
            temperature=float(os.getenv("ADK_TEMPERATURE", "0.7")),
            max_output_tokens=int(os.getenv("ADK_MAX_OUTPUT_TOKENS", "8192")),
        )
    
    def to_generation_config(self) -> Dict[str, Any]:
        """Convert to generation config dict"""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens,
        }


def configure_gemini(api_key: Optional[str] = None) -> bool:
    """
    Configure Gemini API with API key
    
    Args:
        api_key: Google API key (or uses GOOGLE_API_KEY env var)
        
    Returns:
        True if configured successfully
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
    
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GOOGLE_API_KEY not found. Set it in .env or pass api_key parameter")
    
    genai.configure(api_key=key)
    return True


def get_gemini_model(
    config: Optional[GeminiConfig] = None,
    api_key: Optional[str] = None
) -> Any:
    """
    Get a configured Gemini model instance
    
    Args:
        config: GeminiConfig instance (or uses defaults)
        api_key: API key (or uses env var)
        
    Returns:
        Configured GenerativeModel instance
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-generativeai package not installed")
    
    configure_gemini(api_key)
    
    if config is None:
        config = GeminiConfig.from_env()
    
    model_kwargs = {
        "model_name": config.model_name,
        "generation_config": config.to_generation_config(),
    }
    
    if config.system_instruction:
        model_kwargs["system_instruction"] = config.system_instruction
    
    if config.safety_settings:
        model_kwargs["safety_settings"] = config.safety_settings
    
    return genai.GenerativeModel(**model_kwargs)


def list_available_models() -> List[str]:
    """List available Gemini models"""
    if not GENAI_AVAILABLE:
        return []
    
    try:
        configure_gemini()
        models = genai.list_models()
        return [m.name for m in models if "gemini" in m.name.lower()]
    except Exception:
        return [
            "models/gemini-2.0-flash",
            "models/gemini-2.0-pro",
            "models/gemini-1.5-flash",
            "models/gemini-1.5-pro",
        ]


# Convenience functions for common use cases

def quick_generate(prompt: str, model_name: str = "gemini-2.0-flash") -> str:
    """
    Quick text generation with Gemini
    
    Args:
        prompt: The prompt text
        model_name: Model to use
        
    Returns:
        Generated text
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-generativeai package not installed")
    
    configure_gemini()
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text


def chat_session(
    system_prompt: Optional[str] = None,
    model_name: str = "gemini-2.0-flash"
) -> Any:
    """
    Start a chat session with Gemini
    
    Args:
        system_prompt: System instruction for the chat
        model_name: Model to use
        
    Returns:
        Chat session object
    """
    if not GENAI_AVAILABLE:
        raise ImportError("google-generativeai package not installed")
    
    configure_gemini()
    
    model_kwargs = {"model_name": model_name}
    if system_prompt:
        model_kwargs["system_instruction"] = system_prompt
    
    model = genai.GenerativeModel(**model_kwargs)
    return model.start_chat()


if __name__ == "__main__":
    print("Available Gemini Models:")
    for model in list_available_models():
        print(f"  - {model}")
