#!/usr/bin/env python3
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from collections import namedtuple
import re

Collection = namedtuple('Collection', ['date', 't', 'icon'])

ICON_MAP = {
    "Black": "mdi:trash-can",
    "Blue": "mdi:recycle",
    "Light": "mdi:bottle-soda",
    "Burgundy": "mdi:flower",
}

SORT_ORDER = {
    "Blue": 1,
    "Light": 2,
    "Burgundy": 3,
    "Black": 4,
}


class Source:
    def __init__(self, record_id: str | int, street_name: str, pdf_url: str = None):
        self._record_id = str(record_id).zfill(6)
        self._street_name = str(street_name)
        # Default to 2026 PDF if not specified - extract year dynamically for future years
        self._pdf_url = pdf_url or "https://www.southlanarkshire.gov.uk/download/downloads/id/18301/east_kilbride_cambuslang_and_rutherglen_bin_collection_calendar_2026_-_households_with_4_bins.pdf"
    
    def fetch(self):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        
        # Get street-specific information (day of week, current week bins)
        r = s.get(
            f"https://www.southlanarkshire.gov.uk/directory_record/{self._record_id}/{self._street_name}"
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # Get the current collection week start date
        bin_div = soup.find("div", {"class": "bin-dir-snip"})
        if not bin_div:
            raise Exception("Could not find bin collection info")
            
        week_para = bin_div.find("p")
        if not week_para:
            raise Exception("Could not find week information")
            
        week_text = week_para.text.strip()
        # Parse: "Monday 26 January 2026 to Friday 30 January 2026"
        parts = week_text.split(" to ")
        if len(parts) != 2:
            raise Exception(f"Unexpected week format: {week_text}")
            
        start_date_str = parts[0].strip()
        current_week_start = datetime.strptime(start_date_str, "%A %d %B %Y").date()
        
        # Get which bins are being collected THIS week
        bins_this_week = set()
        bins_this_week_elements = bin_div.find_all("li")
        for li in bins_this_week_elements:
            h4 = li.find("h4")
            if h4:
                bin_name = h4.text.strip().lower()
                bins_this_week.add(bin_name)
        
        # Get the day of week for collections from the table
        table = soup.find("table")
        if not table:
            raise Exception("Could not find collection schedule table")
            
        rows = table.find_all("tr")
        collection_day = None
        
        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if th and td:
                schedule_text = td.text.strip()
                # Extract day: "Friday (Fortnightly)"
                day_match = re.match(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)', schedule_text)
                if day_match and collection_day is None:
                    collection_day = day_match.group(1)
        
        if not collection_day:
            raise Exception("Could not determine collection day")
        
        day_map = {
            "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
            "Friday": 4, "Saturday": 5, "Sunday": 6,
        }
        collection_day_num = day_map[collection_day]
        
        # Determine current week's bin combination
        current_week_bins = self._identify_bin_combination(bins_this_week)
        
        # Calculate collection date for current week
        days_to_collection = (collection_day_num - current_week_start.weekday()) % 7
        current_collection_date = current_week_start + timedelta(days=days_to_collection)
        
        # Determine the pattern cycle based on current week
        pattern_cycle = self._determine_pattern_cycle(current_week_bins)
        
        # Generate collections for next 52 weeks
        collections = []
        for week_offset in range(52):
            collection_date = current_collection_date + timedelta(weeks=week_offset)
            
            # Determine which bins for this week based on pattern
            bins_for_week = pattern_cycle[week_offset % len(pattern_cycle)]
            
            for bin_type in bins_for_week:
                bin_color = bin_type.split()[0]
                icon = ICON_MAP.get(bin_color, "mdi:trash-can")
                collections.append(
                    Collection(date=collection_date, t=bin_type, icon=icon)
                )
        
        # Sort by date, then by bin priority
        def get_sort_key(entry):
            bin_color = entry.t.split()[0] if entry.t else ""
            sort_order = SORT_ORDER.get(bin_color, 99)
            return (entry.date, sort_order)
        
        collections.sort(key=get_sort_key)
        return collections
    
    def _identify_bin_combination(self, bins_this_week_set):
        """Identify which bin combination is collected this week."""
        has_black = any("black" in b or "green" in b for b in bins_this_week_set)
        has_blue = any("blue" in b for b in bins_this_week_set)
        has_grey = any("grey" in b or "gray" in b for b in bins_this_week_set)
        has_burgundy = any("burgundy" in b for b in bins_this_week_set)
        
        if has_black:
            return "black"
        elif has_blue and has_burgundy:
            return "blue+burgundy"
        elif has_blue:
            return "blue+burgundy"  # Assume burgundy comes with it
        elif has_grey and has_burgundy:
            return "grey+burgundy"
        elif has_grey:
            return "grey+burgundy"  # Assume burgundy comes with it
        else:
            return "black"  # Default
    
    def _determine_pattern_cycle(self, current_week_bins):
        """Determine the repeating pattern cycle based on current week.
        
        According to the PDF, valid combinations are:
        - Black only
        - Blue + Burgundy
        - Grey + Burgundy
        
        The pattern is a 4-week cycle that alternates between Black weeks and Recycling weeks.
        Black alternates fortnightly.
        Recycling weeks alternate between Blue+Burgundy and Grey+Burgundy.
        """
        
        black_bins = ["Black/Green - Non Recyclable Waste"]
        blue_burgundy_bins = ["Blue (paper and card)", "Burgundy - Food and garden"]
        grey_burgundy_bins = ["Light Grey - Glass, cans and plastics", "Burgundy - Food and garden"]
        
        if current_week_bins == "black":
            # Pattern starting with Black: Black, Grey+Burg, Black, Blue+Burg
            return [
                black_bins,
                grey_burgundy_bins,
                black_bins,
                blue_burgundy_bins,
            ]
        elif current_week_bins == "grey+burgundy":
            # Pattern starting with Grey+Burgundy: Grey+Burg, Black, Blue+Burg, Black
            return [
                grey_burgundy_bins,
                black_bins,
                blue_burgundy_bins,
                black_bins,
            ]
        elif current_week_bins == "blue+burgundy":
            # Pattern starting with Blue+Burgundy: Blue+Burg, Black, Grey+Burg, Black
            return [
                blue_burgundy_bins,
                black_bins,
                grey_burgundy_bins,
                black_bins,
            ]
        else:
            # Default pattern
            return [
                black_bins,
                grey_burgundy_bins,
                black_bins,
                blue_burgundy_bins,
            ]


def test_source():
    """Test the South Lanarkshire Council waste collection source."""
    print("Testing South Lanarkshire Council waste collection source...")
    print("=" * 70)
    
    try:
        # Create source for Clincarthill Road, Rutherglen
        source = Source('574605', 'clincarthill_road_rutherglen')
        
        # Fetch collections
        entries = source.fetch()
        
        print("✓ Fetch successful!")
        print(f"\nTotal entries: {len(entries)}")
        
        # Display first 15 collections
        print("\nFirst 15 collections:")
        for entry in entries[:15]:
            date_str = entry.date.strftime("%Y-%m-%d (%a)")
            print(f"  {date_str} - {entry.t}")
        
        # Verify dates are sorted
        is_sorted = all(entries[i].date <= entries[i+1].date for i in range(len(entries)-1))
        if is_sorted:
            print("\n✓ Dates are properly sorted")
        else:
            print("\n✗ ERROR: Dates are not sorted correctly!")
            return False
        
        # Show this week's collections
        today = datetime.now().date()
        this_week = [e for e in entries if e.date >= today and e.date < today + timedelta(days=7)]
        print("\nThis week's collections:")
        if this_week:
            for e in this_week:
                print(f"  {e.t}")
        else:
            print("  None")
        
        # Show next 4 weeks schedule grouped by date
        print("\nNext 4 weeks schedule:")
        weeks_shown = {}
        for e in entries:
            if e.date >= today and e.date < today + timedelta(days=28):
                date_str = e.date.strftime("%Y-%m-%d")
                if date_str not in weeks_shown:
                    weeks_shown[date_str] = []
                weeks_shown[date_str].append(e.t)
        
        for date_str in sorted(weeks_shown.keys()):
            bins = ", ".join(weeks_shown[date_str])
            print(f"  {date_str}: {bins}")
        
        print("\n✓ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_source()
