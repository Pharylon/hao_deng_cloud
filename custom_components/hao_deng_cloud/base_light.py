"""Base light entity for Hao Deng Cloud integration."""

import asyncio
import colorsys
import logging
import time

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry

from .mqtt_connector import MqttConnector

_LOGGER = logging.getLogger(__name__)


class HaoDengBaseLight(LightEntity):
    """Base class for Hao Deng lights and group lights."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        mesh_id: int,
        unique_id: str,
        name: str,
        mqtt_connector: MqttConnector,
        initial_available: bool = False,
    ) -> None:
        """Initialize the base light."""
        self._config_entry = config_entry
        self._mqtt_connector = mqtt_connector
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._mesh_id = mesh_id
        self._attr_is_on = False
        self._rgb_color = (255, 0, 0)  # Initial color
        self._attr_supported_color_modes = [
            ColorMode.HS,
            ColorMode.COLOR_TEMP,
        ]
        self._attr_color_mode = ColorMode.UNKNOWN
        self._attr_brightness = 255
        self._attr_hs_color = None
        self._attr_color_temp_kelvin = None
        self._attr_should_poll = False
        self._ignore_next_update = False
        self._last_update = 0

        self._attr_max_color_temp_kelvin = 6535
        self._attr_min_color_temp_kelvin = 2500

        self._attr_available = initial_available

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._attr_is_on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        return self._attr_brightness

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the current color mode."""
        return self._attr_color_mode

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the current HS color."""
        return self._attr_hs_color

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the current color temperature in Kelvin."""
        return self._attr_color_temp_kelvin

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._attr_available

    def _hsv_to_rgb(self, hs: tuple[float, float], brightness: float) -> list[float]:
        brightness_scale_100 = brightness / 255
        rgb_float = colorsys.hsv_to_rgb(hs[0] / 365, hs[1] / 100, brightness_scale_100)
        rgb = [rgb_float[0] * 255, rgb_float[1] * 255, rgb_float[2] * 255]
        return rgb

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on, set options."""
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        self._attr_brightness = self._attr_brightness or 255
        if ATTR_HS_COLOR in kwargs:
            self._attr_color_mode = ColorMode.HS
            self._attr_hs_color = kwargs[ATTR_HS_COLOR]
            rgb = self._hsv_to_rgb(self._attr_hs_color, self._attr_brightness)
            if getattr(self, "hass", None) is not None:
                self.async_write_ha_state()
            await self._mqtt_connector.set_color(self._mesh_id, rgb[0], rgb[1], rgb[2])
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            if getattr(self, "hass", None) is not None:
                self.async_write_ha_state()
            await self._mqtt_connector.set_color_temp(
                self._mesh_id,
                self._attr_color_temp_kelvin,
                self._attr_brightness,
            )
        elif ATTR_BRIGHTNESS in kwargs:
            if getattr(self, "hass", None) is not None:
                self.async_write_ha_state()
            if self._attr_color_mode == ColorMode.COLOR_TEMP:
                await self._mqtt_connector.set_color_temp(
                    self._mesh_id, self._attr_color_temp_kelvin, self._attr_brightness
                )
            elif self._attr_color_mode == ColorMode.HS:
                rgb = self._hsv_to_rgb(self._attr_hs_color, self._attr_brightness)
                await self._mqtt_connector.set_color(
                    self._mesh_id, rgb[0], rgb[1], rgb[2]
                )
        else:
            _LOGGER.info("Just turned on %s ", self._attr_name)
            if getattr(self, "hass", None) is not None:
                self.async_write_ha_state()
            await self._mqtt_connector.turn_on(self._mesh_id)
            if self._attr_color_mode == ColorMode.UNKNOWN:
                # Light was off, so we don't know its color state. Ask the cloud for new color
                await asyncio.sleep(0.1)
                self._mqtt_connector.request_status()
        self._last_update = time.time()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        _LOGGER.info("TURN OFF ASYNC %s", self._attr_name)
        self._attr_is_on = False
        if getattr(self, "hass", None) is not None:
            self.async_write_ha_state()
        await self._mqtt_connector.turn_off(self._mesh_id)
        self._last_update = time.time()
