# Research Skill

## Overview
This skill enables agents to conduct comprehensive web research and synthesize information from multiple sources.

## Capabilities

- Web search across multiple search engines
- Webpage content extraction
- Source verification and cross-referencing
- Information synthesis and summarization

## Usage

```python
from tools.search_tool import web_search, get_webpage_content

# Search for information
results = web_search("stock market trends 2024", num_results=10)

# Get detailed content from a specific page
content = get_webpage_content("https://example.com/article")
```

## Best Practices

1. **Multiple Queries**: Use 3-5 different search queries for comprehensive coverage
2. **Source Diversity**: Include sources from different domains
3. **Recency**: Prioritize recent information for time-sensitive topics
4. **Verification**: Cross-reference key facts across multiple sources
5. **Attribution**: Always note the source of information

## Limitations

- Cannot access paywalled content
- May not have real-time data
- Search results depend on API availability
