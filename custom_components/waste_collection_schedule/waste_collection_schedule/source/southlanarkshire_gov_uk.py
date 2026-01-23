from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from waste_collection_schedule import Collection  # type: ignore[attr-defined]

TITLE = "South Lanarkshire Council"
DESCRIPTION = "Source for South Lanarkshire Council waste collection."
URL = "https://www.southlanarkshire.gov.uk"

HOW_TO_GET_ARGUMENTS_DESCRIPTION = {
    "en": "Find your street on the South Lanarkshire website. The URL format is `.../directory_record/574605/clincarthill_road_rutherglen`. Record ID is `574605` and Street Name is `clincarthill_road_rutherglen`.",
}

PARAM_TRANSLATIONS = {
    "en": {
        "record_id": "Directory Record ID",
        "street_name": "Street Name",
        "pdf_url": "Collection Calendar PDF URL",
    }
}

PARAM_DESCRIPTIONS = {
    "en": {
        "record_id": "The 6-digit number in your URL (e.g., 574605).",
        "street_name": "The text at the end of your URL (e.g., clincarthill_road_rutherglen).",
        "pdf_url": "Full URL to council's bin collection calendar PDF. Find the current year's calendar at https://www.southlanarkshire.gov.uk/downloads/download/791/bin_collection_calendars and copy the PDF link. Example: https://www.southlanarkshire.gov.uk/download/downloads/id/18301/bin_collection_calendar_2026.pdf",
    }
}

TEST_CASES = {
    "Test_001": {
        "record_id": "574605",
        "street_name": "clincarthill_road_rutherglen",
        "pdf_url": "https://www.southlanarkshire.gov.uk/download/downloads/id/18301/bin_collection_calendar_2026.pdf",
    },
}

ICON_MAP = {
    "Black": "mdi:trash-can",
    "Green": "mdi:trash-can",
    "Burgundy": "mdi:leaf",
    "Blue": "mdi:file-document-outline",
    "Light Grey": "mdi:glass-fragile",
}

# Sort order: recyclables first, then organics, then general waste
SORT_ORDER = {
    "Blue": 1,
    "Light Grey": 2,
    "Burgundy": 3,
    "Black": 4,
    "Green": 4,
}


