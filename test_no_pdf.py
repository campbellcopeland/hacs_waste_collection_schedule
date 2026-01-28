#!/usr/bin/env python3
"""Test South Lanarkshire without PDF URL"""

import sys
sys.path.insert(0, "custom_components/waste_collection_schedule")

from waste_collection_schedule.source.southlanarkshire_gov_uk import Source

print("Testing South Lanarkshire Council WITHOUT PDF URL...")
print("=" * 70)

# Test without PDF
source = Source(
    record_id="574605",
    street_name="clincarthill_road_rutherglen"
    # No pdf_url provided
)

try:
    entries = source.fetch()
    print(f"✓ Fetch successful! Got {len(entries)} entries")
    print("\nFirst 10 collections:")
    for entry in entries[:10]:
        print(f"  {entry.date} ({entry.date.strftime('%a')}) - {entry.type}")
except Exception as e:
    print(f"✗ Fetch failed: {e}")
    import traceback
    traceback.print_exc()
