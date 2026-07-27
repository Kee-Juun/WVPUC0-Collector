"""Test script to extract case numbers from a PDF"""
import PyPDF2
import re
from pathlib import Path

pdf_path = Path(r'C:\Users\libunak\Downloads\WVPUC0 Collections\WVPUC0_02-18-2026_01-11-54-PM\LDC_SMD_24-0900-PWD-C_02112026_E2E.pdf')

# Extract text from PDF
reader = PyPDF2.PdfReader(str(pdf_path))
text = ''
for page in reader.pages:
    text += page.extract_text() + '\n'

# Find all case numbers using the pattern: XX-XXXX-XXX format
case_pattern = r'\b\d{2}-\d{4}-[A-Z0-9-]+\b'
cases = set(re.findall(case_pattern, text, re.IGNORECASE))

print("="*80)
print("CASE NUMBER ANALYSIS")
print("="*80)
print(f"\nFilename case: 24-0900-PWD-C")
print(f"\nTotal unique case numbers found in PDF: {len(cases)}")
print(f"\nAll case numbers found:")
for case in sorted(cases):
    marker = " (FILENAME CASE)" if case.upper() == "24-0900-PWD-C" else " (CONSOLIDATED)"
    print(f"  - {case}{marker}")

other_cases = [c for c in cases if c.upper() != "24-0900-PWD-C"]
if other_cases:
    print(f"\n[!] CONSOLIDATED CASE DETECTED!")
    print(f"   This document contains {len(other_cases)} other case(s):")
    for case in sorted(other_cases):
        print(f"   - {case}")
else:
    print(f"\n[OK] Single case document (no consolidation detected)")

# Show context where other cases appear
if other_cases:
    print(f"\n" + "="*80)
    print("CONTEXT: Where other cases are mentioned")
    print("="*80)
    for case in sorted(other_cases):
        # Find lines containing this case number
        lines = text.split('\n')
        matching_lines = [line.strip() for line in lines if case.upper() in line.upper() and line.strip()]
        print(f"\nCase {case} appears in:")
        for i, line in enumerate(matching_lines[:5]):  # Show first 5 occurrences
            print(f"  {i+1}. {line[:100]}...")

