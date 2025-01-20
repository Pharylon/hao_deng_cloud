"""Hao Deng Lights Integration."""

import asyncio
import logging
from typing import Literal

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.light import LightEntity

from .const import DOMAIN
from .light import MyRGBLight

PLATFORMS = [LIGHT_DOMAIN, SENSOR_DOMAIN]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config) -> bool:
    hass.data[DOMAIN] = {}
    # Return boolean to indicate that initialization was successful.
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up the light platform."""

    await hass.config_entries.async_forward_entry_setup(config_entry, "light")

    return True
