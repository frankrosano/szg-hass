"""Sub-Zero Group integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_DEVICE_PINS
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older config entries to the current schema.

    v1 -> v2: device_pins moves from entry.data to entry.options. The
    options flow saves to entry.options for new PINs going forward, and
    the coordinator reads from entry.options on load.
    """
    if entry.version == 1:
        new_data = dict(entry.data)
        device_pins = new_data.pop(CONF_DEVICE_PINS, {})
        new_options = dict(entry.options)
        if device_pins and CONF_DEVICE_PINS not in new_options:
            new_options[CONF_DEVICE_PINS] = device_pins

        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            options=new_options,
            version=2,
        )
        _LOGGER.info(
            "Migrated config entry %s from v1 to v2 (device_pins -> options)",
            entry.entry_id,
        )

    return True


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
