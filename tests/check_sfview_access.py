"""Quick script to check if SF-View path is accessible"""
import json
from pathlib import Path

config_path = Path(__file__).parent / 'config.json'
with open(config_path, 'r') as f:
    config = json.load(f)

sf_view_url = config.get('sf_view_url', '')
print(f"SF-View URL from config: {sf_view_url}")

# Handle file:// URLs - convert to UNC format for Windows network paths
if sf_view_url.startswith('file://'):
    path_str = sf_view_url.replace('file://', '')
    path_str = path_str.replace('/', '\\')
    # If it's a network path, ensure it starts with \\
    if not path_str.startswith('\\\\') and '\\' in path_str and not path_str[1:2] == ':':
        path_str = '\\\\' + path_str.lstrip('\\')
    sf_view_path = Path(path_str)
else:
    sf_view_path = Path(sf_view_url)

print(f"SF-View path: {sf_view_path}")
print(f"Path exists: {sf_view_path.exists()}")

if sf_view_path.exists():
    print(f"Path is directory: {sf_view_path.is_dir()}")
    try:
        pdf_count = len(list(sf_view_path.glob('*.pdf')))
        print(f"PDF files found in SF-View: {pdf_count}")
        if pdf_count > 0:
            sample_files = list(sf_view_path.glob('*.pdf'))[:5]
            print(f"Sample files:")
            for f in sample_files:
                print(f"  - {f.name}")
    except Exception as e:
        print(f"Error accessing SF-View: {e}")
else:
    print("\n[WARNING] SF-View path does not exist or is not accessible!")
    print("          The test script will report 'NOT FOUND' for all cases")
    print("          because it cannot access the SF-View directory.")

