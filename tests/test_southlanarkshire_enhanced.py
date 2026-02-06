import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta, date
from io import BytesIO
import sys
import os

# Mock the required modules before importing
sys.modules['waste_collection_schedule'] = MagicMock()

# Add the custom_components path to sys.path so we can import the source
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'waste_collection_schedule', 'waste_collection_schedule'))

from source.southlanarkshire_gov_uk import Source


class TestSourceInit(unittest.TestCase):
    """Test Source initialization."""

    def test_init_with_valid_parameters(self):
        """Test Source initialization with valid parameters."""
        source = Source(
            record_id="574605",
            street_name="clincarthill_road_rutherglen",
            pdf_url="https://example.com/calendar.pdf"
        )
        self.assertEqual(source._record_id, "574605")
        self.assertEqual(source._street_name, "clincarthill_road_rutherglen")
        self.assertEqual(source._pdf_url, "https://example.com/calendar.pdf")

    def test_init_with_int_record_id(self):
        """Test Source initialization with integer record_id."""
        source = Source(record_id=574605, street_name="test_street", pdf_url="https://example.com/calendar.pdf")
        self.assertEqual(source._record_id, "574605")

    def test_init_with_short_record_id_pads_with_zeros(self):
        """Test that short record_id values are padded with zeros."""
        source = Source(record_id="123", street_name="test_street", pdf_url="https://example.com/calendar.pdf")
        self.assertEqual(source._record_id, "000123")

    def test_init_raises_error_without_pdf_url(self):
        """Test that ValueError is raised when pdf_url is missing."""
        with self.assertRaises(ValueError) as context:
            Source(record_id="574605", street_name="test_street", pdf_url="")
        self.assertIn("pdf_url is required", str(context.exception))

    def test_init_raises_error_with_none_pdf_url(self):
        """Test that ValueError is raised when pdf_url is None."""
        with self.assertRaises(ValueError):
            Source(record_id="574605", street_name="test_street", pdf_url=None)


class TestIdentifyBinCombination(unittest.TestCase):
    """Test _identify_bin_combination method."""

    def setUp(self):
        self.source = Source(
            record_id="574605",
            street_name="test_street",
            pdf_url="https://example.com/calendar.pdf"
        )

    def test_identify_black_bins(self):
        """Test identification of black bins."""
        result = self.source._identify_bin_combination({"black bin"})
        self.assertEqual(result, "black")

    def test_identify_green_as_black(self):
        """Test that green bins are identified as black."""
        result = self.source._identify_bin_combination({"green bin"})
        self.assertEqual(result, "black")

    def test_identify_blue_burgundy_combination(self):
        """Test identification of blue and burgundy combination."""
        result = self.source._identify_bin_combination({"blue", "burgundy"})
        self.assertEqual(result, "blue+burgundy")

    def test_identify_grey_burgundy_combination(self):
        """Test identification of grey and burgundy combination."""
        result = self.source._identify_bin_combination({"grey", "burgundy"})
        self.assertEqual(result, "grey+burgundy")

    def test_identify_gray_burgundy_combination(self):
        """Test identification of gray (alternate spelling) and burgundy combination."""
        result = self.source._identify_bin_combination({"gray", "burgundy"})
        self.assertEqual(result, "grey+burgundy")

    def test_identify_blue_without_burgundy_defaults_to_black(self):
        """Test that blue without burgundy defaults to black."""
        result = self.source._identify_bin_combination({"blue"})
        self.assertEqual(result, "black")

    def test_identify_empty_set_defaults_to_black(self):
        """Test that empty bin set defaults to black."""
        result = self.source._identify_bin_combination(set())
        self.assertEqual(result, "black")

    def test_identify_brown_as_burgundy(self):
        """Test that brown is identified as burgundy."""
        result = self.source._identify_bin_combination({"blue", "brown"})
        self.assertEqual(result, "blue+burgundy")

    def test_identify_case_insensitive(self):
        """Test that bin identification is case-insensitive."""
        result = self.source._identify_bin_combination({"BLACK BIN"})
        self.assertEqual(result, "black")

    def test_identify_with_none_values(self):
        """Test identification with None values in set."""
        result = self.source._identify_bin_combination({None, "black"})
        self.assertEqual(result, "black")


