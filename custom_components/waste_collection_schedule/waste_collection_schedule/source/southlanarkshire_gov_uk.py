from datetime import datetime, timedelta
import re

import requests
from bs4 import BeautifulSoup
from waste_collection_schedule import Collection  # type: ignore[attr-defined]

TITLE = "South Lanarkshire Council"
DESCRIPTION = "Source for South Lanarkshire Council waste collection."
URL = "https://www.southlanarkshire.gov.uk"

HOW_TO_GET_ARGUMENTS_DESCRIPTION = {
    "en": "Find your street on the South Lanarkshire website. The URL format is \`.../directory_record/574605/clincarthill_road_rutherglen\`. Record ID is \`574605\` and Street Name is \`clincarthill_road_rutherglen\`.",
}

PARAM_TRANSLATIONS = {
    "en": {
        "calendar_title": "Calendar Title",
        "record_id": "Directory Record ID",
        "street_name": "Street Name",
        "pdf_url": "Collection Calendar PDF URL (optional)",
    }
}

PARAM_DESCRIPTIONS = {
    "en": {
        "calendar_title": "A more readable, or user-friendly, name for the waste calendar. If nothing is provided, the name returned by the source will be used.",
        "record_id": "The 6-digit number in your URL (e.g., 574605).",
        "street_name": "The text at the end of your URL (e.g., clincarthill_road_rutherglen).",
        "pdf_url": "(Optional) Full URL to council's bin collection calendar PDF. The schedule is determined from your current week's bins, so this is optional but can be provided for reference. Find PDFs at https://www.southlanarkshire.gov.uk/downloads/download/791/bin_collection_calendars",
    }
}

TEST_CASES = {
    "Rutherglen": {
        "record_id": "574605",
        "street_name": "clincarthill_road_rutherglen",
        "pdf_url": "https://www.southlanarkshire.gov.uk/download/downloads/id/18301/east_kilbride_cambuslang_and_rutherglen_bin_collection_calendar_2026_-_households_with_4_bins.pdf",
    },
    "Hamilton": {
        "record_id": "576617",
        "street_name": "alexander_balfour_gardens_hamilton",
        "pdf_url": "https://www.southlanarkshire.gov.uk/downloads/file/18300/hamilton_and_clydesdale_bin_collection_calendar_2026_-_households_with_4_bins",
    },
}

ICON_MAP = {
    "Black": "mdi:trash-can",
    "Green": "mdi:trash-can",
    "Burgundy": "mdi:leaf",
    "Blue": "mdi:file-document-outline",
    "Light": "mdi:glass-fragile",
}

SORT_ORDER = {
    "Blue": 1,
    "Light": 2,
    "Burgundy": 3,
    "Black": 4,
    "Green": 4,
}


class Source:
    def __init__(self, record_id: str | int, street_name: str, pdf_url: str = None):
        self._record_id = str(record_id).zfill(6)
        self._street_name = str(street_name)
        self._pdf_url = pdf_url
    
    def fetch(self):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        
        r = s.get(
            f"https://www.southlanarkshire.gov.uk/directory_record/{self._record_id}/{self._street_name}"
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        bin_div = soup.find("div", {"class": "bin-dir-snip"})
        if not bin_div:
            raise Exception("Could not find bin collection info")
            
        week_para = bin_div.find("p")
        if not week_para:
            raise Exception("Could not find week information")
            
        week_text = week_para.text.strip()
        parts = week_text.split(" to ")
        if len(parts) != 2:
            raise Exception(f"Unexpected week format: {week_text}")
            
        start_date_str = parts[0].strip()
        current_week_start = datetime.strptime(start_date_str, "%A %d %B %Y").date()
        
        bins_this_week = set()
        bins_this_week_elements = bin_div.find_all("li")
        for li in bins_this_week_elements:
            h4 = li.find("h4")
            if h4:
                bin_name = h4.text.strip().lower()
                bins_this_week.add(bin_name)
        
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
        
        current_week_bins = self._identify_bin_combination(bins_this_week)
        
        days_to_collection = (collection_day_num - current_week_start.weekday()) % 7
        current_collection_date = current_week_start + timedelta(days=days_to_collection)
        
        pattern_cycle = self._determine_pattern_cycle(current_week_bins)
        
        collections = []
        for week_offset in range(52):
            collection_date = current_collection_date + timedelta(weeks=week_offset)
            bins_for_week = pattern_cycle[week_offset % len(pattern_cycle)]
            
            for bin_type in bins_for_week:
                bin_color = bin_type.split()[0]
                icon = ICON_MAP.get(bin_color, "mdi:trash-can")
                collections.append(
                    Collection(date=collection_date, t=bin_type, icon=icon)
                )
        
        def get_sort_key(entry):
            bin_color = entry.type.split()[0] if entry.type else ""
            sort_order = SORT_ORDER.get(bin_color, 99)
            return (entry.date, sort_order)
        
        collections.sort(key=get_sort_key)
        return collections
    
    def _identify_bin_combination(self, bins_this_week_set):
        has_black = any("black" in b or "green" in b for b in bins_this_week_set)
        has_blue = any("blue" in b for b in bins_this_week_set)
        has_grey = any("grey" in b or "gray" in b for b in bins_this_week_set)
        has_burgundy = any("burgundy" in b for b in bins_this_week_set)
        
        if has_black:
            return "black"
        elif has_blue and has_burgundy:
            return "blue+burgundy"
        elif has_blue:
            return "blue+burgundy"
        elif has_grey and has_burgundy:
            return "grey+burgundy"
        elif has_grey:
            return "grey+burgundy"
        else:
            return "black"
    
    def _determine_pattern_cycle(self, current_week_bins):
        black_bins = ["Black/Green - Non Recyclable Waste"]
        blue_burgundy_bins = ["Blue (paper and card)", "Burgundy - Food and garden"]
        grey_burgundy_bins = ["Light Grey - Glass, cans and plastics", "Burgundy - Food and garden"]
        
        if current_week_bins == "black":
            return [black_bins, grey_burgundy_bins, black_bins, blue_burgundy_bins]
        elif current_week_bins == "grey+burgundy":
            return [grey_burgundy_bins, black_bins, blue_burgundy_bins, black_bins]
        elif current_week_bins == "blue+burgundy":
            return [blue_burgundy_bins, black_bins, grey_burgundy_bins, black_bins]
        else:
            return [black_bins, grey_burgundy_bins, black_bins, blue_burgundy_bins]
