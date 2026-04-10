"""Waste Collection Schedule Component."""

from __future__ import annotations

import logging
import site
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Ensure bundled package imports like `waste_collection_schedule.*` resolve.
package_dir = Path(__file__).resolve().parent
site.addsitedir(str(package_dir))


def _load_yaml_setup() -> tuple[Any, Any]:
    """Load YAML setup symbols lazily.

    Some Home Assistant versions deprecate or remove helper imports used by
    YAML setup. We keep config-flow setup available even when YAML setup fails
    to import.
    """
    try:
        from .init_yaml import CONFIG_SCHEMA as _CONFIG_SCHEMA, async_setup as _async_setup

        return _CONFIG_SCHEMA, _async_setup
    except Exception as err:  # pragma: no cover - only hit in HA runtime
        _LOGGER.error("Failed to import YAML setup for waste_collection_schedule: %s", err)
        return vol.Schema({}, extra=vol.ALLOW_EXTRA), None


CONFIG_SCHEMA, _ASYNC_SETUP = _load_yaml_setup()


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration from YAML config."""
    if _ASYNC_SETUP is None:
        # Keep HA startup healthy if YAML setup import is broken.
        return True
    return await _ASYNC_SETUP(hass, config)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up integration from config entry."""
    from .init_ui import async_setup_entry as _async_setup_entry

    return await _async_setup_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload integration from config entry."""
    from .init_ui import async_unload_entry as _async_unload_entry

    return await _async_unload_entry(hass, entry)


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle config entry updates."""
    from .init_ui import async_update_listener as _async_update_listener

    return await _async_update_listener(hass, entry)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    from .init_ui import async_migrate_entry as _async_migrate_entry

    return await _async_migrate_entry(hass, entry)