class TestGetPatternFromCyclePosition(unittest.TestCase):
    """Test _get_pattern_from_cycle_position method."""

    def setUp(self):
        self.source = Source(
            record_id="574605",
            street_name="test_street",
            pdf_url="https://example.com/calendar.pdf"
        )

    def test_pattern_position_0(self):
        """Test pattern at position 0."""
        pattern = self.source._get_pattern_from_cycle_position(0)
        self.assertEqual(len(pattern), 4)
        self.assertEqual(pattern[0], ["Black/Green - Non Recyclable Waste"])
        self.assertEqual(pattern[1], ["Light Grey - Glass, cans and plastics", "Burgundy - Food and garden"])
        self.assertEqual(pattern[2], ["Black/Green - Non Recyclable Waste"])
        self.assertEqual(pattern[3], ["Blue (paper and card)", "Burgundy - Food and garden"])

    def test_pattern_position_1(self):
        """Test pattern rotated to position 1."""
        pattern = self.source._get_pattern_from_cycle_position(1)
        self.assertEqual(len(pattern), 4)
        self.assertEqual(pattern[0], ["Light Grey - Glass, cans and plastics", "Burgundy - Food and garden"])

    def test_pattern_position_2(self):
        """Test pattern rotated to position 2."""
        pattern = self.source._get_pattern_from_cycle_position(2)
        self.assertEqual(len(pattern), 4)
        self.assertEqual(pattern[0], ["Black/Green - Non Recyclable Waste"])

    def test_pattern_position_3(self):
        """Test pattern rotated to position 3."""
        pattern = self.source._get_pattern_from_cycle_position(3)
        self.assertEqual(len(pattern), 4)
        self.assertEqual(pattern[0], ["Blue (paper and card)", "Burgundy - Food and garden"])

    def test_pattern_cycles_correctly(self):
        """Test that pattern cycles through 4 positions correctly."""
        for position in range(4):
            pattern = self.source._get_pattern_from_cycle_position(position)
            # Verify it's a list of 4 weeks
            self.assertEqual(len(pattern), 4)
            # Verify each week contains bin types
            for week in pattern:
                self.assertIsInstance(week, list)
                self.assertGreater(len(week), 0)


class TestIdentifyBinsFromPdfLines(unittest.TestCase):
    """Test _identify_bins_from_pdf_lines method."""

    def setUp(self):
        self.source = Source(
            record_id="574605",
            street_name="test_street",
            pdf_url="https://example.com/calendar.pdf"
        )

    def test_identify_black_from_lines(self):
        """Test identification of black bins from PDF lines."""
        lines = ["5 January", "Black bin collection"]
        result = self.source._identify_bins_from_pdf_lines(lines, 1)
        self.assertEqual(result, "black")

    def test_identify_blue_burgundy_from_lines(self):
        """Test identification of blue and burgundy from PDF lines."""
        lines = ["12 January", "Blue bin and Burgundy bin collection"]
        result = self.source._identify_bins_from_pdf_lines(lines, 1)
        self.assertEqual(result, "blue+burgundy")

    def test_identify_bins_in_surrounding_lines(self):
        """Test that bin identification checks surrounding lines."""
        lines = ["5 January", "Collection day", "Black bins", "Extra info"]
        result = self.source._identify_bins_from_pdf_lines(lines, 0)
        self.assertEqual(result, "black")

    def test_identify_none_when_no_bins(self):
        """Test that None is returned when no bins found."""
        lines = ["5 January", "No bins mentioned"]
        result = self.source._identify_bins_from_pdf_lines(lines, 0)
        self.assertIsNone(result)

    def test_identify_within_search_range(self):
        """Test that search stays within expected range."""
        lines = [""] * 10
        lines[5] = "Blue bin"
        # Should find from index 0-9 when searching around index 5
        result = self.source._identify_bins_from_pdf_lines(lines, 5)
        self.assertEqual(result, "black")  # Blue alone defaults to black


class TestDetermineCyclePosition(unittest.TestCase):
    """Test _determine_cycle_position method."""

    def setUp(self):
        self.source = Source(
            record_id="574605",
            street_name="test_street",
            pdf_url="https://example.com/calendar.pdf"
        )

    def test_determine_position_with_black_bins(self):
        """Test cycle position determination with black bins."""
        current_week = date(2026, 1, 5)
        pdf_schedule = {date(2026, 1, 12): "grey+burgundy"}
        bins_this_week = {"black bin"}

        position = self.source._determine_cycle_position(current_week, pdf_schedule, bins_this_week)
        self.assertEqual(position, 0)

    def test_determine_position_with_grey_burgundy(self):
        """Test cycle position determination with grey+burgundy bins."""
        current_week = date(2026, 1, 5)
        pdf_schedule = {date(2026, 1, 12): "black"}
        bins_this_week = {"grey bin", "burgundy bin"}

        position = self.source._determine_cycle_position(current_week, pdf_schedule, bins_this_week)
        self.assertEqual(position, 1)

    def test_determine_position_with_blue_burgundy(self):
        """Test cycle position determination with blue+burgundy bins."""
        current_week = date(2026, 1, 5)
        pdf_schedule = {date(2026, 1, 12): "black"}
        bins_this_week = {"blue bin", "burgundy bin"}

        position = self.source._determine_cycle_position(current_week, pdf_schedule, bins_this_week)
        self.assertEqual(position, 3)

    def test_determine_position_raises_with_empty_schedule(self):
        """Test that exception is raised with empty PDF schedule."""
        current_week = date(2026, 1, 5)
        bins_this_week = {"black bin"}

        with self.assertRaises(Exception) as context:
            self.source._determine_cycle_position(current_week, {}, bins_this_week)
        self.assertIn("PDF schedule is empty", str(context.exception))

    def test_determine_position_disambiguates_black_with_next_week(self):
        """Test that black position is disambiguated using next week's data."""
        current_week = date(2026, 1, 5)
        next_week = date(2026, 1, 12)
        pdf_schedule = {next_week: "grey+burgundy"}
        bins_this_week = {"black bin"}

        position = self.source._determine_cycle_position(current_week, pdf_schedule, bins_this_week)
        # If next week is grey+burgundy, current black should be at position 0
        self.assertEqual(position, 0)


