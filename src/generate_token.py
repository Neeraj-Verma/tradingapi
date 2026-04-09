"""
Generate Access Token for Kite Connect API
Run this first to get your access token
"""

import os
from dotenv import load_dotenv
from kiteconnect import KiteConnect
import webbrowser

# Load environment variables from .env
load_dotenv()

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

def main():
    kite = KiteConnect(api_key=API_KEY)
    
    # Step 1: Get login URL
    login_url = kite.login_url()
    print("=" * 60)
    print("KITE CONNECT - ACCESS TOKEN GENERATOR")
    print("=" * 60)
    print(f"\n1. Opening login URL in browser...")
    print(f"   {login_url}\n")
    
    webbrowser.open(login_url)
    
    # Step 2: After login, you'll be redirected to your redirect URL with request_token
    print("2. After logging in, you'll be redirected to a URL like:")
    print("   https://your-redirect-url.com/?request_token=XXXXXXXX&action=login\n")
    
    request_token = input("3. Enter the request_token from the URL: ").strip()
    
    if not request_token:
        print("No token provided. Exiting.")
        return
    
    # Step 3: Generate access token
    try:
        data = kite.generate_session(request_token, api_secret=API_SECRET)
        access_token = data["access_token"]
        
        # Save to .env file
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        with open(env_path, 'r') as f:
            content = f.read()
        
        if 'ACCESS_TOKEN=' in content:
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('ACCESS_TOKEN='):
                    lines[i] = f'ACCESS_TOKEN={access_token}'
            content = '\n'.join(lines)
        else:
            content += f'\nACCESS_TOKEN={access_token}'
        
        with open(env_path, 'w') as f:
            f.write(content)
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS!")
        print("=" * 60)
        print(f"\nAccess Token saved to .env file!")
        print("You can now run: python sell_negative_stocks.py")
        print("Note: Access token is valid for one trading day only")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error generating access token: {e}")


if __name__ == "__main__":
    main()
