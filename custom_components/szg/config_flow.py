"""Config flow for Sub-Zero Group integration."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

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
        self._code_challenge: str = ""
        self._state: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — open browser for OAuth login."""
        if user_input is not None:
            # User clicked submit, open the browser
            self._code_verifier = secrets.token_urlsafe(64)[:128]
            self._code_challenge = base64.urlsafe_b64encode(
                hashlib.sha256(self._code_verifier.encode()).digest()
            ).rstrip(b"=").decode()
            self._state = secrets.token_urlsafe(32)

            auth_url = SZGCloudAuth.get_authorize_url(
                self._code_challenge, self._state
            )

            return self.async_external_step(step_id="auth_callback", url=auth_url)

        return self.async_show_form(step_id="user")

    async def async_step_auth_callback(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the OAuth callback with the redirect URL."""
        if user_input is None:
            return self.async_show_form(
                step_id="auth_callback",
                data_schema=vol.Schema({
                    vol.Required("redirect_url"): str,
                }),
            )

        redirect_url = user_input.get("redirect_url", "")
        errors = {}

        # Extract auth code from redirect URL
        import urllib.parse
        if "?" in redirect_url:
            qs = redirect_url.split("?", 1)[1]
            params = urllib.parse.parse_qs(qs)
        else:
            params = {}

        if "code" not in params:
            errors["base"] = "invalid_url"
            return self.async_show_form(
                step_id="auth_callback",
                data_schema=vol.Schema({
                    vol.Required("redirect_url"): str,
                }),
                errors=errors,
            )

        code = params["code"][0]

        try:
            tokens = await self.hass.async_add_executor_job(
                self._auth.exchange_code, code, self._code_verifier
            )
        except Exception:
            _LOGGER.exception("Authentication failed")
            errors["base"] = "auth_failed"
            return self.async_show_form(
                step_id="auth_callback",
                data_schema=vol.Schema({
                    vol.Required("redirect_url"): str,
                }),
                errors=errors,
            )

        # Check if this account is already configured
        await self.async_set_unique_id(tokens.user_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=tokens.name or tokens.email or "Sub-Zero Group",
            data={
                CONF_TOKENS: tokens.to_dict(),
                CONF_DEVICE_PINS: {},
            },
        )

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
        """Show device PIN entry."""
        return await self.async_step_device_pin(user_input)

    async def async_step_device_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle PIN entry for a device."""
        errors = {}

        if user_input is not None:
            pin = user_input.get("pin", "").strip()
            device_id = user_input.get("device_id", "")

            if len(pin) != 6 or not pin.isdigit():
                errors["base"] = "invalid_pin"
            else:
                # Store the PIN
                new_data = dict(self._config_entry.data)
                pins = dict(new_data.get(CONF_DEVICE_PINS, {}))
                pins[device_id] = pin
                new_data[CONF_DEVICE_PINS] = pins

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="device_pin",
            data_schema=vol.Schema({
                vol.Required("device_id"): str,
                vol.Required("pin"): str,
            }),
            errors=errors,
        )
