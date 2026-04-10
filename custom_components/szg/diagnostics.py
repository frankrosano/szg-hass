"""Diagnostics support for Sub-Zero Group integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN, CONF_TOKENS, CONF_DEVICE_PINS
from .coordinator import SZGCoordinator

# Keys to redact from diagnostics output for privacy
REDACT_CONFIG = {CONF_TOKENS, CONF_DEVICE_PINS}
REDACT_DEVICE = {"appliance_serial", "ipv4_addr", "device_wlan_id", "ap_ssid", "remote_svc_reg_token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the entire config entry (all devices)."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]

    devices_diag = {}
    for device_id, conn in coordinator.devices.items():
        devices_diag[device_id[:16]] = {
            "appliance_type": str(conn.appliance_type),
            "module_generation": str(conn.module_generation),
            "has_local": conn.has_local,
            "supports_local": conn.supports_local,
            "raw_property_count": len(conn.appliance.raw),
            "raw_properties": async_redact_data(conn.appliance.raw, REDACT_DEVICE),
        }

    return {
        "config_entry": async_redact_data(dict(entry.data), REDACT_CONFIG),
        "devices": devices_diag,
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a specific device."""
    coordinator: SZGCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Find the connection matching this device
    for device_id, conn in coordinator.devices.items():
        if (DOMAIN, device_id) in device.identifiers:
            # Refresh to get the latest state
            await conn.async_refresh(hass)

            return {
                "device_id": device_id,
                "device_name": conn.name,
                "appliance_type": conn.appliance_type.name,
                "module_generation": conn.module_generation.name,
                "has_local_connection": conn.has_local,
                "supports_local": conn.supports_local,
                "model": conn.appliance.model,
                "serial": "**REDACTED**",
                "firmware": {
                    "api": conn.appliance.api_version,
                    "fw": conn.appliance.fw_version,
                },
                "network": {
                    "ip": "**REDACTED**",
                    "mac": "**REDACTED**",
                    "wifi_ssid": "**REDACTED**",
                    "wifi_channel": conn.appliance.wifi_channel,
                    "wifi_rssi": conn.appliance.wifi_rssi,
                },
                "raw_property_count": len(conn.appliance.raw),
                "raw_properties": async_redact_data(
                    conn.appliance.raw, REDACT_DEVICE
                ),
            }

    return {"error": "Device not found in coordinator"}
