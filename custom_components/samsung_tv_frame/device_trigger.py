"""Device triggers for Samsung Frame TV — state transitions in the UI."""
from __future__ import annotations

from typing import NamedTuple

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_FOR,
    CONF_PLATFORM,
    CONF_TYPE,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .models import TvMode


class _Transition(NamedTuple):
    """One trigger: which entity, and which state change on it."""

    # Unique-id suffix identifying the entity this trigger watches.
    suffix: str
    to_state: str
    # Only set where firing out of "unavailable" would be a lie. A state
    # trigger with `to` alone also fires on unavailable -> <state>, which for
    # regained_contact would announce a recovery after nothing worse than a
    # coordinator hiccup. lost_contact deliberately keeps no `from`: a loss
    # that begins while the coordinator is failing is still a real loss, and
    # this also matches how turned_off has always behaved.
    from_state: str | None = None


TRIGGER_TYPES: dict[str, _Transition] = {
    "turned_off": _Transition("_tv_mode", TvMode.OFF),
    "started_watching": _Transition("_tv_mode", TvMode.WATCHING),
    "entered_art_mode": _Transition("_tv_mode", TvMode.ART_MODE),
    "lost_contact": _Transition("_connection", STATE_OFF),
    "regained_contact": _Transition("_connection", STATE_ON, STATE_OFF),
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id_or_uuid,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        vol.Optional(CONF_FOR): cv.positive_time_period_dict,
    }
)


def _entity_by_suffix(
    hass: HomeAssistant, device_id: str, suffix: str
) -> er.RegistryEntry | None:
    registry = er.async_get(hass)
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.platform == DOMAIN and entry.unique_id.endswith(suffix):
            return entry
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device triggers for a Frame TV device."""
    triggers = []
    for trigger, transition in TRIGGER_TYPES.items():
        entry = _entity_by_suffix(hass, device_id, transition.suffix)
        if entry is None:
            continue
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_ENTITY_ID: entry.id,
                CONF_TYPE: trigger,
            }
        )
    return triggers


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """Support an optional 'for' duration on every trigger.

    Notably useful on started_watching: powering off from art mode passes
    through 'watching' for a few seconds, and a small 'for' filters that out.
    """
    return {
        "extra_fields": vol.Schema(
            {vol.Optional(CONF_FOR): cv.positive_time_period_dict}
        )
    }


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a state trigger on the entity this trigger type watches."""
    transition = TRIGGER_TYPES[config[CONF_TYPE]]
    state_config = {
        CONF_PLATFORM: "state",
        CONF_ENTITY_ID: config[CONF_ENTITY_ID],
        state_trigger.CONF_TO: transition.to_state,
    }
    if transition.from_state is not None:
        state_config[state_trigger.CONF_FROM] = transition.from_state
    if CONF_FOR in config:
        state_config[CONF_FOR] = config[CONF_FOR]
    state_config = await state_trigger.async_validate_trigger_config(
        hass, state_config
    )
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )
