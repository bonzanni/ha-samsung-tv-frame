"""Shared fixtures for Samsung Frame TV tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


@pytest.fixture
def mock_device() -> MagicMock:
    """A mocked FrameDevice with async methods."""
    device = MagicMock()
    device.async_device_info = AsyncMock(
        return_value={"PowerState": "on", "FrameTVSupport": "true",
                      "wifiMac": "02:00:00:00:00:01", "modelName": "QE65LS03BAUXXH"}
    )
    device.async_get_artmode = AsyncMock(return_value=False)
    device.async_set_artmode = AsyncMock()
    device.async_turn_on = AsyncMock()
    device.async_turn_off = AsyncMock()
    device.async_start_art_listener = AsyncMock()
    device.async_stop = AsyncMock()
    device.newest_token = None  # plain attr: MagicMock's default would be truthy
    return device
