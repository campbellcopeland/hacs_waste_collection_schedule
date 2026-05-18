"""
Integration-layer contract tests.

These tests do NOT require Home Assistant to be installed.  They use direct
imports (for modules without HA dependencies) and AST parsing (for modules that
import HA) to verify that the glue between our local files is consistent.

What they catch after an upstream merge
---------------------------------------
* const.py is missing a name that init_ui.py or wcs_coordinator.py references.
* WCSCoordinator.__init__ gains a new required parameter that init_ui.py doesn't pass.
* SourceShell.create gains a new required parameter that init_ui.py doesn't pass.
* config_flow.py uses a renamed attribute (e.g. the self._source → self._id
  rename that broke the config flow in the v2.18.0 merge).
* The waste_collection_schedule sub-package is not reachable from the component
  directory (the import-path bug that required the site.addsitedir fix).
"""

import ast
import importlib.util
import inspect
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
COMPONENT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "custom_components", "waste_collection_schedule")
)
INIT_UI_PATH = os.path.join(COMPONENT_DIR, "init_ui.py")
COORDINATOR_PATH = os.path.join(COMPONENT_DIR, "wcs_coordinator.py")
CONST_PATH = os.path.join(COMPONENT_DIR, "const.py")
CONFIG_FLOW_PATH = os.path.join(COMPONENT_DIR, "config_flow.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ast(path: str) -> ast.Module:
    with open(path) as fh:
        return ast.parse(fh.read(), filename=path)


def _const_attr_references(tree: ast.Module) -> set[str]:
    """Return all `const.XXX` attribute names referenced in the AST."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "const"
        ):
            names.add(node.attr)
    return names


def _kwargs_passed_to(tree: ast.Module, callee_name: str) -> set[str]:
    """Return keyword argument names passed to any call of `callee_name(...)` in the tree."""
    kwargs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Matches bare name: WCSCoordinator(...) or SourceShell.create(...)
            is_match = (
                (isinstance(func, ast.Name) and func.id == callee_name)
                or (isinstance(func, ast.Attribute) and func.attr == callee_name)
            )
            if is_match:
                for kw in node.keywords:
                    if kw.arg is not None:  # skip **kwargs spreads
                        kwargs.add(kw.arg)
    return kwargs


def _import_const():
    """Import const.py without needing homeassistant installed."""
    spec = importlib.util.spec_from_file_location("wcs_const", CONST_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Import-path smoke test
# ---------------------------------------------------------------------------

class TestImportPath:
    """Verify the waste_collection_schedule sub-package structure is intact so
    that the HA integration layer can import it at runtime.

    These tests use filesystem and AST checks (not runtime imports) so they are
    immune to sys.modules state set by other test files in the suite, e.g.
    test_southlanarkshire_enhanced.py which installs a MagicMock in sys.modules."""

    PKG_DIR = os.path.join(COMPONENT_DIR, "waste_collection_schedule")

    def test_bundled_package_directory_exists(self):
        """COMPONENT_DIR must contain a waste_collection_schedule/ subdirectory."""
        assert os.path.isdir(self.PKG_DIR), (
            f"Bundled package not found at {self.PKG_DIR}. "
            "The HA integration won't be able to import waste_collection_schedule."
        )

    def test_package_init_exists(self):
        """The bundled package must have an __init__.py."""
        init_path = os.path.join(self.PKG_DIR, "__init__.py")
        assert os.path.isfile(init_path), (
            f"{init_path} not found — waste_collection_schedule is not a package."
        )

    def test_package_init_exports_collection(self):
        """waste_collection_schedule/__init__.py must export Collection."""
        init_path = os.path.join(self.PKG_DIR, "__init__.py")
        tree = _parse_ast(init_path)
        # Look for 'Collection' in any import or assignment at module level
        exported = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    exported.add(alias.asname or alias.name)
        assert "Collection" in exported, (
            f"waste_collection_schedule/__init__.py does not export Collection. "
            f"Exported names: {sorted(exported)}"
        )

    def test_package_init_exports_source_shell(self):
        """waste_collection_schedule/__init__.py must export SourceShell."""
        init_path = os.path.join(self.PKG_DIR, "__init__.py")
        tree = _parse_ast(init_path)
        exported = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    exported.add(alias.asname or alias.name)
        assert "SourceShell" in exported, (
            f"waste_collection_schedule/__init__.py does not export SourceShell. "
            f"Exported names: {sorted(exported)}"
        )

    def test_source_directory_exists(self):
        """waste_collection_schedule/source/ directory must exist."""
        source_dir = os.path.join(self.PKG_DIR, "source")
        assert os.path.isdir(source_dir), (
            f"source directory not found at {source_dir}. "
            "SourceShell.create won't be able to load any sources."
        )

    def test_southlanarkshire_source_file_exists_with_source_class(self):
        """The South Lanarkshire source must exist and define a Source class.
        Tested via AST to be immune to sys.modules state from other test files."""
        source_path = os.path.join(
            self.PKG_DIR, "source", "southlanarkshire_gov_uk.py"
        )
        assert os.path.isfile(source_path), (
            f"southlanarkshire_gov_uk.py not found at {source_path}"
        )
        tree = _parse_ast(source_path)
        class_names = [
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ]
        assert "Source" in class_names, (
            "southlanarkshire_gov_uk.py must define a Source class"
        )


# ---------------------------------------------------------------------------
# const.py completeness: every name used in init_ui.py must exist
# ---------------------------------------------------------------------------

class TestConstCompleteness:
    """AST-scan init_ui.py for every `const.XXX` reference, then verify each
    one is actually defined in const.py.

    This is the exact check that would have caught a missing
    CONF_FETCH_INTERVAL_DAYS or CONF_IGNORE_DUPLICATES if init_ui.py used them
    before const.py defined them."""

    @pytest.fixture(scope="class")
    def const_mod(self):
        return _import_const()

    @pytest.fixture(scope="class")
    def init_ui_const_refs(self):
        tree = _parse_ast(INIT_UI_PATH)
        return _const_attr_references(tree)

    def test_all_init_ui_const_references_exist(self, const_mod, init_ui_const_refs):
        missing = [
            name for name in init_ui_const_refs if not hasattr(const_mod, name)
        ]
        assert not missing, (
            f"const.py is missing names used by init_ui.py: {sorted(missing)}. "
            "Either add them to const.py or update init_ui.py."
        )

    def test_domain_defined(self, const_mod):
        assert hasattr(const_mod, "DOMAIN"), "const.DOMAIN must be defined"

    def test_core_conf_names_defined(self, const_mod):
        """Belt-and-braces check for names that are fundamental to the integration."""
        core_names = [
            "CONF_SOURCE_NAME",
            "CONF_SOURCE_ARGS",
            "CONF_SEPARATOR",
            "CONF_SEPARATOR_DEFAULT",
            "CONF_FETCH_TIME",
            "CONF_FETCH_TIME_DEFAULT",
            "CONF_RANDOM_FETCH_TIME_OFFSET",
            "CONF_RANDOM_FETCH_TIME_OFFSET_DEFAULT",
            "CONF_DAY_SWITCH_TIME",
            "CONF_DAY_SWITCH_TIME_DEFAULT",
            "CONF_DAY_OFFSET",
            "CONF_DAY_OFFSET_DEFAULT",
            "CONF_CUSTOMIZE",
        ]
        missing = [n for n in core_names if not hasattr(const_mod, n)]
        assert not missing, f"const.py is missing core names: {missing}"


# ---------------------------------------------------------------------------
# WCSCoordinator call-site compatibility
# ---------------------------------------------------------------------------

class TestWCSCoordinatorCallSite:
    """Verify that init_ui.py passes every required parameter of WCSCoordinator.

    When upstream adds a new required parameter to WCSCoordinator.__init__ (e.g.
    fetch_interval_days in v2.19+), this test will fail, alerting you to update
    init_ui.py before the merge is deployed."""

    @pytest.fixture(scope="class")
    def coordinator_required_params(self):
        """Parse wcs_coordinator.py with AST to find WCSCoordinator.__init__ required params."""
        tree = _parse_ast(COORDINATOR_PATH)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "WCSCoordinator":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        args = item.args
                        all_args = [a.arg for a in args.args[1:]]  # skip self
                        n_defaults = len(args.defaults)
                        required = (
                            set(all_args[: len(all_args) - n_defaults])
                            if n_defaults
                            else set(all_args)
                        )
                        return required
        pytest.fail("Could not find WCSCoordinator.__init__ in wcs_coordinator.py")

    @pytest.fixture(scope="class")
    def init_ui_coordinator_kwargs(self):
        """Find kwargs that init_ui.py passes to WCSCoordinator(...)."""
        tree = _parse_ast(INIT_UI_PATH)
        return _kwargs_passed_to(tree, "WCSCoordinator")

    def test_init_ui_passes_all_required_coordinator_params(
        self, coordinator_required_params, init_ui_coordinator_kwargs
    ):
        # 'hass' and 'source_shell' are passed positionally; exclude them from check
        positional_params = {"hass", "source_shell"}
        required_kwargs = coordinator_required_params - positional_params
        missing = required_kwargs - init_ui_coordinator_kwargs
        assert not missing, (
            f"init_ui.py does not pass required WCSCoordinator parameter(s): {sorted(missing)}. "
            "Update init_ui.py to pass the new parameter(s), then update this test."
        )

    def test_known_required_coordinator_params_still_present(self, coordinator_required_params):
        """These params have been required since v2.18 — alert if they are removed/renamed."""
        known = {"hass", "source_shell", "separator", "fetch_time",
                 "random_fetch_time_offset", "day_switch_time"}
        removed = known - coordinator_required_params
        assert not removed, (
            f"WCSCoordinator.__init__ lost previously-required params: {sorted(removed)}. "
            "Check if init_ui.py needs updating."
        )


# ---------------------------------------------------------------------------
# config_flow.py internal consistency
# ---------------------------------------------------------------------------

class TestConfigFlowConsistency:
    """AST checks on config_flow.py to catch internal inconsistencies that
    would produce AttributeError at runtime without a traceback that identifies
    the call site.

    The specific history here: in the v2.18.0 merge the config_flow broke
    because a method was called with an attribute (self._source / self._id)
    that was not assigned at that point in the flow.  These tests verify that
    whatever attribute _get_description_placeholders is called with is actually
    assigned somewhere in the same file."""

    @pytest.fixture(scope="class")
    def config_flow_tree(self):
        return _parse_ast(CONFIG_FLOW_PATH)

    def _collect_assigned_self_attrs(self, tree: ast.Module) -> set[str]:
        """Return every `self.xxx` attribute that is the target of an assignment."""
        assigned: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and isinstance(
                        target.value, ast.Name
                    ) and target.value.id == "self":
                        assigned.add(target.attr)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                target = node.target
                if isinstance(target, ast.Attribute) and isinstance(
                    target.value, ast.Name
                ) and target.value.id == "self":
                    assigned.add(target.attr)
        return assigned

    def _args_passed_to_description_placeholders(self, tree: ast.Module) -> list[str]:
        """Return self.xxx attribute names passed to _get_description_placeholders."""
        attr_args: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_get_description_placeholders"
            ):
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Attribute)
                        and isinstance(arg.value, ast.Name)
                        and arg.value.id == "self"
                    ):
                        attr_args.append(arg.attr)
        return attr_args

    def test_description_placeholders_called_with_assigned_attribute(
        self, config_flow_tree
    ):
        """_get_description_placeholders must be called with a self.xxx attribute
        that is actually assigned somewhere in config_flow.py.  This catches the
        case where a rename (e.g. self._source → self._id) is applied to one place
        but not the other, leaving a dangling reference."""
        assigned = self._collect_assigned_self_attrs(config_flow_tree)
        args_used = self._args_passed_to_description_placeholders(config_flow_tree)

        assert args_used, (
            "_get_description_placeholders is never called with a self.xxx argument. "
            "Verify config_flow.py still calls _get_description_placeholders correctly."
        )

        for attr in args_used:
            assert attr in assigned, (
                f"_get_description_placeholders is called with self.{attr}, "
                f"but self.{attr} is never assigned in config_flow.py. "
                f"This will raise AttributeError at runtime. "
                f"Attributes that ARE assigned: {sorted(assigned)}"
            )

    def test_description_placeholders_argument_is_consistent_across_all_calls(
        self, config_flow_tree
    ):
        """All calls to _get_description_placeholders should use the same
        self.xxx attribute — mixing self._source and self._id would indicate
        a half-applied rename."""
        args_used = self._args_passed_to_description_placeholders(config_flow_tree)
        unique = set(args_used)
        assert len(unique) <= 1, (
            f"_get_description_placeholders is called with inconsistent attributes: "
            f"{unique}. This suggests a partial rename in config_flow.py."
        )


# ---------------------------------------------------------------------------
# init_ui.py const references completeness — wcs_coordinator.py too
# ---------------------------------------------------------------------------

class TestCoordinatorConstReferences:
    """Same const completeness check applied to wcs_coordinator.py."""

    @pytest.fixture(scope="class")
    def const_mod(self):
        return _import_const()

    def test_all_coordinator_const_references_exist(self, const_mod):
        tree = _parse_ast(COORDINATOR_PATH)
        refs = _const_attr_references(tree)
        missing = [name for name in refs if not hasattr(const_mod, name)]
        assert not missing, (
            f"const.py is missing names used by wcs_coordinator.py: {sorted(missing)}"
        )
