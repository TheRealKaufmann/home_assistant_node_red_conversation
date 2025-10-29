"""Config flow for the integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    TextSelector,
)

from . import (
    CONF_ERROR_MESSAGE,
    CONF_TIMEOUT,
    CONF_WEBHOOK_RECEIVE_ID,
    CONF_WEBHOOK_SEND_ID,
    DEFAULT_ERROR_MESSAGE,
    DEFAULT_NAME,
    DEFAULT_TIMEOUT,
    DEFAULT_WEBHOOK_SEND_ID,
    DEFAULT_WEBHOOK_RECEIVE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        return self.async_create_entry(
            title=user_input.get(CONF_NAME, DEFAULT_NAME), data=user_input
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options or {}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WEBHOOK_SEND_ID,
                    default=options.get(CONF_WEBHOOK_SEND_ID, DEFAULT_WEBHOOK_SEND_ID),
                ): TextSelector(),
                vol.Optional(
                    CONF_WEBHOOK_RECEIVE_ID,
                    default=options.get(CONF_WEBHOOK_RECEIVE_ID, DEFAULT_WEBHOOK_RECEIVE_ID),
                ): TextSelector(),
                vol.Optional(
                    CONF_TIMEOUT,
                    default=options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): NumberSelector(NumberSelectorConfig(min=1, max=300, step=1)),
                vol.Optional(
                    CONF_ERROR_MESSAGE,
                    default=options.get(CONF_ERROR_MESSAGE, DEFAULT_ERROR_MESSAGE),
                ): TextSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