class TestParsePdfSchedule(unittest.TestCase):
    """Test _parse_pdf_schedule method."""

    def setUp(self):
        self.source = Source(
            record_id="574605",
            street_name="test_street",
            pdf_url="https://example.com/calendar.pdf"
        )

    @patch('source.southlanarkshire_gov_uk.requests.Session')
    @patch('source.southlanarkshire_gov_uk.PdfReader')
    def test_parse_pdf_with_valid_content(self, mock_pdf_reader, mock_session):
        """Test PDF parsing with valid content."""
        # Mock PDF response
        mock_response = Mock()
        mock_response.content = b"PDF content"
        mock_response.raise_for_status = Mock()

        mock_session_instance = Mock()
        mock_session_instance.get = Mock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        # Mock PDF reader
        mock_page = Mock()
        mock_page.extract_text = Mock(return_value="5 January\nBlack bin\n12 January\nGrey bin")
        mock_pdf_reader.return_value.pages = [mock_page]

        schedule = self.source._parse_pdf_schedule()
        self.assertIsInstance(schedule, dict)

    @patch('source.southlanarkshire_gov_uk.requests.Session')
    @patch('source.southlanarkshire_gov_uk.PdfReader')
    def test_parse_pdf_with_no_text(self, mock_pdf_reader, mock_session):
        """Test PDF parsing when no text can be extracted."""
        mock_response = Mock()
        mock_response.content = b"PDF content"
        mock_response.raise_for_status = Mock()

        mock_session_instance = Mock()
        mock_session_instance.get = Mock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        mock_page = Mock()
        mock_page.extract_text = Mock(return_value="")
        mock_pdf_reader.return_value.pages = [mock_page]

        schedule = self.source._parse_pdf_schedule()
        self.assertEqual(schedule, {})

    @patch('source.southlanarkshire_gov_uk.requests.Session')
    def test_parse_pdf_network_error(self, mock_session):
        """Test PDF parsing with network error."""
        import requests
        mock_session_instance = Mock()
        mock_session_instance.get = Mock(side_effect=requests.exceptions.RequestException("Network error"))
        mock_session.return_value = mock_session_instance

        with self.assertRaises(requests.exceptions.RequestException):
            self.source._parse_pdf_schedule()


class TestFetch(unittest.TestCase):
    """Test fetch method."""

    def setUp(self):
        self.source = Source(
            record_id="574605",
            street_name="clincarthill_road_rutherglen",
            pdf_url="https://example.com/calendar.pdf"
        )

    @patch('source.southlanarkshire_gov_uk.requests.Session')
    def test_fetch_raises_on_missing_bin_info(self, mock_session):
        """Test that fetch raises exception when bin info is missing."""
        mock_response = Mock()
        mock_response.text = "<html><body>No bin info</body></html>"
        mock_response.raise_for_status = Mock()

        mock_session_instance = Mock()
        mock_session_instance.get = Mock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        with self.assertRaises(Exception) as context:
            self.source.fetch()
        self.assertIn("Could not find bin collection info", str(context.exception))

    @patch('source.southlanarkshire_gov_uk.requests.Session')
    def test_fetch_raises_on_missing_week_info(self, mock_session):
        """Test that fetch raises exception when week info is missing."""
        mock_response = Mock()
        mock_response.text = '<html><body><div class="bin-dir-snip"></div></body></html>'
        mock_response.raise_for_status = Mock()

        mock_session_instance = Mock()
        mock_session_instance.get = Mock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        with self.assertRaises(Exception) as context:
            self.source.fetch()
        self.assertIn("Could not find week information", str(context.exception))

    @patch('source.southlanarkshire_gov_uk.requests.Session')
    def test_fetch_raises_on_missing_table(self, mock_session):
        """Test that fetch raises exception when schedule table is missing."""
        mock_response = Mock()
        mock_response.text = '''<html><body>
            <div class="bin-dir-snip">
                <p>Monday 5 January 2026 to Friday 9 January 2026</p>
                <li><h4>Black bin</h4></li>
            </div>
        </body></html>'''
        mock_response.raise_for_status = Mock()

        mock_session_instance = Mock()
        mock_session_instance.get = Mock(return_value=mock_response)
        mock_session.return_value = mock_session_instance

        with self.assertRaises(Exception) as context:
            self.source.fetch()
        self.assertIn("Could not find collection schedule table", str(context.exception))


class TestSourceIntegration(unittest.TestCase):
    """Integration tests for Source class."""

    def test_source_creation_and_properties(self):
        """Test source can be created and properties are set correctly."""
        source = Source(
            record_id=574605,
            street_name="test_street",
            pdf_url="https://example.com/calendar.pdf"
        )
        self.assertIsNotNone(source)
        self.assertEqual(source._record_id, "574605")


if __name__ == "__main__":
    unittest.main()
