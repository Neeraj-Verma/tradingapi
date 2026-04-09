# Gemini ADK Agents

A collection of AI agents built using Google's Agent Development Kit (ADK) with Gemini and Vertex AI.

## Project Structure

```
gemini_adk_agents/
├── agents/              # ADK agent definitions
│   ├── __init__.py
│   ├── base_agent.py    # Base agent class
│   ├── research_agent/  # Research agent
│   └── analyst_agent/   # Analysis agent
├── tools/               # Custom tools for agents
│   ├── __init__.py
│   ├── search_tool.py
│   ├── web_scraper.py
│   └── data_tool.py
├── prompts/             # Prompt templates
│   ├── system_prompts/
│   └── task_prompts/
├── skills/              # Agent skills with SKILL.md
│   ├── research/
│   └── analysis/
├── model_schemas/       # Pydantic/dataclass schemas
│   ├── __init__.py
│   └── schemas.py
├── llm/                 # LLM configurations (GCP/Vertex)
│   ├── __init__.py
│   ├── gemini_config.py
│   └── vertex_config.py
├── data/                # Data storage
│   ├── input/
│   ├── output/
│   └── cache/
├── .env.example         # Environment template
└── main.py              # Entry point
```

## Setup

1. Copy `.env.example` to `.env` and fill in your credentials
2. Install dependencies:
   ```bash
   pip install google-adk google-generativeai google-cloud-aiplatform
   ```

3. Authenticate with GCP:
   ```bash
   gcloud auth application-default login
   ```

## Running Agents

```bash
# Run with ADK CLI
adk run research_agent

# Or run directly
python main.py
```

## Models Supported

- **Gemini 2.0 Flash** - Fast, efficient for most tasks
- **Gemini 2.0 Pro** - Advanced reasoning
- **Vertex AI** - Enterprise deployment with additional features
