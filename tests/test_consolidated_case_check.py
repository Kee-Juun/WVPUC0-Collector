"""Test script for consolidated case detection and SF-View checking"""
import PyPDF2
import re
from pathlib import Path
from datetime import date
import json

# Test file
pdf_path = Path(r'C:\Users\libunak\Downloads\WVPUC0 Collections\WVPUC0_02-18-2026_01-11-54-PM\LDC_SMD_24-0900-PWD-C_02112026_E2E.pdf')
filename = pdf_path.name

# Extract case number and date from filename
# Format: LDC_SMD_{case_number}_{date}_E2E.pdf
# Case number format: XX-XXXX-XXX (e.g., 24-0900-PWD-C)
filename_match = re.match(r'LDC_SMD_(\d{2}-\d{4}-[A-Z0-9-]+)_(\d{8})_E2E\.pdf', filename, re.IGNORECASE)
if not filename_match:
    print(f"ERROR: Could not parse filename: {filename}")
    print(f"       Expected format: LDC_SMD_XX-XXXX-XXX_MMDDYYYY_E2E.pdf")
    exit(1)

filename_case = filename_match.group(1)  # 24-0900-PWD-C
filename_date = filename_match.group(2)   # 02112026

print("="*80)
print("CONSOLIDATED CASE DETECTION TEST")
print("="*80)
print(f"\nFilename: {filename}")
print(f"Filename case: {filename_case}")
print(f"Filename date: {filename_date}")

# Extract text from TOP of document (first page only - this is where case numbers appear)
reader = PyPDF2.PdfReader(str(pdf_path))
first_page_text = reader.pages[0].extract_text()

# Look for case numbers in the TOP section (first 2000 characters or first 50 lines)
top_section = first_page_text[:2000]  # First 2000 chars should cover the header
top_lines = top_section.split('\n')[:50]  # First 50 lines
top_text = '\n'.join(top_lines)

print(f"\n--- Top section of document (first 2000 chars / 50 lines) ---")
print(top_text[:1000])
print("...")

# Find all case numbers in top section
case_pattern = r'\b\d{2}-\d{4}-[A-Z0-9-]+\b'
top_cases = set(re.findall(case_pattern, top_text, re.IGNORECASE))

print(f"\n--- Case numbers found in TOP section ---")
for case in sorted(top_cases):
    marker = " (FILENAME CASE)" if case.upper() == filename_case.upper() else " (CONSOLIDATED)"
    print(f"  - {case}{marker}")

# Determine if this is a consolidated case
other_cases = [c for c in top_cases if c.upper() != filename_case.upper()]

if not other_cases:
    print(f"\n[OK] Single case document - NOT consolidated")
    print(f"     No action needed.")
else:
    print(f"\n[!] CONSOLIDATED CASE DETECTED!")
    print(f"     Found {len(other_cases)} other case(s) at the top:")
    for case in sorted(other_cases):
        print(f"       - {case}")
    
    # Now check SF-View for each other case
    print(f"\n--- Checking SF-View for other consolidated cases ---")
    
    # Load config
    config_path = Path(__file__).parent / 'config.json'
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    sf_view_url = config.get('sf_view_url', '')
    if sf_view_url.startswith('file://'):
        sf_view_path = Path(sf_view_url.replace('file://', ''))
    else:
        sf_view_path = Path(sf_view_url)
    
    print(f"SF-View path: {sf_view_path}")
    print(f"SF-View exists: {sf_view_path.exists()}")
    
    if not sf_view_path.exists():
        print(f"\n[WARNING] SF-View path does not exist - cannot check for duplicates")
        print(f"          Would keep file: {filename}")
    else:
        # Check each other case
        found_in_sfview = []
        not_found_in_sfview = []
        
        for other_case in sorted(other_cases):
            # Construct expected filename for the other case
            # Format: LDC_SMD_{case_number}_{date}_E2E.pdf
            expected_filename = f"LDC_SMD_{other_case}_{filename_date}_E2E.pdf"
            
            print(f"\n  Checking for: {expected_filename}")
            
            # Check if file exists in SF-View
            possible_patterns = [
                f'*{other_case}*.pdf',
                f'LDC_SMD_{other_case}_*.pdf',
                expected_filename
            ]
            
            found = False
            for pattern in possible_patterns:
                matching_files = list(sf_view_path.glob(pattern))
                if matching_files:
                    print(f"    [FOUND] {matching_files[0].name}")
                    found_in_sfview.append((other_case, matching_files[0].name))
                    found = True
                    break
            
            if not found:
                print(f"    [NOT FOUND]")
                not_found_in_sfview.append(other_case)
        
        # Decision logic
        print(f"\n--- DECISION ---")
        if found_in_sfview:
            print(f"[DELETE] File should be DELETED because:")
            for case, existing_file in found_in_sfview:
                print(f"         - Case {case} already exists in SF-View as: {existing_file}")
            print(f"\n         Action: DELETE {filename}")
        elif not_found_in_sfview:
            print(f"[KEEP] File should be KEPT because:")
            for case in not_found_in_sfview:
                print(f"        - Case {case} NOT found in SF-View")
            print(f"\n        Action: KEEP {filename}")
        else:
            print(f"[KEEP] No other cases found to check")
            print(f"       Action: KEEP {filename}")

print("\n" + "="*80)

