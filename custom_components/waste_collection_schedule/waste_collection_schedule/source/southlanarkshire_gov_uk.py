from datetime import datetime, timedelta
import re
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from waste_collection_schedule import Collection  # type: ignore[attr-defined]

TITLE = "South Lanarkshire Council"
DESCRIPTION = "Source for South Lanarkshire Council waste collection."
URL = "https://www.southlanarkshire.gov.uk"

HOW_TO_GET_ARGUMENTS_DESCRIPTION = {
    "en": "Find your street on the South Lanarkshire website. The URL format is `.../directory_record/574605/clincarthill_road_rutherglen`. Record ID is `574605` and Street Name is `clincarthill_road_rutherglen`.",
}

PARAM_TRANSLATIONS = {
    "en": {
        "calendar_title": "Calendar Title",
        "record_id": "Directory Record ID",
        "street_name": "Street Name",
        "pdf_url": "Collection Calendar PDF URL",
    }
}

PARAM_DESCRIPTIONS = {
    "en": {
        "calendar_title": "A more readable, or user-friendly, name for the waste calendar. If nothing is provided, the name returned by the source will be used.",
        "record_id": "The 6-digit number in your URL (e.g., 574605).",
        "street_name": "The text at the end of your URL (e.g., clincarthill_road_rutherglen).",
        "pdf_url": "REQUIRED: Full URL to council's bin collection calendar PDF. This is essential for determining your exact position in the 4-week collection cycle, as black bins appear twice per cycle. Find PDFs at https://www.southlanarkshire.gov.uk/downloads/download/791/bin_collection_calendars",
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
    def __init__(self, record_id: str | int, street_name: str, pdf_url: str):
        if not pdf_url:
            raise ValueError(
                "pdf_url is required to determine collection cycle position. "
                "Black bins appear twice in the 4-week cycle, making position impossible to determine without PDF reference. "
                "Find PDFs at: https://www.southlanarkshire.gov.uk/downloads/download/791/bin_collection_calendars"
            )
        self._record_id = str(record_id).zfill(6)
        self._street_name = str(street_name)
        self._pdf_url = pdf_url
    
    def fetch(self):
        # Get current week's bins from website
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
        
        days_to_collection = (collection_day_num - current_week_start.weekday()) % 7
        current_collection_date = current_week_start + timedelta(days=days_to_collection)
        
        # Parse PDF to determine position in 4-week cycle
        pdf_schedule = self._parse_pdf_schedule()
        cycle_position = self._determine_cycle_position(current_week_start, pdf_schedule)
        pattern_cycle = self._get_pattern_from_cycle_position(cycle_position)
        
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
    
    def _parse_pdf_schedule(self):
        """Parse PDF to extract bin collection schedule for multiple weeks."""
        import logging
        logger = logging.getLogger(__name__)
        
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        
        # Add timeout to prevent hanging in Home Assistant
        logger.debug(f"Downloading PDF from: {self._pdf_url}")
        response = s.get(self._pdf_url, timeout=30)
        response.raise_for_status()
        logger.debug(f"PDF downloaded, size: {len(response.content)} bytes")
        
        pdf_reader = PdfReader(BytesIO(response.content))
        schedule = {}
        
        logger.debug(f"PDF has {len(pdf_reader.pages)} pages")
        
        # Try to detect year from PDF filename or content
        year_from_url = re.search(r'20\d{2}', self._pdf_url)
        current_year = datetime.now().year
        years_to_try = [current_year]
        if year_from_url:
            pdf_year = int(year_from_url.group())
            if pdf_year not in years_to_try:
                years_to_try.insert(0, pdf_year)
        years_to_try.append(current_year + 1)  # Also try next year
        logger.debug(f"Will try years: {years_to_try}")
        
        # Extract text from all pages and parse dates and bins
        all_text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            # Try layout mode first, fall back to default if not supported
            try:
                text = page.extract_text(extraction_mode="layout")
                logger.debug(f"Page {page_num + 1}: extracted text with layout mode")
            except (TypeError, AttributeError) as e:
                # Older pypdf versions don't support extraction_mode parameter
                text = page.extract_text()
                logger.debug(f"Page {page_num + 1}: extracted text with default mode (layout not supported: {e})")
            if text:
                all_text += text + "\n"
                logger.debug(f"Page {page_num + 1}: extracted {len(text)} characters")
            else:
                logger.warning(f"Page {page_num + 1}: no text extracted")
        
        logger.debug(f"Total text extracted: {len(all_text)} characters")
        
        if not all_text.strip():
            logger.error("No text extracted from PDF at all - PDF may be image-based or encrypted")
            return schedule
        
        # Log first 500 chars to help debug
        logger.debug(f"First 500 chars of PDF text: {all_text[:500]}")
        
        # Try multiple date patterns to handle different PDF formats
        date_patterns = [
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)',
            r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
            r'(\d{1,2})/(\d{1,2})/(20\d{2})',  # DD/MM/YYYY format
        ]
        
        lines = all_text.split('\n')
        logger.debug(f"Split into {len(lines)} lines")
        
        dates_found = 0
        for i, line in enumerate(lines):
            # Try first pattern: "Monday 5 January"
            date_match = re.search(date_patterns[0], line)
            if date_match:
                day_name, day, month = date_match.groups()
                for year in years_to_try:
                    try:
                        date_obj = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
                        bins_for_this_week = self._identify_bins_from_pdf_lines(lines, i)
                        if bins_for_this_week:
                            schedule[date_obj] = bins_for_this_week
                            dates_found += 1
                            logger.debug(f"Found date {date_obj} with bins: {bins_for_this_week}")
                            break
                        else:
                            logger.debug(f"Found date {date_obj} but no bins identified")
                    except ValueError:
                        continue
                continue
            
            # Try second pattern: "5 January Monday"
            date_match = re.search(date_patterns[1], line)
            if date_match:
                day, month, day_name = date_match.groups()
                for year in years_to_try:
                    try:
                        date_obj = datetime.strptime(f"{day} {month} {year}", "%d %B %Y").date()
                        bins_for_this_week = self._identify_bins_from_pdf_lines(lines, i)
                        if bins_for_this_week:
                            schedule[date_obj] = bins_for_this_week
                            dates_found += 1
                            logger.debug(f"Found date {date_obj} with bins: {bins_for_this_week}")
                            break
                        else:
                            logger.debug(f"Found date {date_obj} but no bins identified")
                    except ValueError:
                        continue
        
        logger.info(f"PDF parsing complete: found {dates_found} dates with bins out of {len(schedule)} total")
        
        if not schedule:
            logger.error(
                "No dates with bins found in PDF. "
                "This may be due to: 1) PDF is image-based (not text), "
                "2) Date format doesn't match patterns, "
                "3) Bin keywords not found near dates. "
                f"PDF URL: {self._pdf_url}"
            )
        
        return schedule
    
    def _identify_bins_from_pdf_lines(self, lines, current_line_idx):
        """Extract bin types from PDF text around a date."""
        bins = set()
        
        # Look at next few lines after the date for bin information
        for i in range(current_line_idx + 1, min(current_line_idx + 5, len(lines))):
            line_lower = lines[i].lower()
            if "black" in line_lower or "green" in line_lower:
                bins.add("black")
            if "blue" in line_lower:
                bins.add("blue")
            if "grey" in line_lower or "gray" in line_lower:
                bins.add("grey")
            if "burgundy" in line_lower or "brown" in line_lower:
                bins.add("burgundy")
        
        return self._identify_bin_combination(bins) if bins else None
    
    def _determine_cycle_position(self, current_week_date, pdf_schedule):
        """Determine where in the 4-week cycle we are based on PDF data."""
        if not pdf_schedule:
            raise Exception("PDF schedule is empty - could not parse any dates from PDF. Please verify the PDF URL is correct and accessible.")
        
        # Find entries from PDF that are closest to current week (look back 60 days, forward 180 days)
        all_dates = list(pdf_schedule.keys())
        sorted_dates = sorted([d for d in all_dates if current_week_date - timedelta(days=60) <= d <= current_week_date + timedelta(days=180)])
        
        if not sorted_dates:
            # Provide helpful error with actual dates found
            date_range = f"{min(all_dates)} to {max(all_dates)}" if all_dates else "none"
            raise Exception(
                f"Could not find current week ({current_week_date}) in PDF schedule. "
                f"PDF contains dates from {date_range}. "
                f"Current date: {datetime.now().date()}. "
                f"Please ensure you're using the correct year's PDF."
            )
        
        # Find the date closest to current week
        pdf_week_date = min(sorted_dates, key=lambda d: abs(d - current_week_date))
        current_week_type = pdf_schedule[pdf_week_date]
        
        # Get the next few weeks from PDF to establish the cycle
        cycle_from_pdf = []
        for i in range(4):
            check_date = pdf_week_date + timedelta(weeks=i)
            # Find closest matching date within 7 days
            candidates = [d for d in all_dates if abs((d - check_date).days) <= 7]
            if candidates:
                closest = min(candidates, key=lambda d: abs(d - check_date))
                if closest in pdf_schedule:
                    cycle_from_pdf.append(pdf_schedule[closest])
        
        # Map cycle_from_pdf to a position (0-3) based on known patterns
        if len(cycle_from_pdf) >= 2:
            first_type = cycle_from_pdf[0]
            second_type = cycle_from_pdf[1] if len(cycle_from_pdf) > 1 else None
            
            # Determine position based on the sequence
            if first_type == "black" and second_type == "grey+burgundy":
                return 0  # Black is at position 0
            elif first_type == "grey+burgundy" and second_type == "black":
                return 1  # Grey+Burgundy is at position 1
            elif first_type == "blue+burgundy" and second_type == "black":
                return 2  # Blue+Burgundy is at position 2
            elif first_type == "black" and second_type == "blue+burgundy":
                return 3  # Second Black is at position 3
        
        # Fallback: assume position 0
        return 0
    
    def _get_pattern_from_cycle_position(self, position):
        """Get the 4-week repeating pattern based on position."""
        black_bins = ["Black/Green - Non Recyclable Waste"]
        blue_burgundy_bins = ["Blue (paper and card)", "Burgundy - Food and garden"]
        grey_burgundy_bins = ["Light Grey - Glass, cans and plastics", "Burgundy - Food and garden"]
        
        base_pattern = [black_bins, grey_burgundy_bins, black_bins, blue_burgundy_bins]
        
        # Rotate pattern based on position
        return base_pattern[position:] + base_pattern[:position]
    def _identify_bin_combination(self, bins_set):
        """Convert bin set to standardized type string."""
        has_black = any("black" in str(b).lower() or "green" in str(b).lower() for b in bins_set)
        has_blue = any("blue" in str(b).lower() for b in bins_set)
        has_grey = any("grey" in str(b).lower() or "gray" in str(b).lower() for b in bins_set)
        has_burgundy = any("burgundy" in str(b).lower() or "brown" in str(b).lower() for b in bins_set)
        
        if has_black:
            return "black"
        elif (has_blue or has_grey) and has_burgundy:
            if has_blue:
                return "blue+burgundy"
            else:
                return "grey+burgundy"
        else:
            return "black"
