"""Config flow for Sub-Zero Group integration."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import urllib.parse
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from pyszg import SZGCloudAuth

from .const import DOMAIN, CONF_TOKENS, CONF_DEVICE_PINS

_LOGGER = logging.getLogger(__name__)


class SZGConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sub-Zero Group."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._auth = SZGCloudAuth()
        self._code_verifier: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Single step: user pastes the redirect URL after logging in."""
        errors = {}

        if user_input is not None:
            redirect_url = user_input.get("redirect_url", "").strip()

            # Extract auth code
            code = None
            if "?" in redirect_url:
                qs = redirect_url.split("?", 1)[1]
                params = urllib.parse.parse_qs(qs)
                if "code" in params:
                    code = params["code"][0]

            if not code:
                errors["base"] = "invalid_url"
            else:
                try:
                    tokens = await self.hass.async_add_executor_job(
                        self._auth.exchange_code, code, self._code_verifier
                    )
                    await self.async_set_unique_id(tokens.user_id)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title="Sub-Zero Group",
                        data={
                            CONF_TOKENS: tokens.to_dict(),
                            CONF_DEVICE_PINS: {},
                        },
                    )
                except Exception:
                    _LOGGER.exception("Authentication failed")
                    errors["base"] = "auth_failed"

        # Generate fresh PKCE values each time the form is shown
        self._code_verifier = secrets.token_urlsafe(64)[:128]
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self._code_verifier.encode()).digest()
        ).rstrip(b"=").decode()
        state = secrets.token_urlsafe(32)
        auth_url = SZGCloudAuth.get_authorize_url(code_challenge, state)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("redirect_url"): str,
            }),
            description_placeholders={"auth_url": auth_url},
            errors=errors,
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> FlowResult:
        """Handle DHCP discovery of a Sub-Zero Group appliance on the network.

        DHCP finds individual appliances by MAC (OUI 00:06:80), but the
        integration is configured per-account (one config entry covers all
        appliances). If any config entry already exists, abort silently.
        Otherwise, prompt the user to set up their account.
        """
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        self.context["title_placeholders"] = {
            "name": discovery_info.hostname or "Sub-Zero Appliance",
        }
        return await self.async_step_user()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SZGOptionsFlow:
        """Get the options flow for this handler."""
        return SZGOptionsFlow(config_entry)


class SZGOptionsFlow(OptionsFlow):
    """Handle options flow for entering device PINs."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._device_id: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Select a device and trigger PIN display."""
        coordinator = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
        if not coordinator:
            return self.async_abort(reason="not_loaded")

        existing_pins = self._config_entry.data.get(CONF_DEVICE_PINS, {})
        eligible = {}
        for device_id, conn in coordinator.devices.items():
            if conn.supports_local:
                label = conn.name
                if device_id in existing_pins:
                    label += " (PIN already set)"
                eligible[device_id] = label

        if not eligible:
            return self.async_abort(reason="no_local_devices")

        if user_input is not None:
            self._device_id = user_input.get("device_id", "")

            # Trigger PIN display on the selected device
            if self._device_id and self._device_id in coordinator.devices:
                conn = coordinator.devices[self._device_id]
                try:
                    await conn.async_display_pin(self.hass)
                except Exception:
                    pass  # PIN display may fail if door is closed

            return await self.async_step_enter_pin()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("device_id"): vol.In(eligible),
            }),
        )

    async def async_step_enter_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Enter the PIN shown on the appliance display."""
        errors = {}

        if user_input is not None:
            pin = user_input.get("pin", "").strip()

            if len(pin) != 6 or not pin.isdigit():
                errors["base"] = "invalid_pin"
            else:
                # Validate the PIN against the appliance before saving
                coordinator = self.hass.data.get(DOMAIN, {}).get(
                    self._config_entry.entry_id
                )
                if coordinator and self._device_id in coordinator.devices:
                    conn = coordinator.devices[self._device_id]
                    ip = conn.appliance.ip_address
                    if not ip:
                        errors["base"] = "cannot_connect"
                    else:
                        from pyszg import SZGClient
                        from pyszg.exceptions import AuthenticationError as PinError

                        try:
                            client = SZGClient(ip, pin=pin)
                            await self.hass.async_add_executor_job(client.refresh)
                        except PinError:
                            errors["base"] = "wrong_pin"
                        except Exception:
                            errors["base"] = "cannot_connect"

                if not errors:
                    new_data = dict(self._config_entry.data)
                    pins = dict(new_data.get(CONF_DEVICE_PINS, {}))
                    pins[self._device_id] = pin
                    new_data[CONF_DEVICE_PINS] = pins

                    self.hass.config_entries.async_update_entry(
                        self._config_entry, data=new_data
                    )
                    return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="enter_pin",
            data_schema=vol.Schema({
                vol.Required("pin"): str,
            }),
            errors=errors,
        )
