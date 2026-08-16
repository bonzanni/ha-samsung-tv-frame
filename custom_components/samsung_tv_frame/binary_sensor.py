"""Binary sensors for Samsung Frame TV."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_MAC
from .coordinator import FrameConfigEntry, FrameCoordinator
from .entity import FrameEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(
        [
            FrameArtModeBinarySensor(entry.runtime_data),
            FrameConnectionBinarySensor(entry.runtime_data),
        ]
    )


class FrameArtModeBinarySensor(FrameEntity, BinarySensorEntity):
    """True when the TV is displaying art mode."""

    _attr_translation_key = "art_mode"
    _attr_name = "Art mode"

    def __init__(self, coordinator: FrameCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.data[CONF_MAC]}_art_mode"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.art_mode


class FrameConnectionBinarySensor(FrameEntity, BinarySensorEntity):
    """Whether the TV answered the integration's REST heartbeat.

    This is the one entity that can say "we cannot see the TV" out loud.
    Everything else answers the different question of what the TV is doing,
    and an unreachable TV is published as OFF there — a reasonable inference
    that is indistinguishable from a network fault, a DHCP move, a crashed
    Tizen, or the panel having gone to sleep.

    Deliberately undebounced: the 2-poll OFF debounce exists to stabilise the
    mode, and applying it here would hide exactly the short outages this
    entity exists to reveal. Automations that want persistence use `for:`.
    """

    _attr_translation_key = "connection"
    _attr_name = "Connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: FrameCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_MAC]}_connection"
        )

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.reachable
