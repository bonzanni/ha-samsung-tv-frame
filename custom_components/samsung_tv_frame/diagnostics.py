"""Diagnostics support for the Samsung Frame TV integration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_MODEL,
    DEFAULT_DETECT_RUNNING_APP,
    DEFAULT_HEARTBEAT_SECONDS,
    OPT_DETECT_RUNNING_APP,
    OPT_HEARTBEAT,
)
from .coordinator import FrameConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FrameConfigEntry
) -> dict[str, Any]:
    """Return strictly allowlisted, zero-I/O config-entry diagnostics."""
    del hass
    coordinator = getattr(entry, "runtime_data", None)
    result = {
        "loaded": coordinator is not None,
        "model": entry.data.get(CONF_MODEL, "The Frame"),
        "heartbeat_seconds": entry.options.get(
            OPT_HEARTBEAT, DEFAULT_HEARTBEAT_SECONDS
        ),
        "detect_running_app": entry.options.get(
            OPT_DETECT_RUNNING_APP, DEFAULT_DETECT_RUNNING_APP
        ),
    }
    if not result["loaded"]:
        return result
    return {**result, **coordinator.diagnostics_snapshot()}
