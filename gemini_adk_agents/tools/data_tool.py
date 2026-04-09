"""
Data Tool - Data manipulation and storage for ADK agents
Handles research data, analysis, and report generation
"""

import os
import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


# Data directory
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def save_research_data(data: Dict[str, Any], filename: str = "research_data.json") -> str:
    """
    Save research data to a JSON file.
    
    Args:
        data: Dictionary containing research data to save
        filename: Name of the output file (default: research_data.json)
        
    Returns:
        JSON string with status and file path
    """
    try:
        output_dir = DATA_DIR / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = output_dir / filename
        
        # Add metadata
        data_with_meta = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "filename": filename
            },
            "data": data
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_with_meta, f, indent=2, ensure_ascii=False)
        
        return json.dumps({
            "status": "success",
            "message": f"Data saved successfully",
            "filepath": str(filepath),
            "size_bytes": filepath.stat().st_size
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, indent=2)


def load_research_data(filename: str = "research_data.json") -> str:
    """
    Load research data from a JSON file.
    
    Args:
        filename: Name of the file to load
        
    Returns:
        JSON string with the loaded data or error message
    """
    try:
        # Try output directory first
        filepath = DATA_DIR / "output" / filename
        if not filepath.exists():
            # Try input directory
            filepath = DATA_DIR / "input" / filename
        if not filepath.exists():
            # Try data directory root
            filepath = DATA_DIR / filename
        
        if not filepath.exists():
            return json.dumps({
                "status": "error",
                "message": f"File not found: {filename}",
                "searched_paths": [
                    str(DATA_DIR / "output" / filename),
                    str(DATA_DIR / "input" / filename),
                    str(DATA_DIR / filename)
                ]
            }, indent=2)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return json.dumps({
            "status": "success",
            "filepath": str(filepath),
            "data": data
        }, indent=2)
        
    except json.JSONDecodeError as e:
        return json.dumps({
            "status": "error",
            "message": f"Invalid JSON: {str(e)}"
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, indent=2)


def analyze_data(data: Dict[str, Any], analysis_type: str = "summary") -> str:
    """
    Analyze data and return insights.
    
    Args:
        data: Dictionary containing data to analyze
        analysis_type: Type of analysis (summary, detailed, statistical)
        
    Returns:
        JSON string with analysis results
    """
    try:
        analysis = {
            "analysis_type": analysis_type,
            "timestamp": datetime.now().isoformat(),
            "data_overview": {}
        }
        
        # Basic data overview
        if isinstance(data, dict):
            analysis["data_overview"] = {
                "type": "dictionary",
                "keys": list(data.keys())[:20],
                "total_keys": len(data)
            }
            
            # Count nested items
            for key, value in list(data.items())[:10]:
                if isinstance(value, list):
                    analysis["data_overview"][f"{key}_count"] = len(value)
                elif isinstance(value, dict):
                    analysis["data_overview"][f"{key}_keys"] = len(value)
        
        elif isinstance(data, list):
            analysis["data_overview"] = {
                "type": "list",
                "length": len(data),
                "sample": data[:3] if len(data) > 0 else []
            }
        
        # Statistical analysis for numerical data
        if analysis_type == "statistical":
            numbers = []
            
            def extract_numbers(obj):
                if isinstance(obj, (int, float)):
                    numbers.append(obj)
                elif isinstance(obj, dict):
                    for v in obj.values():
                        extract_numbers(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_numbers(item)
            
            extract_numbers(data)
            
            if numbers:
                analysis["statistics"] = {
                    "count": len(numbers),
                    "sum": sum(numbers),
                    "min": min(numbers),
                    "max": max(numbers),
                    "mean": sum(numbers) / len(numbers)
                }
        
        return json.dumps({
            "status": "success",
            "analysis": analysis
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, indent=2)


def generate_report(
    title: str,
    sections: List[Dict[str, str]],
    output_format: str = "markdown"
) -> str:
    """
    Generate a formatted report.
    
    Args:
        title: Report title
        sections: List of sections, each with 'heading' and 'content' keys
        output_format: Output format (markdown or json)
        
    Returns:
        JSON string with the generated report and file path
    """
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if output_format == "markdown":
            # Generate Markdown report
            report_lines = [
                f"# {title}",
                f"",
                f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
                f"",
                "---",
                ""
            ]
            
            for section in sections:
                heading = section.get("heading", "Section")
                content = section.get("content", "")
                
                report_lines.append(f"## {heading}")
                report_lines.append("")
                report_lines.append(content)
                report_lines.append("")
            
            report_content = "\n".join(report_lines)
            
            # Save report
            output_dir = DATA_DIR / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            safe_title = "".join(c if c.isalnum() or c in "- _" else "_" for c in title)
            filename = f"report_{safe_title}_{timestamp}.md"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            return json.dumps({
                "status": "success",
                "format": "markdown",
                "filepath": str(filepath),
                "content_preview": report_content[:500] + "..." if len(report_content) > 500 else report_content
            }, indent=2)
        
        else:
            # Generate JSON report
            report = {
                "title": title,
                "generated_at": datetime.now().isoformat(),
                "sections": sections
            }
            
            output_dir = DATA_DIR / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            safe_title = "".join(c if c.isalnum() or c in "- _" else "_" for c in title)
            filename = f"report_{safe_title}_{timestamp}.json"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            return json.dumps({
                "status": "success",
                "format": "json",
                "filepath": str(filepath),
                "report": report
            }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, indent=2)


def list_data_files(directory: str = "output") -> str:
    """
    List all data files in a directory.
    
    Args:
        directory: Subdirectory to list (input, output, or cache)
        
    Returns:
        JSON string with list of files
    """
    try:
        target_dir = DATA_DIR / directory
        
        if not target_dir.exists():
            return json.dumps({
                "status": "success",
                "directory": str(target_dir),
                "files": [],
                "message": "Directory is empty or does not exist"
            }, indent=2)
        
        files = []
        for f in target_dir.iterdir():
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })
        
        return json.dumps({
            "status": "success",
            "directory": str(target_dir),
            "file_count": len(files),
            "files": sorted(files, key=lambda x: x["modified"], reverse=True)
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e)
        }, indent=2)


if __name__ == "__main__":
    # Test
    print("Testing save_research_data...")
    result = save_research_data({"test": "data", "items": [1, 2, 3]}, "test_data.json")
    print(result)
    
    print("\nTesting load_research_data...")
    result = load_research_data("test_data.json")
    print(result)
