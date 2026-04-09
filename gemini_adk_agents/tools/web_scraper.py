"""
Web Scraper Tool - Advanced web scraping for ADK agents
Provides structured data extraction from web pages
"""

import os
import json
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ScrapedPage:
    """Scraped page data"""
    url: str
    title: str
    content: str
    links: List[str]
    metadata: Dict[str, Any]


def scrape_webpage(url: str, extract_links: bool = True) -> str:
    """
    Scrape a webpage and extract structured content.
    
    Args:
        url: The URL to scrape
        extract_links: Whether to extract links from the page
        
    Returns:
        JSON string with scraped content including title, text, and links
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        html = response.text
        
        # Extract title
        import re
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else "No title"
        
        # Extract links if requested
        links = []
        if extract_links:
            link_pattern = r'href=["\']([^"\']+)["\']'
            raw_links = re.findall(link_pattern, html, re.IGNORECASE)
            
            # Filter and normalize links
            base_domain = urlparse(url).netloc
            for link in raw_links[:50]:  # Limit to 50 links
                if link.startswith('http'):
                    links.append(link)
                elif link.startswith('/'):
                    links.append(f"https://{base_domain}{link}")
        
        # Extract text content
        # Remove script and style
        content = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', ' ', content)
        # Clean whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        
        # Truncate content
        if len(content) > 15000:
            content = content[:15000] + "... [truncated]"
        
        return json.dumps({
            "status": "success",
            "url": url,
            "title": title,
            "content_length": len(content),
            "content": content,
            "links_count": len(links),
            "links": links[:20]  # Return first 20 links
        }, indent=2)
        
    except requests.exceptions.Timeout:
        return json.dumps({
            "status": "error",
            "url": url,
            "message": "Request timed out"
        }, indent=2)
    except requests.exceptions.RequestException as e:
        return json.dumps({
            "status": "error",
            "url": url,
            "message": str(e)
        }, indent=2)


def scrape_multiple_pages(urls: List[str]) -> str:
    """
    Scrape multiple webpages.
    
    Args:
        urls: List of URLs to scrape
        
    Returns:
        JSON string with results for each URL
    """
    results = []
    
    for url in urls[:10]:  # Limit to 10 URLs
        try:
            result = json.loads(scrape_webpage(url, extract_links=False))
            results.append(result)
        except Exception as e:
            results.append({
                "status": "error",
                "url": url,
                "message": str(e)
            })
    
    return json.dumps({
        "status": "success",
        "total_urls": len(urls),
        "processed": len(results),
        "results": results
    }, indent=2)


def extract_tables(url: str) -> str:
    """
    Extract tables from a webpage.
    
    Args:
        url: The URL to extract tables from
        
    Returns:
        JSON string with extracted table data
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        html = response.text
        
        # Basic table extraction using regex (for production, use BeautifulSoup)
        import re
        tables = []
        
        table_pattern = r'<table[^>]*>(.*?)</table>'
        table_matches = re.findall(table_pattern, html, re.DOTALL | re.IGNORECASE)
        
        for i, table_html in enumerate(table_matches[:5]):  # Limit to 5 tables
            # Extract rows
            rows = []
            row_pattern = r'<tr[^>]*>(.*?)</tr>'
            row_matches = re.findall(row_pattern, table_html, re.DOTALL | re.IGNORECASE)
            
            for row_html in row_matches[:50]:  # Limit rows
                cells = []
                cell_pattern = r'<t[dh][^>]*>(.*?)</t[dh]>'
                cell_matches = re.findall(cell_pattern, row_html, re.DOTALL | re.IGNORECASE)
                
                for cell in cell_matches:
                    # Clean cell content
                    cell_text = re.sub(r'<[^>]+>', '', cell)
                    cell_text = re.sub(r'\s+', ' ', cell_text).strip()
                    cells.append(cell_text)
                
                if cells:
                    rows.append(cells)
            
            if rows:
                tables.append({
                    "table_index": i,
                    "rows_count": len(rows),
                    "rows": rows
                })
        
        return json.dumps({
            "status": "success",
            "url": url,
            "tables_found": len(tables),
            "tables": tables
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "status": "error",
            "url": url,
            "message": str(e)
        }, indent=2)


if __name__ == "__main__":
    # Test
    print("Testing scrape_webpage...")
    result = scrape_webpage("https://example.com")
    print(result[:500])
