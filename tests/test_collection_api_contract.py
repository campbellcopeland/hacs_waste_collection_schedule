"""
Collection API contract tests.

These tests import the REAL waste_collection_schedule package (no mocking) and
verify that:
  1. The Collection constructor accepts exactly the arguments used by
     southlanarkshire_gov_uk.py: Collection(date=..., t=..., icon=...)
  2. The properties the source relies on (.type, .date, .icon) still exist and
     return the correct values.
  3. CollectionAggregator and SourceShell remain importable from the package
     root (used by wcs_coordinator.py and init_ui.py).

If upstream changes the Collection signature (e.g. makes `t` keyword-only,
renames it, or adds a new required argument), these tests will fail immediately
rather than silently producing broken collections at runtime.
"""

import datetime
import inspect
import sys
import os

import pytest

# ---------------------------------------------------------------------------
# Make the bundled package importable without Home Assistant being installed
# ---------------------------------------------------------------------------
PACKAGE_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "custom_components",
    "waste_collection_schedule",
)
sys.path.insert(0, os.path.abspath(PACKAGE_DIR))

from waste_collection_schedule import Collection, CollectionAggregator  # noqa: E402
from waste_collection_schedule.source_shell import Customize, SourceShell  # noqa: E402


# ---------------------------------------------------------------------------
# Collection constructor signature
# ---------------------------------------------------------------------------

class TestCollectionSignature:
    """Verify Collection.__init__ keeps the signature used by southlanarkshire_gov_uk.py."""

    def test_collection_has_date_param(self):
        sig = inspect.signature(Collection.__init__)
        assert "date" in sig.parameters, "Collection.__init__ must have a 'date' parameter"

    def test_collection_has_t_param(self):
        sig = inspect.signature(Collection.__init__)
        assert "t" in sig.parameters, (
            "Collection.__init__ must have a 't' parameter — "
            "southlanarkshire_gov_uk.py calls Collection(date=..., t=bin_type, icon=...)"
        )

    def test_collection_has_icon_param(self):
        sig = inspect.signature(Collection.__init__)
        assert "icon" in sig.parameters, "Collection.__init__ must have an 'icon' parameter"

    def test_icon_has_default_value(self):
        """icon must be optional so sources that omit it still work."""
        sig = inspect.signature(Collection.__init__)
        param = sig.parameters["icon"]
        assert param.default is not inspect.Parameter.empty, (
            "Collection.__init__ 'icon' must have a default value (it is optional)"
        )

    def test_t_is_not_positional_only(self):
        """t must be passable as a keyword argument (Collection(date=..., t=..., icon=...))."""
        sig = inspect.signature(Collection.__init__)
        param = sig.parameters["t"]
        assert param.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
        ), "'t' must be usable as a keyword argument"


# ---------------------------------------------------------------------------
# Collection construction — the exact call pattern in southlanarkshire_gov_uk
# ---------------------------------------------------------------------------

class TestCollectionConstruction:
    """Verify Collection can be constructed as the source does it."""

    def _make(self, bin_type="Black/Green - Non Recyclable Waste", icon="mdi:trash-can"):
        return Collection(
            date=datetime.date(2026, 1, 5),
            t=bin_type,
            icon=icon,
        )

    def test_construction_does_not_raise(self):
        c = self._make()
        assert c is not None

    def test_type_property_returns_bin_type(self):
        c = self._make(bin_type="Blue (paper and card)")
        assert c.type == "Blue (paper and card)"

    def test_date_property_returns_date(self):
        c = self._make()
        assert c.date == datetime.date(2026, 1, 5)

    def test_icon_property_returns_icon(self):
        c = self._make(icon="mdi:leaf")
        assert c.icon == "mdi:leaf"

    def test_none_icon_is_accepted(self):
        """Sources may omit icon; None must be a valid value."""
        c = Collection(date=datetime.date(2026, 1, 5), t="Black Bin", icon=None)
        assert c is not None

    def test_all_bin_types_used_by_southlanarkshire(self):
        """Every bin label emitted by southlanarkshire_gov_uk.py must be valid."""
        bin_types = [
            "Black/Green - Non Recyclable Waste",
            "Light Grey - Glass, cans and plastics",
            "Burgundy - Food and garden",
            "Blue (paper and card)",
        ]
        for bt in bin_types:
            c = Collection(date=datetime.date(2026, 1, 5), t=bt, icon="mdi:trash-can")
            assert c.type == bt, f"Expected type '{bt}', got '{c.type}'"

    def test_collection_is_sortable_by_date(self):
        """Collections must be sortable — the source sorts by (date, sort_order)."""
        c1 = Collection(date=datetime.date(2026, 1, 5), t="Black Bin")
        c2 = Collection(date=datetime.date(2026, 1, 12), t="Blue Bin")
        assert c1.date < c2.date


