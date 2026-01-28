# South Lanarkshire Waste Collection - Deployment to Home Assistant

## Files to Copy to Home Assistant

To update your Home Assistant installation with the fixed South Lanarkshire waste collection schedule, copy this ONE file:

### Required File:
```
custom_components/waste_collection_schedule/waste_collection_schedule/source/southlanarkshire_gov_uk.py
```

### Copy Location in Home Assistant:
```
<your-homeassistant-config>/custom_components/waste_collection_schedule/waste_collection_schedule/source/southlanarkshire_gov_uk.py
```

## What Was Fixed

✅ **Correct bin combinations** - Now only shows valid combinations from the PDF:
   - Black bin only
   - Blue + Burgundy
   - Grey + Burgundy

✅ **No impossible combinations** - Fixed issues where Black appeared with recycling bins, or all three bins appeared together

✅ **PDF-aware pattern detection** - Schedule is determined from your current week's bins, making it work for any year

✅ **4-week repeating cycle** - Properly implements the council's pattern

✅ **Works for all South Lanarkshire areas** - Tested with:
   - Rutherglen (East Kilbride/Cambuslang/Rutherglen PDF)
   - Hamilton (Hamilton/Clydesdale PDF)

## Configuration Example

```yaml
waste_collection_schedule:
  sources:
    - name: southlanarkshire_gov_uk
      args:
        record_id: "574605"
        street_name: "clincarthill_road_rutherglen"
        pdf_url: "https://www.southlanarkshire.gov.uk/download/downloads/id/18301/east_kilbride_cambuslang_and_rutherglen_bin_collection_calendar_2026_-_households_with_4_bins.pdf"  # Optional
```

**Note:** The `pdf_url` parameter is now optional. The schedule works without it by detecting the pattern from your current week's bins.

## After Copying

1. Restart Home Assistant
2. Check your waste collection calendar
3. Verify the schedule matches the council's PDF calendar

## Expected Schedule Pattern

The schedule follows a 4-week cycle (example for Rutherglen):
- **Week 1**: Black bin only
- **Week 2**: Grey + Burgundy
- **Week 3**: Black bin only
- **Week 4**: Blue + Burgundy

(Hamilton and other areas may be on a different phase of the same cycle)

## For Future Years (2027+)

When the council releases a new PDF for 2027, simply update the `pdf_url` parameter in your configuration (optional). The pattern detection will continue to work automatically.
