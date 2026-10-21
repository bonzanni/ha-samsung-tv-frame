# tests/test_image.py
from dataclasses import replace
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_tv_frame.const import (
    CONF_HOST,
    CONF_MAC,
    CONF_TOKEN,
    DOMAIN,
)

ENTITY = "image.samsung_frame_tv_current_art_image"


async def _setup(hass, mock_device):
    mock_device.art_ready = True
    mock_device.art_generation = 1
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


async def test_image_serves_current_art_thumbnail(hass, mock_device):
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = True
    mock_device.async_get_current_art.return_value = "MY_F0034"
    mock_device.async_get_art_thumbnail.return_value = b"jpeg-bytes"
    entry = await _setup(hass, mock_device)
    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.state != "unknown"  # timestamp set since current_art known

    coordinator = entry.runtime_data
    entity = hass.data["image"].get_entity(ENTITY)
    image = await entity.async_image()
    assert image == b"jpeg-bytes"
    mock_device.async_get_art_thumbnail.assert_awaited_once_with("MY_F0034")

    # Second call is served from cache — no new fetch.
    await entity.async_image()
    assert mock_device.async_get_art_thumbnail.await_count == 1

    # Art change invalidates the cache and bumps the timestamp.
    mock_device.async_get_art_thumbnail.return_value = b"jpeg-2"
    coordinator.handle_art_event(
        "d2d_service_message",
        {"event": "image_selected", "content_id": "MY_F0042"},
    )
    assert await entity.async_image() == b"jpeg-2"
    assert mock_device.async_get_art_thumbnail.await_count == 2


async def test_image_serves_placeholder_when_thumbnail_refused(hass, mock_device):
    """A refused thumbnail (store art was refused in July 2026) must serve the
    bundled placeholder instead of a broken image."""
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = True
    mock_device.async_get_current_art.return_value = "SAM-S1110879"
    mock_device.async_get_art_thumbnail.return_value = None
    await _setup(hass, mock_device)
    entity = hass.data["image"].get_entity(ENTITY)
    image = await entity.async_image()
    assert image is not None
    assert image[:3] == b"\xff\xd8\xff"  # bundled JPEG placeholder


async def test_failed_fetch_for_a_new_artwork_serves_the_placeholder(
    hass, mock_device
):
    """Issue #13: never show a real, plausible, *wrong* artwork.

    A failed fetch used to serve whichever artwork last succeeded, with
    nothing saying it was stale. The placeholder is honest.
    """
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = True
    mock_device.async_get_current_art.return_value = "MY_F0034"
    mock_device.async_get_art_thumbnail.return_value = b"jpeg-bytes"
    entry = await _setup(hass, mock_device)
    entity = hass.data["image"].get_entity(ENTITY)
    assert await entity.async_image() == b"jpeg-bytes"

    mock_device.async_get_art_thumbnail.reset_mock()
    mock_device.async_get_art_thumbnail.return_value = None
    entry.runtime_data.handle_art_event(
        "d2d_service_message",
        {"event": "image_selected", "content_id": "MY_F0042"},
    )
    image = await entity.async_image()
    assert image != b"jpeg-bytes"
    assert image[:3] == b"\xff\xd8\xff"  # bundled JPEG placeholder
    mock_device.async_get_art_thumbnail.assert_awaited_once_with("MY_F0042")

    # It retries on the next request rather than giving up on that artwork.
    mock_device.async_get_art_thumbnail.return_value = b"jpeg-42"
    assert await entity.async_image() == b"jpeg-42"


async def test_last_artwork_is_kept_while_the_tv_reports_none(hass, mock_device):
    """With no current artwork known (TV off, art channel down), the last
    fetched artwork is still the last thing that was on the wall."""
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = True
    mock_device.async_get_current_art.return_value = "MY_F0034"
    mock_device.async_get_art_thumbnail.return_value = b"jpeg-bytes"
    entry = await _setup(hass, mock_device)
    entity = hass.data["image"].get_entity(ENTITY)
    assert await entity.async_image() == b"jpeg-bytes"

    coordinator = entry.runtime_data
    coordinator.async_set_updated_data(replace(coordinator.data, current_art=None))
    await hass.async_block_till_done()
    assert await entity.async_image() == b"jpeg-bytes"


async def test_failed_fetch_does_not_keep_bumping_the_timestamp(hass, mock_device):
    """Issue #13: the timestamp tracked the last *successful* fetch, so while
    fetches failed every poll moved it and made the frontend refetch."""
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = True
    mock_device.async_get_current_art.return_value = "SAM-S1110879"
    mock_device.async_get_art_thumbnail.return_value = None
    entry = await _setup(hass, mock_device)
    entity = hass.data["image"].get_entity(ENTITY)
    await entity.async_image()
    before = hass.states.get(ENTITY).state

    # Unrelated updates (volume, mute, settings) keep arriving while the
    # same artwork is shown and its fetch keeps failing.
    coordinator = entry.runtime_data
    for volume in (10, 11, 12):
        coordinator.async_set_updated_data(
            replace(coordinator.data, volume_level=volume / 100)
        )
        await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == before


async def test_entity_picture_changes_with_the_artwork(
    hass, mock_device, hass_client_no_auth
):
    """The small picture (state-badge) loads `entity_picture` as-is.

    Core's URL only carries the access token, which rotates every 5 minutes,
    so with a faster slideshow the badge kept showing an old artwork while the
    more-info dialog (which appends `&state=`) showed the right one. The URL
    must change with the artwork, stay put otherwise, and still load.
    """
    mock_device.async_device_info.return_value = {"PowerState": "on"}
    mock_device.async_get_artmode.return_value = True
    mock_device.async_get_current_art.return_value = "MY_F0034"
    mock_device.async_get_art_thumbnail.return_value = b"jpeg-bytes"
    entry = await _setup(hass, mock_device)
    coordinator = entry.runtime_data
    first = hass.states.get(ENTITY).attributes["entity_picture"]

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["entity_picture"] == first

    coordinator.handle_art_event(
        "d2d_service_message",
        {"event": "image_selected", "content_id": "MY_F0042"},
    )
    await hass.async_block_till_done()
    second = hass.states.get(ENTITY).attributes["entity_picture"]
    assert second != first

    client = await hass_client_no_auth()
    response = await client.get(second)
    assert response.status == 200
    assert await response.read() == b"jpeg-bytes"
