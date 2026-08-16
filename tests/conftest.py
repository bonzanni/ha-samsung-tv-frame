"""Shared fixtures for Samsung Frame TV tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.samsung_tv_frame.art_session import ArtSessionState

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration in every test."""
    yield


@pytest.fixture(autouse=True)
def silent_ssdp_scanner():
    """Set up the ssdp dependency without emitting real SSDP traffic.

    The manifest declares ``dependencies: ["ssdp"]`` so that core guarantees
    ``async_upnp_client`` is present (see CHANGELOG 0.9.1). That makes Home
    Assistant set up the real ssdp integration during tests, whose listeners
    and UPnP servers open multicast sockets that pytest-socket blocks at
    teardown. Patch them out, mirroring core's own fixture of the same name.
    """
    with (
        patch(
            "homeassistant.components.ssdp.scanner.Scanner._async_start_ssdp_listeners"
        ),
        patch(
            "homeassistant.components.ssdp.scanner.Scanner._async_stop_ssdp_listeners"
        ),
        patch("homeassistant.components.ssdp.scanner.Scanner.async_scan"),
        patch("homeassistant.components.ssdp.server.Server._async_start_upnp_servers"),
        patch("homeassistant.components.ssdp.server.Server._async_stop_upnp_servers"),
    ):
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
    device.set_art_event_callback = MagicMock()
    device.art_ready = False
    device.art_generation = 0
    device.art_session_state = ArtSessionState.STOPPED
    device.observe_art_power = MagicMock()
    device.set_art_session_state_callback = MagicMock()
    device.set_remote_token_callback = MagicMock()
    device.set_remote_reauth_callback = MagicMock()
    device.async_start_art_session = AsyncMock()
    device.async_set_artmode = AsyncMock()
    device.async_turn_on = AsyncMock()
    device.async_turn_off = AsyncMock()
    device.async_stop = AsyncMock()
    device.async_quiesce_remote = AsyncMock()
    device.resume_remote = MagicMock()
    device.async_send_key = AsyncMock()
    device.async_launch_app = AsyncMock()
    device.async_app_list = AsyncMock(return_value=None)
    device.async_app_status = AsyncMock(return_value=None)
    device.async_get_volume = AsyncMock(return_value=(None, None))
    device.async_set_volume = AsyncMock()
    device.async_set_mute = AsyncMock()
    device.async_hold_key = AsyncMock()
    device.async_get_current_art = AsyncMock(return_value=None)
    device.async_get_art_settings = AsyncMock(return_value=None)
    device.async_get_slideshow_state = AsyncMock(return_value=None)
    device.async_set_art_brightness = AsyncMock()
    device.async_select_art = AsyncMock()
    device.async_get_art_thumbnail = AsyncMock(return_value=None)
    device.async_change_matte = AsyncMock()
    device.async_set_photo_filter = AsyncMock()
    device.async_set_favourite = AsyncMock()
    device.async_set_color_temperature = AsyncMock()
    device.async_upload_art = AsyncMock(return_value="MY_F9999")
    device.async_delete_art = AsyncMock(return_value=True)
    device.async_set_slideshow = AsyncMock()
    device.async_set_motion_timer = AsyncMock()
    device.async_set_motion_sensitivity = AsyncMock()
    device.async_set_brightness_sensor = AsyncMock()
    device.newest_token = None  # plain attr: MagicMock's default would be truthy
    return device
