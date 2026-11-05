"""A hostless Art answer is a fault only once it outlasts a boot (#29).

Measured on a 2022 Frame: a cold boot answers the Art channel without a host
for up to 84 s while PowerState is already "on", and a screen-dark standby
wake leaves the Art session idle while the sticky flag still remembers an
earlier wedge. Neither is something the owner should power-cycle for.
"""
from unittest.mock import patch

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_tv_frame.const import (
    ART_HOST_GRACE_SECONDS,
    CONF_HOST,
    CONF_MAC,
    CONF_TOKEN,
    DOMAIN,
)

SENSOR = "binary_sensor.samsung_frame_tv_art_service"


async def _setup(hass, mock_device):
    """Set up healthy, so every hostless stretch starts on the test's clock."""
    mock_device.art_host_unavailable = False
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_MAC: "02:00:00:00:00:01", CONF_TOKEN: "t"},
        unique_id="02:00:00:00:00:01",
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.samsung_tv_frame.FrameDevice", return_value=mock_device
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    coordinator = entry.runtime_data
    clock = [1000.0]
    coordinator._clock = lambda: clock[0]
    return entry, coordinator, clock


async def _poll(hass, coordinator):
    await coordinator.async_refresh()
    await hass.async_block_till_done()


def _reported(hass, entry) -> bool:
    sensor = hass.states.get(SENSOR).state == "on"
    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"art_service_unavailable_{entry.entry_id}"
    ) is not None
    assert sensor == issue, "the sensor and the repair must agree"
    return sensor


async def test_a_booting_tv_is_not_reported_until_the_grace_runs_out(
    hass, mock_device
):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    entry, coordinator, clock = await _setup(hass, mock_device)
    mock_device.art_host_unavailable = True
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)

    clock[0] += ART_HOST_GRACE_SECONDS - 1
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)

    clock[0] += 1
    await _poll(hass, coordinator)
    assert _reported(hass, entry)


async def test_a_host_that_registers_in_time_is_never_reported(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    entry, coordinator, clock = await _setup(hass, mock_device)
    mock_device.art_host_unavailable = True
    await _poll(hass, coordinator)

    clock[0] += 84
    mock_device.art_host_unavailable = False
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)

    # A later hostless stretch starts its own grace, not the boot's.
    clock[0] += 600
    mock_device.art_host_unavailable = True
    await _poll(hass, coordinator)
    clock[0] += ART_HOST_GRACE_SECONDS - 1
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)
    clock[0] += 1
    await _poll(hass, coordinator)
    assert _reported(hass, entry)


async def test_losing_the_tv_restarts_the_grace(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    entry, coordinator, clock = await _setup(hass, mock_device)
    mock_device.art_host_unavailable = True
    await _poll(hass, coordinator)

    clock[0] += ART_HOST_GRACE_SECONDS - 10
    mock_device.async_device_info.return_value = None
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)

    clock[0] += 20
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)
    clock[0] += ART_HOST_GRACE_SECONDS
    await _poll(hass, coordinator)
    assert _reported(hass, entry)


async def test_a_standby_wake_on_a_learned_model_is_never_reported(
    hass, mock_device
):
    """The session does not ask the TV here, so the flag is only a memory."""
    mock_device.async_device_info.return_value = {"PowerState": "standby"}
    entry, coordinator, clock = await _setup(hass, mock_device)
    mock_device.art_host_unavailable = True
    coordinator._art_implies_power_on = True

    for _ in range(3):
        await _poll(hass, coordinator)
        clock[0] += ART_HOST_GRACE_SECONDS
    await _poll(hass, coordinator)
    assert not _reported(hass, entry)


async def test_standby_still_counts_on_a_model_that_shows_art_in_standby(
    hass, mock_device
):
    """2025 Frames report "standby" during normal art mode, and the session
    keeps asking them, so a wedge there must still surface."""
    mock_device.async_device_info.return_value = {"PowerState": "standby"}
    entry, coordinator, clock = await _setup(hass, mock_device)
    mock_device.art_host_unavailable = True
    assert coordinator._art_implies_power_on is False

    await _poll(hass, coordinator)
    clock[0] += ART_HOST_GRACE_SECONDS
    await _poll(hass, coordinator)
    assert _reported(hass, entry)