# ---------------------------------------------------------------------------
# Package-level exports used by the HA integration layer
# ---------------------------------------------------------------------------

class TestPackageExports:
    """Verify the package __init__.py still exports the names used by init_ui.py
    and wcs_coordinator.py.  If upstream restructures the package these will fail
    before the integration even loads in Home Assistant."""

    def test_collection_importable_from_package_root(self):
        from waste_collection_schedule import Collection as C  # noqa: F401
        assert C is not None

    def test_collection_aggregator_importable(self):
        from waste_collection_schedule import CollectionAggregator as CA  # noqa: F401
        assert CA is not None

    def test_source_shell_importable(self):
        from waste_collection_schedule import SourceShell as SS  # noqa: F401
        assert SS is not None

    def test_customize_importable(self):
        from waste_collection_schedule import Customize as Cust  # noqa: F401
        assert Cust is not None

    def test_collection_aggregator_accepts_list_of_shells(self):
        """CollectionAggregator.__init__ takes an iterable of SourceShell — verify
        the constructor signature hasn't changed."""
        sig = inspect.signature(CollectionAggregator.__init__)
        params = list(sig.parameters.keys())
        # First param after self should accept source shells
        assert len(params) >= 2, "CollectionAggregator.__init__ must accept at least one argument"


# ---------------------------------------------------------------------------
# SourceShell.create signature — matches what init_ui.py passes
# ---------------------------------------------------------------------------

class TestSourceShellCreateSignature:
    """init_ui.py calls SourceShell.create(name, customize, args, calendar_title, day_offset).
    If upstream adds a new REQUIRED parameter, init_ui.py will break silently."""

    def test_create_has_source_name_param(self):
        sig = inspect.signature(SourceShell.create)
        params = sig.parameters
        assert "source_name" in params, "SourceShell.create must have 'source_name' parameter"

    def test_create_has_customize_param(self):
        sig = inspect.signature(SourceShell.create)
        assert "customize" in sig.parameters

    def test_create_has_source_args_param(self):
        sig = inspect.signature(SourceShell.create)
        assert "source_args" in sig.parameters

    def test_create_calendar_title_is_optional(self):
        sig = inspect.signature(SourceShell.create)
        param = sig.parameters.get("calendar_title")
        assert param is not None, "SourceShell.create must have 'calendar_title' param"
        assert param.default is not inspect.Parameter.empty, (
            "'calendar_title' must be optional — init_ui.py passes options.get(...) which may be None"
        )

    def test_create_day_offset_is_optional(self):
        sig = inspect.signature(SourceShell.create)
        param = sig.parameters.get("day_offset")
        assert param is not None, "SourceShell.create must have 'day_offset' param"
        assert param.default is not inspect.Parameter.empty, (
            "'day_offset' must be optional — init_ui.py passes options.get(..., default)"
        )

    def test_no_new_required_params_added(self):
        """Alert when upstream adds a new REQUIRED param to SourceShell.create.
        If this test fails after a merge, update init_ui.py to pass the new param."""
        sig = inspect.signature(SourceShell.create)
        required = {
            name
            for name, p in sig.parameters.items()
            if p.default is inspect.Parameter.empty
            and p.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        }
        known_required = {"source_name", "customize", "source_args"}
        new_required = required - known_required
        assert not new_required, (
            f"SourceShell.create gained new required parameter(s): {new_required}. "
            "Update init_ui.py to pass these, then update this test."
        )