class Source:
    def __init__(self, record_id: str | int, street_name: str, pdf_url: str = None):
        self._record_id = str(record_id).zfill(6)
        self._street_name = str(street_name)
        self._pdf_url = pdf_url
        self._collection_weeks_cache = None
    
    def _parse_pdf_weeks(self, year: int) -> list:
        """Parse collection week dates from council PDF calendar."""
        import re
        import tempfile
        
        if not self._pdf_url:
            raise Exception(
                "pdf_url parameter is required. "
                "Please find the current year's bin collection calendar PDF at "
                "https://www.southlanarkshire.gov.uk/downloads/download/791/bin_collection_calendars "
                "and provide the full PDF URL. "
                "Example: https://www.southlanarkshire.gov.uk/download/downloads/id/18301/bin_collection_calendar_2026.pdf"
            )
        
        pdf_url = self._pdf_url
        
        try:
            # Download PDF
            s = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            response = s.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name
            
            try:
                # Try to import pypdf or PyPDF2
                pdf_text = ""
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(tmp_path)
                    for page in reader.pages:
                        pdf_text += page.extract_text()
                except ImportError:
                    try:
                        from PyPDF2 import PdfReader
                        reader = PdfReader(tmp_path)
                        for page in reader.pages:
                            pdf_text += page.extract_text()
                    except ImportError:
                        raise Exception(
                            "PDF parsing requires 'pypdf' or 'PyPDF2' library. "
                            "Please install with: pip install pypdf"
                        )
                
                # Parse Monday dates from PDF
                # Look for patterns like "5 January", "12 January", etc.
                weeks = []
                month_names = [
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ]
                
                for line in pdf_text.split('\n'):
                    for month_name in month_names:
                        matches = re.findall(rf'\b(\d{{1,2}})\s+{month_name}\b', line)
                        for day in matches:
                            try:
                                date_obj = datetime.strptime(f"{day} {month_name} {year}", "%d %B %Y").date()
                                # Only include Mondays (weekday 0)
                                if date_obj.weekday() == 0:
                                    date_str = date_obj.strftime("%Y-%m-%d")
                                    if date_str not in weeks:
                                        weeks.append(date_str)
                            except ValueError:
                                continue
                
                weeks.sort()
                
                if not weeks:
                    raise Exception(f"No Monday dates found in PDF from {pdf_url}")
                
                return weeks
            finally:
                import os
                os.unlink(tmp_path)
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download PDF from {pdf_url}: {e}")
        except Exception as e:
            raise Exception(f"Failed to parse PDF calendar: {e}. Please check pdf_url parameter or update for new year.")
    
    def _generate_mondays(self, year: int) -> list:
        """Generate all Mondays for a given year as fallback."""
        weeks = []
        jan_1 = datetime(year, 1, 1).date()
        
        # Find first Monday
        days_until_monday = (7 - jan_1.weekday()) % 7
        if days_until_monday == 0 and jan_1.weekday() != 0:
            days_until_monday = 7
        first_monday = jan_1 + timedelta(days=days_until_monday)
        
        # Generate all Mondays
        current = first_monday
        end_of_year = datetime(year, 12, 31).date()
        
        while current <= end_of_year:
            weeks.append(current.strftime("%Y-%m-%d"))
            current += timedelta(weeks=1)
        
        return weeks

    def fetch(self):
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        
        r = s.get(
            f"https://www.southlanarkshire.gov.uk/directory_record/{self._record_id}/{self._street_name}"
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        
        # Get the current collection week start date
        bin_div = soup.find("div", {"class": "bin-dir-snip"})
        if not bin_div:
            raise Exception("Could not find bin collection information on page")
            
        week_para = bin_div.find("p")
        if not week_para:
            raise Exception("Could not find collection week information")
            
        week_text = week_para.text.strip()
        # Parse: "Monday 19 January 2026 to Friday 23 January 2026"
        parts = week_text.split(" to ")
        if len(parts) != 2:
            raise Exception(f"Unexpected week format: {week_text}")
            
        start_date_str = parts[0].strip()
        current_week_start = datetime.strptime(start_date_str, "%A %d %B %Y").date()
        
        # Get collection weeks for absolute positioning
        year = current_week_start.year
        if self._collection_weeks_cache is None:
            self._collection_weeks_cache = self._parse_pdf_weeks(year)
        collection_weeks = self._collection_weeks_cache
        
        # Find current week index
        current_week_str = current_week_start.strftime("%Y-%m-%d")
        try:
            current_week_index = collection_weeks.index(current_week_str)
        except ValueError:
            # Fallback: calculate based on first week
            first_week = datetime.strptime(collection_weeks[0], "%Y-%m-%d").date()
            weeks_diff = (current_week_start - first_week).days // 7
            current_week_index = max(0, weeks_diff)
        
        # Get which bins are being collected THIS week
        bins_this_week = set()
        bins_this_week_elements = bin_div.find_all("li")
        for li in bins_this_week_elements:
            h4 = li.find("h4")
            if h4:
                link = h4.find("a")
                if link:
                    bin_name = link.text.strip().lower()
                    bins_this_week.add(bin_name)
        
        # Get the schedule table
        table = soup.find("table")
        if not table:
            raise Exception("Could not find collection schedule table")
            
        rows = table.find_all("tr")
        entries = []
        
        day_map = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }
        
        for row in rows:
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            
            waste_type = th.text.strip()
            schedule_info = td.text.strip()
            
            # Find day of week in schedule
            day_name = None
            for day in day_map:
                if day in schedule_info:
                    day_name = day
                    break
                    
            if not day_name:
                continue
            
            day_of_week = day_map[day_name]
            
            # Get icon for this waste type
            icon = "mdi:trash-can"
            for color, color_icon in ICON_MAP.items():
                if color in waste_type:
                    icon = color_icon
                    break
            
            # Check if this bin is collected this week
            waste_type_lower = waste_type.lower()
            is_collected_this_week = any(
                ("blue" in waste_type_lower and "blue" in bin_name) or
                ("burgundy" in waste_type_lower and "burgundy" in bin_name) or
                ("black" in waste_type_lower and "black" in bin_name) or
                ("grey" in waste_type_lower and "grey" in bin_name) or
                ("gray" in waste_type_lower and "gray" in bin_name)
                for bin_name in bins_this_week
            )
            
            # Generate future collection dates using absolute week positioning
            for i in range(current_week_index, min(current_week_index + 52, len(collection_weeks))):
                week_str = collection_weeks[i]
                week_monday = datetime.strptime(week_str, "%Y-%m-%d").date()
                
                # Calculate the actual collection day in this week
                days_to_add = (day_of_week - week_monday.weekday()) % 7
                collection_date = week_monday + timedelta(days=days_to_add)
                
                # Calculate week offset from current week (for determining phase)
                week_offset = i - current_week_index
                
                # Determine if this bin should be collected based on absolute week position
                should_collect = False
                
                if "Fortnightly" in schedule_info:
                    # Fortnightly: use absolute week number modulo 2
                    # If collected this week, check if (absolute_week % 2) matches current
                    if is_collected_this_week:
                        should_collect = (i % 2) == (current_week_index % 2)
                    else:
                        should_collect = (i % 2) != (current_week_index % 2)
                        
                elif "4 Weekly" in schedule_info:
                    # 4-weekly: use absolute week number modulo 4
                    if is_collected_this_week:
                        should_collect = (i % 4) == (current_week_index % 4)
                    else:
                        # We don't know which phase without checking other weeks
                        # Try to find the phase by checking the fortnightly bins
                        # If both fortnightly bins follow the same absolute week parity,
                        # we can infer the 4-weekly phase
                        # For South Lanarkshire: 4-weekly bins are typically offset by 2 weeks
                        # from the alternate fortnightly bin
                        # 
                        # The robust solution: check which fortnightly bin is collected this week
                        # Blue/Burgundy on even weeks (0,2,4,6), Black/Green on odd weeks (1,3,5,7)
                        # Light Grey on weeks where (week % 4 == 0)
                        # So if current week is even (Blue collected), Light Grey phase is 0
                        # If current week is odd (Black collected), Light Grey is 2 weeks ahead
                        if current_week_index % 2 == 0:
                            # Even week: 4-weekly bin at phase 0
                            target_phase = 0
                        else:
                            # Odd week: 4-weekly bin at phase 2 (odd + 2 = next cycle)
                            target_phase = 2
                        should_collect = (i % 4) == target_phase
                else:
                    # Weekly collection
                    should_collect = True
                
                if should_collect:
                    entries.append(
                        Collection(date=collection_date, t=waste_type, icon=icon)
                    )

        # Sort entries by date first, then by bin type (recyclables before organics/waste)
        def get_sort_key(entry):
            # Find which color this bin is
            for color in SORT_ORDER:
                if color in entry.type:
                    return (entry.date, SORT_ORDER[color])
            return (entry.date, 99)  # Unknown types go last
        
        entries.sort(key=get_sort_key)
        return entries
