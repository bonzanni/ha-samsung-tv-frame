"""Image entity showing the artwork currently displayed on the Frame."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_MAC
from .coordinator import FrameConfigEntry, FrameCoordinator
from .entity import FrameEntity

PARALLEL_UPDATES = 0

# Shown when the thumbnail for the current artwork cannot be fetched — a
# designed card beats both the frontend's broken-image icon and a picture of
# some other artwork (#13). Store artworks were refused in July 2026 and served
# on 2026-10-20 with an active Art Store subscription.
_PLACEHOLDER_PATH = Path(__file__).parent / "placeholder.jpg"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FrameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FrameCurrentArtImage(entry.runtime_data, hass)])


class FrameCurrentArtImage(FrameEntity, ImageEntity):
    """Thumbnail of the current artwork, refreshed when the selection changes."""

    _attr_translation_key = "current_art_image"
    _attr_name = "Current art image"
    _attr_content_type = "image/jpeg"

    def __init__(self, coordinator: FrameCoordinator, hass: HomeAssistant) -> None:
        FrameEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = (
            f"{coordinator.config_entry.data[CONF_MAC]}_current_art_image"
        )
        self._fetched_id: str | None = None
        self._fetched_image: bytes | None = None
        self._placeholder: bytes | None = None
        # The artwork image_last_updated refers to — tracked apart from the
        # last successful fetch, so a failing fetch does not re-bump it.
        self._shown_id: str | None = None
        if coordinator.data and coordinator.data.current_art:
            self._shown_id = coordinator.data.current_art
            self._attr_image_last_updated = dt_util.utcnow()

    @property
    def entity_picture(self) -> str | None:
        """Core's URL, versioned by the artwork it shows.

        Core's URL only carries the access token, which rotates every 5
        minutes. The more-info dialog appends `&state=` itself, but the
        state badge loads `entity_picture` as-is, so with a faster slideshow
        the badge kept showing an old artwork. The proxy ignores extra query
        parameters.
        """
        url = super().entity_picture
        if url is None or self.image_last_updated is None:
            return url
        return f"{url}&v={self.image_last_updated.timestamp()}"

    @callback
    def _handle_coordinator_update(self) -> None:
        content_id = self.coordinator.data.current_art
        # Bump the timestamp only on a real change: the frontend refetches
        # the proxied image whenever image_last_updated moves.
        if content_id and content_id != self._shown_id:
            self._shown_id = content_id
            self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        content_id = self.coordinator.data.current_art
        if content_id is None:
            # Nothing newer is known (TV off, art channel down): the last
            # artwork fetched is still the last one that was on the wall.
            return self._fetched_image or await self._async_placeholder()
        if content_id == self._fetched_id and self._fetched_image is not None:
            return self._fetched_image
        image = await self.coordinator.device.async_get_art_thumbnail(content_id)
        if image is None:
            # Never the previous artwork: that is a real, plausible, wrong
            # picture (#13). The next request retries the fetch.
            return await self._async_placeholder()
        self._fetched_id = content_id
        self._fetched_image = image
        return image

    async def _async_placeholder(self) -> bytes:
        if self._placeholder is None:
            self._placeholder = await self.hass.async_add_executor_job(
                _PLACEHOLDER_PATH.read_bytes
            )
        return self._placeholder
