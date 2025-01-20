import asyncio
import logging
import colorsys
import math
import time

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .mqtt_connector import MqttConnector
from .pocos import Device
from .rest_api_connector import RestApiConnector
from .color_helper import get_rgb_distance

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, add_entities: AddEntitiesCallback
) -> bool:
    """Set up the light platform."""
    _LOGGER.warning("DOMAIN DATA %s", repr(config_entry.data))

    rest_connector = RestApiConnector(
        config_entry.data["username"],
        config_entry.data["password"],
        config_entry.data["country"],
    )
    await rest_connector.connect()
    devices: list[Device] = await rest_connector.devices()
    controlData = await rest_connector.get_mqtt_control_data()
    mqtt_connector = MqttConnector(controlData, config_entry.data["country"])
    mqtt_connector.connect()
    while mqtt_connector.client_connected is False:
        await asyncio.sleep(0.1)

    lights = []
    for device in devices:
        if device.wiringType == 0:
            continue
        light = MyRGBLight(config_entry, device, mqtt_connector)
        lights.append(light)

    add_entities(lights)

    return True


class MyRGBLight(LightEntity):
    def __init__(
        self, config_entry: ConfigEntry, device: Device, mqtt_connector: MqttConnector
    ):
        """Initialize the light."""
        _LOGGER.info("Initializing Light %s", device.displayName)
        self._config_entry = config_entry
        self._mqtt_connector = mqtt_connector
        self._attr_unique_id = device.uniID  # Use config entry ID for uniqueness
        self._attr_name = device.displayName
        self._mesh_id = device.meshAddress
        self._is_on = False
        self._rgb_color = (255, 0, 0)  # Initial color
        self._attr_supported_color_modes = {
            ColorMode.RGB,
            ColorMode.COLOR_TEMP,
            ColorMode.BRIGHTNESS,
            ColorMode.ONOFF,
        }
        self._attr_color_mode = ColorMode.RGB
        self._brightness = 255
        self._attr_should_poll = False
        self._ignore_next_update = False
        self._last_update = 0

        def update_light(a, d):
            _LOGGER.info("update_light: A: %d, D: %s", a, d)
            if a == self._mesh_id:
                _LOGGER.info("Updating Light %s", self._attr_name)
                self.update_light(d)

        mqtt_connector.subscribe(update_light)

    @property
    def is_on(self) -> bool:
        """Return True if light is on."""
        return self._is_on

    def get_base_colors(self, rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        """Get what the colors would be at brightness 100%."""
        multiplier = max(rgb) / 255
        # brightest_color_value = max(rgb[0], rgb[1], rgb[2])
        adjusted_colors = []
        for color in rgb:
            adjusted_value = min(math.ceil(color / multiplier), 255)
            adjusted_colors.append(adjusted_value)
        return adjusted_colors

    def normalize_colors(self, red: int, green: int, blue: int) -> list[int]:
        # _LOGGER.info("Initial Values %d %d %d %d", red, green, blue, brightness)
        # hsv = colorsys.rgb_to_hsv(red, green, blue)
        # newRgb = colorsys.hsv_to_rgb(hsv[0], hsv[1], brightness)
        # _LOGGER.info("New Values %d %d %d", red, green, blue)
        if red > 0 and red < 20:
            red = red - min([10, red])
        if green > 0 and green < 20:
            green = green - min([10, green])
        if blue > 0 and blue < 20:
            blue = blue - min([10, blue])

        # adjusted = [
        #     int(red * brightness / 255),
        #     int(green * brightness / 255),
        #     int(blue * brightness / 255),
        # ]
        # _LOGGER.info(
        #     "Final Values %d %d %d %d",
        #     adjusted[0],
        #     adjusted[1],
        #     adjusted[2],
        #     brightness,
        # )
        return [red, green, blue]

    def update_light(self, rgb: tuple[int, int, int]):
        """Fetch new state data for this light."""
        # I haven't been able to figure out the logic that exactly
        # converts their HSL-ish data into real RGB. So if it's
        # "close enough" we don't udpate, becuase we already have
        # the correct color. We should really only update this way
        # if the new color was created outside of Home Assistant.
        # In this case, at least we'll have something close in HA.
        _LOGGER.info("Update_light %s", repr(rgb))
        if (time.time() - self._last_update) < 10:
            _LOGGER.info("Skipping update, too soon after we issued a command")
            return  # We just updated the light, this is probably just the echo of that.
        if rgb[0] == 0 and rgb[1] == 0 and rgb[2] == 0:
            self.turn_off()
            return
        rgb_distance = get_rgb_distance(
            [
                self._rgb_color[0],
                self._rgb_color[1],
                self._rgb_color[2],
            ],
            rgb,
        )
        if rgb_distance < 50:  # the color is 'close enough', we don't need to update
            return
        _LOGGER.info("UPDATING from Hao Deng to %s", repr(rgb))
        self._is_on = True
        self._rgb_color = rgb
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""

        _LOGGER.info("TURN ON")
        if ATTR_RGB_COLOR in kwargs:
            self._brightness = 255
            normalized_colors = self.normalize_colors(
                kwargs[ATTR_RGB_COLOR][0],
                kwargs[ATTR_RGB_COLOR][1],
                kwargs[ATTR_RGB_COLOR][2],
            )
            self._rgb_color = normalized_colors
            _LOGGER.info("BRIGTHNESS %s", self._brightness)
            _LOGGER.info("COLOR %s", repr(kwargs[ATTR_RGB_COLOR]))
            # self._rgb_color = kwargs[ATTR_RGB_COLOR]
            _LOGGER.info("COLOR %s", repr(self._rgb_color))
            # Send command to your RGB light to set the color
        elif ATTR_BRIGHTNESS in kwargs:
            _LOGGER.info("BRIGTHNESS %s", repr(kwargs[ATTR_BRIGHTNESS]))
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            base_colors = self.get_base_colors(self._rgb_color)
            new_rgb = []
            for color in base_colors:
                color = color * self._brightness / 255
                new_rgb.append(color)
            self._rgb_color = new_rgb
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            _LOGGER.info("COLOR TEMP %s", repr(kwargs[ATTR_COLOR_TEMP_KELVIN]))
            self._mqtt_connector.set_color_temp(
                self._mesh_id, kwargs[ATTR_COLOR_TEMP_KELVIN]
            )
            return
        else:
            await self.just_turn_on()
            return

        self._mqtt_connector.set_color(
            self._mesh_id,
            self._rgb_color[0],
            self._rgb_color[1],
            self._rgb_color[2],
        )
        self._is_on = True
        # self._ignore_next_update = True
        self._last_update = time.time()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        _LOGGER.info("TURN OFF")
        self._mqtt_connector.turn_off(self._mesh_id)
        self._is_on = False
        # Send command to your RGB light to turn off
        self._last_update = time.time()
        self.async_write_ha_state()

    async def just_turn_on(self) -> None:
        """Turn the light off."""
        _LOGGER.info("JUST TURN ON")
        self._mqtt_connector.turn_on(self._mesh_id)
        self._is_on = True
        # Send command to your RGB light to turn off
        self._last_update = time.time()
        self.async_write_ha_state()

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return the rgb color value [int, int, int]."""
        return self._rgb_color

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self._brightness
