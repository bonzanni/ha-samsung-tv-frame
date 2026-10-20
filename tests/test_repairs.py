"""The wedged-art-service repair: the remedy is physical, so it must be said."""
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_tv_frame.art_session import ArtSessionState
from custom_components.samsung_tv_frame.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_TOKEN,
    DOMAIN,
)


async def _setup(hass, mock_device):
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
    return entry


def _issue(hass, entry):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"art_service_unavailable_{entry.entry_id}"
    )


async def test_a_wedged_art_host_raises_a_repair_naming_the_remedy(
    hass, mock_device
):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.translation_key == "art_service_unavailable"


async def test_no_repair_while_the_art_host_is_present(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = False
    entry = await _setup(hass, mock_device)

    assert _issue(hass, entry) is None


async def test_no_repair_for_a_tv_we_simply_cannot_reach(hass, mock_device):
    """An unreachable TV is not a repair — the owner has nothing to fix."""
    mock_device.async_device_info.return_value = None
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)

    assert _issue(hass, entry) is None


async def test_the_repair_clears_when_the_art_host_comes_back(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)
    assert _issue(hass, entry) is not None

    mock_device.art_host_unavailable = False
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_unloading_the_entry_clears_a_raised_repair(hass, mock_device):
    """A repair must not outlive the integration that can clear it.

    Once the entry is gone nothing polls the TV, so a lingering issue would
    be permanent and unactionable.
    """
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)
    assert _issue(hass, entry) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_a_stale_issue_is_reconciled_on_the_first_poll(hass, mock_device):
    """The in-memory edge flag cannot know what the registry already holds.

    A repair left standing by anything else must be cleared by the first
    healthy poll, not held until the flag happens to change.
    """
    ir.async_create_issue(
        hass,
        DOMAIN,
        "art_service_unavailable_stale",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="art_service_unavailable",
    )
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = False
    entry = await _setup(hass, mock_device)

    registry = ir.async_get(hass)
    # Its own issue id was reconciled away on the first poll.
    assert registry.async_get_issue(
        DOMAIN, f"art_service_unavailable_{entry.entry_id}"
    ) is None
    coordinator = entry.runtime_data
    assert coordinator._art_service_repair_synced is True


async def test_a_failed_setup_does_not_orphan_a_repair(hass, mock_device):
    """A repair with no coordinator behind it can never be cleared."""
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_MAC: "02:00:00:00:00:01", CONF_TOKEN: "t"},
        unique_id="02:00:00:00:00:01",
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.samsung_tv_frame.FrameDevice",
            return_value=mock_device,
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            side_effect=RuntimeError("platform setup blew up"),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_the_fault_is_poll_owned_and_an_art_push_cannot_move_it(
    hass, mock_device
):
    """One writer. The poll owns this fact, exactly like `reachable`.

    Retracting it from art pushes and READY transitions as well was tried and
    cut: it needed the fault cleared from four places, and four reviewers'
    rounds each found another path where they disagreed, published a stale
    value, or resurrected a failing coordinator. A recovered TV now clears
    within one heartbeat, which the documented `for:`-guarded automation does
    not notice.
    """
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)
    coordinator = entry.runtime_data
    assert coordinator.data.art_service_unavailable is True

    # A push republishes the snapshot; the polled fact must ride through
    # unchanged rather than being invented from a different channel.
    with patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        for payload in (
            {"event": "art_mode_changed", "status": "on"},
            {"event": "art_mode_changed", "status": "nav"},
            {"event": "go_to_standby"},
        ):
            coordinator.handle_art_event("d2d_service_message", payload)
        await hass.async_block_till_done()

    assert coordinator.data.art_service_unavailable is True
    assert _issue(hass, entry) is not None


async def test_one_poll_clears_it_once_the_host_is_back(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)
    coordinator = entry.runtime_data
    assert coordinator.data.art_service_unavailable is True

    mock_device.art_host_unavailable = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.data.art_service_unavailable is False
    assert _issue(hass, entry) is None


async def test_a_failed_poll_is_not_marked_successful_by_this_change(
    hass, mock_device
):
    """Nothing in this feature may touch `last_update_success`."""
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.art_host_unavailable = True
    entry = await _setup(hass, mock_device)
    coordinator = entry.runtime_data

    coordinator.last_update_success = False
    with patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
        coordinator.handle_art_session_state(ArtSessionState.READY)
        await hass.async_block_till_done()

    assert coordinator.last_update_success is False
