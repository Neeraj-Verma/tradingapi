# Analysis Skill

## Overview
This skill enables agents to analyze data and generate insights with actionable recommendations.

## Capabilities

- Data loading and preprocessing
- Statistical analysis
- Pattern recognition
- Report generation in multiple formats

## Usage

```python
from tools.data_tool import load_research_data, analyze_data, generate_report

# Load data
data = load_research_data("research_data.json")

# Analyze
analysis = analyze_data(data, analysis_type="statistical")

# Generate report
report = generate_report(
    title="Market Analysis Report",
    sections=[
        {"heading": "Overview", "content": "..."},
        {"heading": "Key Findings", "content": "..."}
    ],
    output_format="markdown"
)
```

## Analysis Types

| Type | Description | Use Case |
|------|-------------|----------|
| summary | High-level overview | Quick insights |
| detailed | In-depth breakdown | Comprehensive analysis |
| statistical | Quantitative metrics | Data-driven decisions |

## Best Practices

1. **Data Quality**: Validate data before analysis
2. **Context**: Consider external factors affecting data
3. **Objectivity**: Let data drive conclusions
4. **Visualization**: Suggest appropriate charts
5. **Actionability**: Focus on actionable insights

## Output Formats

- **Markdown**: Formatted reports with headers and lists
- **JSON**: Structured data for programmatic use
