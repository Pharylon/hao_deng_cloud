import asyncio
import logging
import colorsys
import math
import time

from homeassistant.components.light import (
    _DEPRECATED_ATTR_KELVIN,
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_COLOR_TEMP_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
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

    rest_connector = RestApiConnector(
        config_entry.data["username"],
        config_entry.data["password"],
        config_entry.data["country"],
    )
    await rest_connector.connect()
    devices: list[Device] = await rest_connector.devices()
    controlData = await rest_connector.get_mqtt_control_data()
    mqtt_connector = MqttConnector(controlData, config_entry.data["country"], devices)
    mqtt_connector.connect()
    while mqtt_connector.client_connected is False:
        await asyncio.sleep(0.1)

    lights = []
    for device in devices:
        if device.wiringType == 0:
            continue
        light = HaoDengLight(config_entry, device, mqtt_connector)
        lights.append(light)

    add_entities(lights)
    mqtt_connector.request_status()  # Get initial status of lights

    return True


class HaoDengLight(LightEntity):
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
        self._attr_supported_color_modes = [
            ColorMode.RGB,
            ColorMode.COLOR_TEMP,
            # ColorMode.BRIGHTNESS,
            # ColorMode.ONOFF,
        ]
        self._attr_color_mode = ColorMode.UNKNOWN
        self._brightness = 255
        self._attr_should_poll = False
        self._ignore_next_update = False
        self._last_update = 0

        self._attr_max_color_temp_kelvin = 6535
        self._attr_min_color_temp_kelvin = 2000

        def update_light(a, d):
            if a == self._mesh_id:
                # _LOGGER.info("Received update for Light %s", self._attr_name)
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

    def normalize_colors(
        self, red: int, green: int, blue: int, brightness: int
    ) -> list[int]:
        adjusted = [
            int(red * brightness / 255),
            int(green * brightness / 255),
            int(blue * brightness / 255),
        ]
        max_color = max(adjusted)
        normalized = []
        for color in adjusted:
            if max_color > 100 and color > 0 and color < 20:
                color = color - min([10, color])
            normalized.append(color)
        return normalized

    def update_light(self, rgb: tuple[int, int, int]):
        """Fetch new state data for this light."""
        # I haven't been able to figure out the logic that exactly
        # converts their HSL-ish data into real RGB. So if it's
        # "close enough" we don't udpate, becuase we already have
        # the correct color. We should really only update this way
        # if the new color was created outside of Home Assistant.
        # In this case, at least we'll have something close in HA.
        # _LOGGER.info("Update_light %s: %s %s", self._attr_name, repr(rgb), self._is_on)
        if (time.time() - self._last_update) < 2:
            _LOGGER.info("Skipping update, too soon after we issued a command")
            return  # We just updated the light, this is probably just the echo of that.
        if rgb[0] == 0 and rgb[1] == 0 and rgb[2] == 0:
            self._is_on = False
            self.schedule_update_ha_state()

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
        _LOGGER.info("UPDATING ID %s from Hao Deng to %s", self._attr_name, repr(rgb))
        self._is_on = True
        self._rgb_color = rgb
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        # _LOGGER.info("TURN ON %s", self._attr_name)
        self._is_on = True
        # self._ignore_next_update = True
        self._last_update = time.time()
        if _DEPRECATED_ATTR_KELVIN in kwargs:
            deprecated_color_temp = kwargs[ATTR_COLOR_TEMP_KELVIN]
            _LOGGER.info("Deprecated color temp %s", deprecated_color_temp)
        if ATTR_BRIGHTNESS in kwargs:
            self._brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_RGB_COLOR in kwargs:
            self._attr_color_mode = ColorMode.RGB
            normalized_colors = self.normalize_colors(
                kwargs[ATTR_RGB_COLOR][0],
                kwargs[ATTR_RGB_COLOR][1],
                kwargs[ATTR_RGB_COLOR][2],
                self._brightness,
            )
            self._rgb_color = normalized_colors
        elif (
            ATTR_BRIGHTNESS in kwargs
            and ATTR_COLOR_TEMP_KELVIN not in kwargs
            and ATTR_RGB_COLOR not in kwargs
        ):
            self._brightness = kwargs[ATTR_BRIGHTNESS]
            _LOGGER.info(
                "BRIGTHNESS %s: %s", self._attr_name, repr(kwargs[ATTR_BRIGHTNESS])
            )
            if self._attr_color_mode == ColorMode.RGB:
                base_colors = self.get_base_colors(self._rgb_color)
                new_rgb = []
                for color in base_colors:
                    color = color * self._brightness / 255
                    new_rgb.append(color)
                self._rgb_color = new_rgb
            else:
                self.async_write_ha_state()
                await self._mqtt_connector.set_color_temp(
                    self._mesh_id, self._attr_color_temp_kelvin, self._brightness
                )
                return
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            _LOGGER.info(
                "COLOR TEMPT %s: %s",
                self._attr_name,
                repr(kwargs[ATTR_COLOR_TEMP_KELVIN]),
            )
            self.async_write_ha_state()
            await self._mqtt_connector.set_color_temp(
                self._mesh_id, kwargs[ATTR_COLOR_TEMP_KELVIN], self._brightness
            )
            return
        else:
            await self.just_turn_on()
            return

        self.async_write_ha_state()
        await self._mqtt_connector.set_color(
            self._mesh_id,
            self._rgb_color[0],
            self._rgb_color[1],
            self._rgb_color[2],
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        # _LOGGER.info("TURN OFF ASYNC %s", self._attr_name)
        self._is_on = False
        self.async_write_ha_state()
        await self._mqtt_connector.turn_off(self._mesh_id)
        # Send command to your RGB light to turn off
        self._last_update = time.time()

    async def just_turn_on(self) -> None:
        """Turn the light off."""
        # _LOGGER.info("JUST TURN ON %s", self._attr_name)
        self._is_on = True
        self.async_write_ha_state()
        await self._mqtt_connector.turn_on(self._mesh_id)
        # Send command to your RGB light to turn off
        self._last_update = time.time()

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return the rgb color value [int, int, int]."""
        return self._rgb_color

    @property
    def brightness(self) -> int:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def color_temp_kelvin(self) -> int:
        """return color temp in kelvin."""
        return self._attr_color_temp_kelvin

    @property
    def unique_id(self):
        """Return the unique ID of the light."""
        return self._attr_unique_id

    @property
    def name(self):
        """Return the name of the light."""
        return self._attr_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                ("hao_deng_cloud", self._mesh_id)
            },
            name=self.name,
            manufacturer="Hao Deng",
            model="Hao Deng Light",
            sw_version="1.0.0",
            # Optional: If your device is connected via a hub/bridge, link it here
            # via_device=(DOMAIN, self.api.bridge_id),
        )

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the supported color modes."""
        return self._attr_supported_color_modes

    @property
    def color_mode(self) -> ColorMode:
        """Return the current color mode."""
        return self._attr_color_mode

    # def can_set_color(self):
    #     """Return true if light can set color by any means."""
    #     return True

    # def can_set_temp(self):
    #     """Return true if light can set color temp."""
    #     return True
