# tests/test_device_trigger.py
from unittest.mock import patch

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.samsung_tv_frame.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.samsung_tv_frame.device_trigger import async_get_triggers


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


async def test_get_triggers_lists_mode_transitions(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = False
    await _setup(hass, mock_device)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, "02:00:00:00:00:01")}
    )
    assert device is not None

    triggers = await async_get_triggers(hass, device.id)
    types = {t["type"] for t in triggers}
    # The three mode triggers are the shipped contract: adding contact
    # triggers must not disturb them.
    assert types >= {"turned_off", "started_watching", "entered_art_mode"}
    assert all(t["domain"] == DOMAIN for t in triggers)


async def test_get_triggers_empty_for_unknown_device(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = False
    await _setup(hass, mock_device)
    device_registry = dr.async_get(hass)
    other = device_registry.async_get_or_create(
        config_entry_id=next(iter(hass.config_entries.async_entry_ids())),
        identifiers={("other_domain", "xyz")},
    )
    assert await async_get_triggers(hass, other.id) == []


async def _setup_with_device(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = False
    await _setup(hass, mock_device)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(
        identifiers={(DOMAIN, "02:00:00:00:00:01")}
    )
    assert device is not None
    return device


async def _arm(hass, device, trigger_type, entity_id, event_name):
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    assert entry is not None
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "trigger": {
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": device.id,
                        "entity_id": entry.id,
                        "type": trigger_type,
                    },
                    "action": {"event": event_name},
                }
            ]
        },
    )
    await hass.async_block_till_done()
    return async_capture_events(hass, event_name)


async def test_get_triggers_lists_contact_transitions(hass, mock_device):
    device = await _setup_with_device(hass, mock_device)

    triggers = await async_get_triggers(hass, device.id)
    types = {t["type"] for t in triggers}
    assert types == {
        "turned_off",
        "started_watching",
        "entered_art_mode",
        "lost_contact",
        "regained_contact",
    }


async def test_lost_contact_fires_from_unavailable_too(hass, mock_device):
    """A loss that begins while the coordinator is failing is still a loss."""
    device = await _setup_with_device(hass, mock_device)
    entity_id = "binary_sensor.samsung_frame_tv_connection"
    events = await _arm(hass, device, "lost_contact", entity_id, "lost")

    hass.states.async_set(entity_id, "on")
    await hass.async_block_till_done()
    hass.states.async_set(entity_id, "off")
    await hass.async_block_till_done()
    assert len(events) == 1

    hass.states.async_set(entity_id, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(entity_id, "off")
    await hass.async_block_till_done()
    assert len(events) == 2


async def test_regained_contact_ignores_a_coordinator_hiccup(hass, mock_device):
    """unavailable -> on is Home Assistant recovering, not the TV."""
    device = await _setup_with_device(hass, mock_device)
    entity_id = "binary_sensor.samsung_frame_tv_connection"
    events = await _arm(hass, device, "regained_contact", entity_id, "regained")

    hass.states.async_set(entity_id, "on")
    await hass.async_block_till_done()
    hass.states.async_set(entity_id, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(entity_id, "on")
    await hass.async_block_till_done()
    assert len(events) == 0

    hass.states.async_set(entity_id, "off")
    await hass.async_block_till_done()
    hass.states.async_set(entity_id, "on")
    await hass.async_block_till_done()
    assert len(events) == 1
