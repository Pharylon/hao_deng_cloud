"""Config flow for Hao Deng Lights."""

from collections.abc import Mapping
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_COUNTRY, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN, MAGICHUE_COUNTRY_SERVERS
from .rest_api_connector import RestApiConnector

_LOGGER = logging.getLogger(__name__)


class HaoDengConfigHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    config: Mapping | None = {}

    async def async_step_user(self, user_input) -> None:
        """Set up User."""

        if user_input is None:
            return self.get_user_info_from_dialog()
        username = user_input.get(CONF_USERNAME)
        password = user_input.get(CONF_PASSWORD)
        country = user_input.get(CONF_COUNTRY)
        api_connector = RestApiConnector(username, password, country)
        await api_connector.connect()
        devices = await api_connector.devices()
        if len(devices) == 0:
            return self.async_abort(reason="no_devices_found")
        controlData = await api_connector.get_mqtt_control_data()
        if len(controlData) == 0:
            return self.async_abort(reason="no_control_data_found")
        data = {
            "username": username,
            "password": password,
            "country": country,
        }
        return self.async_create_entry(title=DOMAIN, data=data)

    def get_user_info_from_dialog(self):
        """Get user info from dialog."""
        codes = [x["nationCode"] for x in MAGICHUE_COUNTRY_SERVERS]
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=""): str,
                    vol.Required(CONF_PASSWORD, default=""): str,
                    vol.Required(CONF_COUNTRY): SelectSelector(
                        SelectSelectorConfig(
                            mode=SelectSelectorMode.DROPDOWN,
                            options=codes,
                        )
                    ),
                }
            ),
        )
