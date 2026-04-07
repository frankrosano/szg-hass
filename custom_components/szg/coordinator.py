"""Data coordinator for Sub-Zero Group integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from pyszg import (
    Appliance,
    ApplianceType,
    ModuleGeneration,
    SZGClient,
    SZGCloudAuth,
    SZGCloudClient,
    SZGCloudSignalR,
    TokenSet,
)

from .const import DOMAIN, CONF_TOKENS, CONF_DEVICE_PINS

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=30)


class SZGDeviceConnection:
    """Manages the connection to a single appliance."""

    def __init__(
        self,
        device_info: dict[str, Any],
        cloud_client: SZGCloudClient,
    ) -> None:
        self.device_id: str = device_info["id"]
        self.device_info = device_info
        self.cloud_client = cloud_client
        self.local_client: SZGClient | None = None
        self.appliance = Appliance()
        self.pin: str | None = None

        # Parse type info from the device list
        type_str = device_info.get("applianceId", "")
        self.appliance_type = ApplianceType.from_type_string(type_str)
        self.module_generation = ModuleGeneration.from_type_string(type_str)

    @property
    def name(self) -> str:
        return (
            self.device_info.get("name")
            or self.appliance.model
            or self.device_info.get("applianceId", "Unknown")
        )

    @property
    def supports_local(self) -> bool:
        return self.module_generation.supports_local_ip

    @property
    def has_local(self) -> bool:
        return self.local_client is not None

    def setup_local(self, ip: str, pin: str) -> None:
        """Set up local IP connection for a CAT device."""
        self.pin = pin
        self.local_client = SZGClient(ip, pin=pin)
        _LOGGER.info("Local connection configured for %s at %s", self.name, ip)

    async def async_refresh(self, hass: HomeAssistant) -> Appliance:
        """Refresh appliance state using the best available method."""
        if self.has_local:
            try:
                await hass.async_add_executor_job(self.local_client.refresh)
                self.appliance = self.local_client.appliance
                return self.appliance
            except Exception as exc:
                _LOGGER.warning(
                    "Local refresh failed for %s, falling back to cloud: %s",
                    self.name, exc,
                )

        # Cloud fallback (or primary for Saber/NGIX)
        try:
            self.appliance = await hass.async_add_executor_job(
                self.cloud_client.get_appliance_state, self.device_id
            )
        except Exception as exc:
            _LOGGER.error("Cloud refresh failed for %s: %s", self.name, exc)

        return self.appliance

    async def async_set_property(
        self, hass: HomeAssistant, name: str, value: Any
    ) -> None:
        """Set a property using the best available method."""
        if self.has_local:
            try:
                await hass.async_add_executor_job(
                    self.local_client.set_property, name, value
                )
                return
            except Exception as exc:
                _LOGGER.warning(
                    "Local set failed for %s, falling back to cloud: %s",
                    self.name, exc,
                )

        await hass.async_add_executor_job(
            self.cloud_client.set_property, self.device_id, name, value
        )

    async def async_display_pin(self, hass: HomeAssistant) -> None:
        """Request the appliance to display its PIN."""
        if self.has_local:
            await hass.async_add_executor_job(self.local_client.display_pin)
        else:
            # Use cloud to send display_pin command
            await hass.async_add_executor_job(
                self.cloud_client.send_command,
                self.device_id,
                "display_pin",
                {"duration": 20},
            )


class SZGCoordinator(DataUpdateCoordinator[dict[str, Appliance]]):
    """Coordinate data updates for all Sub-Zero Group appliances."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
        )
        self.entry = entry
        self._auth = SZGCloudAuth()
        self._tokens: TokenSet | None = None
        self._cloud_client: SZGCloudClient | None = None
        self._signalr: SZGCloudSignalR | None = None
        self._signalr_task: asyncio.Task | None = None
        self.devices: dict[str, SZGDeviceConnection] = {}

    async def async_setup(self) -> None:
        """Initialize cloud auth and discover devices."""
        token_data = self.entry.data.get(CONF_TOKENS, {})
        self._tokens = TokenSet.from_dict(token_data)
        self._tokens = await self.hass.async_add_executor_job(
            self._auth.ensure_valid, self._tokens
        )

        # Save refreshed tokens
        new_data = dict(self.entry.data)
        new_data[CONF_TOKENS] = self._tokens.to_dict()
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)

        self._cloud_client = SZGCloudClient(self._tokens, self._auth)

        # Discover devices
        device_list = await self.hass.async_add_executor_job(
            self._cloud_client.get_devices
        )

        pins = self.entry.data.get(CONF_DEVICE_PINS, {})

        for dev_info in device_list:
            device_id = dev_info["id"]
            conn = SZGDeviceConnection(dev_info, self._cloud_client)
            self.devices[device_id] = conn

            # Set up local connection if we have a PIN and the device supports it
            if conn.supports_local and device_id in pins:
                # Get IP from a cloud state fetch
                try:
                    appliance = await self.hass.async_add_executor_job(
                        self._cloud_client.get_appliance_state, device_id
                    )
                    ip = appliance.ip_address
                    if ip:
                        conn.setup_local(ip, pins[device_id])
                except Exception as exc:
                    _LOGGER.warning("Failed to get IP for %s: %s", device_id, exc)

        # Start SignalR for real-time updates
        await self._start_signalr()

    async def _start_signalr(self) -> None:
        """Start SignalR connection for real-time push updates."""
        if SZGCloudSignalR is None:
            _LOGGER.info("websockets not installed, using polling only")
            return

        self._signalr = SZGCloudSignalR(self._tokens, self._auth)

        async def on_signalr_update(device_id: str, msg_type: int, data: dict) -> None:
            """Handle a SignalR push update."""
            if device_id in self.devices:
                conn = self.devices[device_id]
                if msg_type == 1:
                    conn.appliance.update_from_response(data)
                elif msg_type == 2:
                    props = data.get("props", data)
                    conn.appliance.update_from_response(props)
                self.async_set_updated_data(
                    {did: c.appliance for did, c in self.devices.items()}
                )

        device_ids = list(self.devices.keys())
        self._signalr_task = self.hass.async_create_task(
            self._signalr.connect(
                device_ids=device_ids,
                callback=on_signalr_update,
            )
        )

    async def _async_update_data(self) -> dict[str, Appliance]:
        """Poll all devices for current state (fallback when SignalR misses)."""
        for conn in self.devices.values():
            await conn.async_refresh(self.hass)
        return {did: conn.appliance for did, conn in self.devices.items()}

    async def async_shutdown(self) -> None:
        """Clean up connections."""
        if self._signalr:
            await self._signalr.disconnect()
        if self._signalr_task:
            self._signalr_task.cancel()
        for conn in self.devices.values():
            if conn.local_client:
                conn.local_client.disconnect_push()
