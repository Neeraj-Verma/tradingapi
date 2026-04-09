"""
Vertex AI Configuration - Enterprise Gemini deployment
For production use with Google Cloud Platform
"""

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

try:
    from google.cloud import aiplatform
    from vertexai.generative_models import GenerativeModel, Part
    import vertexai
    VERTEX_AVAILABLE = True
except ImportError:
    VERTEX_AVAILABLE = False


@dataclass
class VertexConfig:
    """Configuration for Vertex AI models"""
    
    # GCP settings
    project_id: str = ""
    location: str = "us-central1"
    
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
    def from_env(cls) -> "VertexConfig":
        """Create config from environment variables"""
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            location=os.getenv("GCP_LOCATION", "us-central1"),
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


def init_vertex_ai(
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> bool:
    """
    Initialize Vertex AI SDK
    
    Args:
        project_id: GCP project ID (or uses GCP_PROJECT_ID env var)
        location: GCP region (or uses GCP_LOCATION env var)
        
    Returns:
        True if initialized successfully
    """
    if not VERTEX_AVAILABLE:
        raise ImportError(
            "Vertex AI packages not installed. Run:\n"
            "pip install google-cloud-aiplatform vertexai"
        )
    
    proj = project_id or os.getenv("GCP_PROJECT_ID")
    loc = location or os.getenv("GCP_LOCATION", "us-central1")
    
    if not proj:
        raise ValueError(
            "GCP_PROJECT_ID not found. Set it in .env or pass project_id parameter"
        )
    
    vertexai.init(project=proj, location=loc)
    return True


def get_vertex_model(
    config: Optional[VertexConfig] = None,
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> Any:
    """
    Get a configured Vertex AI Gemini model
    
    Args:
        config: VertexConfig instance (or uses defaults)
        project_id: GCP project ID
        location: GCP region
        
    Returns:
        Configured GenerativeModel instance
    """
    if not VERTEX_AVAILABLE:
        raise ImportError("Vertex AI packages not installed")
    
    if config is None:
        config = VertexConfig.from_env()
    
    proj = project_id or config.project_id
    loc = location or config.location
    
    init_vertex_ai(proj, loc)
    
    model_kwargs = {
        "model_name": config.model_name,
        "generation_config": config.to_generation_config(),
    }
    
    if config.system_instruction:
        model_kwargs["system_instruction"] = config.system_instruction
    
    if config.safety_settings:
        model_kwargs["safety_settings"] = config.safety_settings
    
    return GenerativeModel(**model_kwargs)


def list_vertex_models(
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> List[str]:
    """
    List available models in Vertex AI
    
    Args:
        project_id: GCP project ID
        location: GCP region
        
    Returns:
        List of model names
    """
    # Common Vertex AI Gemini models
    return [
        "gemini-2.0-flash",
        "gemini-2.0-pro", 
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash-002",
        "gemini-1.5-pro-002",
    ]


# Convenience functions for common use cases

def vertex_generate(
    prompt: str,
    model_name: str = "gemini-2.0-flash",
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> str:
    """
    Quick text generation with Vertex AI
    
    Args:
        prompt: The prompt text
        model_name: Model to use
        project_id: GCP project ID
        location: GCP region
        
    Returns:
        Generated text
    """
    if not VERTEX_AVAILABLE:
        raise ImportError("Vertex AI packages not installed")
    
    init_vertex_ai(project_id, location)
    model = GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return response.text


def vertex_chat_session(
    system_prompt: Optional[str] = None,
    model_name: str = "gemini-2.0-flash",
    project_id: Optional[str] = None,
    location: Optional[str] = None
) -> Any:
    """
    Start a chat session with Vertex AI
    
    Args:
        system_prompt: System instruction for the chat
        model_name: Model to use
        project_id: GCP project ID
        location: GCP region
        
    Returns:
        Chat session object
    """
    if not VERTEX_AVAILABLE:
        raise ImportError("Vertex AI packages not installed")
    
    init_vertex_ai(project_id, location)
    
    model_kwargs = {"model_name": model_name}
    if system_prompt:
        model_kwargs["system_instruction"] = system_prompt
    
    model = GenerativeModel(**model_kwargs)
    return model.start_chat()


def get_vertex_embedding_model(model_name: str = "text-embedding-004") -> Any:
    """
    Get Vertex AI embedding model
    
    Args:
        model_name: Embedding model name
        
    Returns:
        Embedding model instance
    """
    if not VERTEX_AVAILABLE:
        raise ImportError("Vertex AI packages not installed")
    
    from vertexai.language_models import TextEmbeddingModel
    return TextEmbeddingModel.from_pretrained(model_name)


if __name__ == "__main__":
    print("Available Vertex AI Models:")
    for model in list_vertex_models():
        print(f"  - {model}")
    
    print("\nTo use Vertex AI, ensure:")
    print("  1. GCP_PROJECT_ID is set in .env")
    print("  2. gcloud auth application-default login is run")
    print("  3. Vertex AI API is enabled in your GCP project")
