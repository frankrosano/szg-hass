"""Sub-Zero Group integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import SZGCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Sub-Zero Group from a config entry."""
    coordinator = SZGCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start SignalR after HA is fully started so it doesn't block bootstrap
    async def _start_signalr_when_ready(_event=None) -> None:
        coordinator.start_signalr_background()

    if hass.is_running:
        coordinator.start_signalr_background()
    else:
        entry.async_on_unload(
            hass.bus.async_listen_once(
                "homeassistant_started", _start_signalr_when_ready
            )
        )

    # React to config entry updates (e.g., PIN added via options flow)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates (e.g., new PIN added)."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_apply_pin_updates()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
