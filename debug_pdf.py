#!/usr/bin/env python3
"""Debug script to inspect PDF content extraction"""

import sys
import re
from io import BytesIO
import requests
from pypdf import PdfReader

if len(sys.argv) < 2:
    print("Usage: python3 debug_pdf.py <pdf_url>")
    sys.exit(1)

pdf_url = sys.argv[1]

print(f"Fetching PDF from: {pdf_url}\n")

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

response = s.get(pdf_url)
response.raise_for_status()

pdf_reader = PdfReader(BytesIO(response.content))

print(f"PDF has {len(pdf_reader.pages)} pages\n")
print("=" * 80)

for page_num in range(min(3, len(pdf_reader.pages))):  # Show first 3 pages
    print(f"\n PAGE {page_num + 1} - Default extraction mode:")
    print("-" * 80)
    page = pdf_reader.pages[page_num]
    text = page.extract_text()
    lines = text.split('\n')[:30]  # First 30 lines
    for i, line in enumerate(lines):
        print(f"{i:3}: {line}")
    
    print(f"\n PAGE {page_num + 1} - Layout extraction mode:")
    print("-" * 80)
    text_layout = page.extract_text(extraction_mode="layout")
    lines_layout = text_layout.split('\n')[:30]  # First 30 lines
    for i, line in enumerate(lines_layout):
        print(f"{i:3}: {line}")
    
    # Look for date patterns
    date_pattern = r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)'
    matches = re.findall(date_pattern, text_layout)
    if matches:
        print(f"\n Found {len(matches)} date matches on page {page_num + 1}:")
        for match in matches[:10]:  # Show first 10
            print(f"   {match}")
