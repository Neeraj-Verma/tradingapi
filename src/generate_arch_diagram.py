"""
Generate architecture diagram PNG from Mermaid markup using kroki.io API
"""
import base64
import urllib.request
import zlib

MERMAID_DIAGRAM = """flowchart TB
    subgraph CLI["Command Line Interface"]
        START[Start] --> ARGS{Parse Args}
        ARGS -->|--protect| PROT
        ARGS -->|--new-stocks| NEWSTK
        ARGS -->|--update-prices| UPDP
        ARGS -->|default| TRANCHE
    end

    subgraph PROT["--protect Flow"]
        P1{--sliced?}
        P2{--refresh?}
        P3[get_existing_gtts]
        P4[delete_existing_gtts]
        P5[protect_existing_holdings]
        P6[protect_existing_holdings_sliced]
        P7[Trailing Stop Logic]
        P8[place_gtt_oco]
        
        PROT --> P1
        P1 -->|No| P2
        P1 -->|Yes| P2
        P2 -->|Yes| P4
        P2 -->|No| P3
        P4 --> P3
        P3 --> P1
        P1 -->|No| P5
        P1 -->|Yes| P6
        P5 --> P7
        P6 --> P7
        P7 -->|LTP > Target| P8
    end

    subgraph NEWSTK["--new-stocks Flow"]
        N1[find_new_stocks]
        N2[Compare Holdings vs Research]
        N3[get_todays_buy_orders]
        N4[buy_new_stocks]
        N5[Place MARKET Orders]
        
        NEWSTK --> N1
        N1 --> N2
        N2 -->|New Symbols| N3
        N3 -->|Skip Duplicates| N4
        N4 --> N5
    end

    subgraph TRANCHE["Default Tranche Flow"]
        T1[Validate Credentials]
        T2{Market Hours?}
        T3[Read order_book.csv]
        T4[initialize_tracker_from_orders]
        T5[run_base_price_orders]
        T6[run_tranche_orders x5]
        T7[Budget Calculation]
        
        TRANCHE --> T1
        T1 --> T2
        T2 -->|Open| T3
        T3 --> T4
        T4 --> T5
        T5 --> T6
        T6 --> T7
    end

    subgraph DATA["Data Sources"]
        D1[(order_book.csv)]
        D2[(research_data.csv)]
        D3[(Kite Holdings)]
        D4[(Kite GTT API)]
    end

    subgraph GTT["GTT Order Types"]
        G1["Single OCO\\n-10% SL / +20% Target"]
        G2["Sliced OCO\\n3 GTTs per stock"]
        G3["Trailing Stop\\nSL/Target from LTP"]
    end

    D2 --> N1
    D3 --> N2
    D1 --> T3
    D3 --> P5
    D4 --> P3

    P5 --> G1
    P6 --> G2
    P7 --> G3

    style CLI fill:#e1f5fe
    style PROT fill:#fff3e0
    style NEWSTK fill:#e8f5e9
    style TRANCHE fill:#fce4ec
    style DATA fill:#f3e5f5
    style GTT fill:#fff8e1
"""


def generate_mermaid_png(diagram: str, output_file: str = "architecture.png"):
    """
    Generate PNG from Mermaid diagram using kroki.io service.
    """
    # Compress with zlib deflate
    compressed = zlib.compress(diagram.encode('utf-8'), level=9)
    
    # Base64 encode (URL safe)
    encoded = base64.urlsafe_b64encode(compressed).decode('ascii')
    
    # Build kroki URL
    url = f"https://kroki.io/mermaid/png/{encoded}"
    
    print(f"Fetching diagram from kroki.io...")
    
    try:
        request = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'image/png'}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            image_data = response.read()
        
        with open(output_file, 'wb') as f:
            f.write(image_data)
        
        print(f"Saved architecture diagram to: {output_file}")
        print(f"File size: {len(image_data):,} bytes")
        return True
        
    except Exception as e:
        print(f"Error generating diagram: {e}")
        return False


if __name__ == "__main__":
    generate_mermaid_png(MERMAID_DIAGRAM, "architecture.png")
