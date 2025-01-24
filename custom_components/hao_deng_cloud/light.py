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
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .mqtt_connector import MqttConnector
from .pocos import Device, ExternalColorData
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
        self._attr_is_on = False
        self._rgb_color = (255, 0, 0)  # Initial color
        self._attr_supported_color_modes = [
            ColorMode.HS,
            ColorMode.COLOR_TEMP,
        ]
        self._attr_color_mode = ColorMode.UNKNOWN
        self._attr_brightness = 255
        self._attr_should_poll = False
        self._ignore_next_update = False
        self._last_update = 0

        self._attr_max_color_temp_kelvin = 6535
        self._attr_min_color_temp_kelvin = 2500

        self._attr_available = False

        def update_light(a, d):
            if a == self._mesh_id:
                # _LOGGER.info("Received update for Light %s", self._attr_name)
                self._update_light(d)

        mqtt_connector.subscribe(update_light)

    # @property
    # def is_on(self) -> bool:
    #     """Return True if light is on."""
    #     return self._attr_is_on

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

    def _update_hsv_values(self, color_data: ExternalColorData):
        _LOGGER.info(
            "Updating HSV of %s %s %s ",
            color_data.hsv[0],
            color_data.hsv[1],
            color_data.hsv[2],
        )
        if color_data.hsv[0] == 0 and color_data.hsv[1] == 0 and color_data.hsv[2] == 0:
            self._attr_is_on = False
            return
        # _LOGGER.info("%s is on", self._attr_name)
        self._attr_is_on = True
        _LOGGER.info("New Bright  PRE %s", color_data.hsv[2])
        self._attr_brightness = color_data.hsv[2] * 255
        self._attr_hs_color = [color_data.hsv[0], color_data.hsv[1] * 100]
        _LOGGER.info("New Bright %s", self._attr_brightness)
        _LOGGER.info("New Hs %s", self._attr_hs_color)
        self._attr_color_mode = ColorMode.HS

    # def _update_rgb_values(self, color_data: ExternalColorData):
    #     # I haven't been able to figure out the logic that exactly
    #     # converts their HSL-ish data into real RGB. So if it's
    #     # "close enough" we don't udpate, becuase we already have
    #     # the correct color. We should really only update this way
    #     # if the new color was created outside of Home Assistant.
    #     # In this case, at least we'll have something close in HA.
    #     # _LOGGER.info("Update_light %s: %s %s", self._attr_name, repr(rgb), self._attr_is_on)
    #     if (
    #         time.time() - self._last_update < 2
    #     ) and self._attr_color_mode != ColorMode.UNKNOWN:
    #         _LOGGER.info("Skipping update, too soon after we issued a command")
    #         return  # We just updated the light, this is probably just the echo of that.
    #     if color_data.rgb[0] == 0 and color_data.rgb[1] == 0 and color_data.rgb[2] == 0:
    #         self._attr_is_on = False
    #         self.schedule_update_ha_state()
    #         return
    #     rgb_distance = get_rgb_distance(
    #         [self._rgb_color[0], self._rgb_color[1], self._rgb_color[2]],
    #         color_data.rgb,
    #     )
    #     if rgb_distance < 50 and self._attr_color_mode != ColorMode.UNKNOWN:
    #         # the color is 'close enough', we don't need to update
    #         _LOGGER.info("CLose enough %s", self._attr_name)
    #         return
    #     _LOGGER.info("Updating RGB %s", self._attr_name)
    #     self._attr_is_on = True
    #     self._rgb_color = color_data.rgb
    #     self._attr_color_mode = ColorMode.RGB

    def _update_light_color_temp(self, color_data: ExternalColorData):
        self._attr_color_mode = ColorMode.COLOR_TEMP
        self._attr_color_temp_kelvin = color_data.colorTempBrightness[0]
        self._attr_is_on = color_data.colorTempBrightness[1] > 0
        self._attr_brightness = min(
            math.ceil(color_data.colorTempBrightness[1] * 255), 255
        )

    def _update_light(self, color_data: ExternalColorData):
        """Update light from fetched cloud data."""
        # _LOGGER.info("Updating %s: %s ", self._attr_name, repr(color_data.__dict__))
        try:
            # self._attr_is_on = True
            # self._attr_available = True
            # self.schedule_update_ha_state()
            # self._attr_color_mode = ColorMode.COLOR_TEMP
            # self._attr_color_temp_kelvin = 3000
            # self._attr_hs_color = [255, 1.0]
            # self._attr_brightness = 255
            # self.schedule_update_ha_state()
            _LOGGER.info("Updating %s: %s ", self._attr_name, repr(color_data.__dict__))
            if (time.time() - self._last_update) < 2:
                _LOGGER.info("Skipping update, too soon after we issued a command")
                return
            if color_data.isHsv:
                self._update_hsv_values(color_data)
            else:
                self._update_light_color_temp(color_data)
            self._attr_available = True
            self.schedule_update_ha_state()
        except Exception as e:
            _LOGGER.error(e)

    def _hsv_to_rgb(self, hs: tuple[float, float], brightness: float):
        brightness_scale_100 = brightness / 255
        rgb_float = colorsys.hsv_to_rgb(hs[0] / 365, hs[1] / 100, brightness_scale_100)
        rgb = [rgb_float[0] * 255, rgb_float[1] * 255, rgb_float[2] * 255]
        _LOGGER.info(
            "Convert HSL of %s %s %s to RGB of %s %s %s",
            hs[0],
            hs[1],
            brightness,
            rgb[0],
            rgb[1],
            rgb[2],
        )
        return rgb

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on, set options."""
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        self._attr_brightness = self._attr_brightness or 255
        if ATTR_HS_COLOR in kwargs:
            _LOGGER.info("Setting Color ON %s", repr(kwargs[ATTR_HS_COLOR]))
            self._attr_color_mode = ColorMode.HS
            _LOGGER.info("HS %s", kwargs[ATTR_HS_COLOR])
            self._attr_hs_color = kwargs[ATTR_HS_COLOR]
            rgb = self._hsv_to_rgb(self._attr_hs_color, self._attr_brightness)
            self.async_write_ha_state()
            await self._mqtt_connector.set_color(self._mesh_id, rgb[0], rgb[1], rgb[2])
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            self.async_write_ha_state()
            await self._mqtt_connector.set_color_temp(
                self._mesh_id,
                self._attr_color_temp_kelvin,
                self._attr_brightness,
            )
        elif ATTR_BRIGHTNESS in kwargs:
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
            self.async_write_ha_state()
            await self._mqtt_connector.turn_on(self._mesh_id)
        self._last_update = time.time()

        # async def async_turn_on(self, **kwargs) -> None:
        #     """Turn the light on."""
        #     # _LOGGER.info("TURN ON %s", self._attr_name)
        #     self._attr_is_on = True
        #     # self._ignore_next_update = True
        #     self._last_update = time.time()
        #     if ATTR_HS_COLOR in kwargs:
        #         _LOGGER.info("HS %s", kwargs[ATTR_HS_COLOR])
        #         self._attr_hs_color = kwargs[ATTR_HS_COLOR]
        #         return
        #     if ATTR_BRIGHTNESS in kwargs:
        #         self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        #     if ATTR_RGB_COLOR in kwargs:
        #         self._attr_color_mode = ColorMode.RGB
        #         normalized_colors = self.normalize_colors(
        #             kwargs[ATTR_RGB_COLOR][0],
        #             kwargs[ATTR_RGB_COLOR][1],
        #             kwargs[ATTR_RGB_COLOR][2],
        #             self._attr_brightness,
        #         )
        #         self._rgb_color = normalized_colors
        #     elif (
        #         ATTR_BRIGHTNESS in kwargs
        #         and ATTR_COLOR_TEMP_KELVIN not in kwargs
        #         and ATTR_RGB_COLOR not in kwargs
        #     ):
        #         _LOGGER.info("Just setting brigthness")
        #         self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        #         self.async_write_ha_state()
        #         _LOGGER.info(
        #             "BRIGTHNESS %s: %s", self._attr_name, repr(kwargs[ATTR_BRIGHTNESS])
        #         )
        #         if self._attr_color_mode == ColorMode.RGB:
        #             base_colors = self.get_base_colors(self._rgb_color)
        #             new_rgb = []
        #             for color in base_colors:
        #                 color = color * self._attr_brightness / 255
        #                 new_rgb.append(color)
        #             self._rgb_color = new_rgb
        #         else:
        #             await self._mqtt_connector.set_color_temp(
        #                 self._mesh_id, self._attr_color_temp_kelvin, self._attr_brightness
        #             )
        #             return
        #     elif ATTR_COLOR_TEMP_KELVIN in kwargs:
        #         self._attr_color_mode = ColorMode.COLOR_TEMP
        #         self._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
        #         _LOGGER.info(
        #             "COLOR TEMPT %s: %s",
        #             self._attr_name,
        #             repr(kwargs[ATTR_COLOR_TEMP_KELVIN]),
        #         )
        #         self.async_write_ha_state()
        #         await self._mqtt_connector.set_color_temp(
        #             self._mesh_id, kwargs[ATTR_COLOR_TEMP_KELVIN], self._attr_brightness
        #         )
        #         return
        #     else:
        #         await self.just_turn_on()
        #         return

        # self.async_write_ha_state()
        # await self._mqtt_connector.set_color(
        #     self._mesh_id,
        #     self._rgb_color[0],
        #     self._rgb_color[1],
        #     self._rgb_color[2],
        # /)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        _LOGGER.info("TURN OFF ASYNC %s", self._attr_name)
        # self._attr_is_on = False
        self.async_write_ha_state()
        await self._mqtt_connector.turn_off(self._mesh_id)
        # Send command to your RGB light to turn off
        self._last_update = time.time()

    async def just_turn_on(self) -> None:
        """Turn the light off."""
        # _LOGGER.info("JUST TURN ON %s", self._attr_name)
        self._attr_is_on = True
        self.async_write_ha_state()
        await self._mqtt_connector.turn_on(self._mesh_id)
        # Send command to your RGB light to turn off
        self._last_update = time.time()

    # @property
    # def rgb_color(self) -> tuple[int, int, int]:
    #     """Return the rgb color value [int, int, int]."""
    #     return self._rgb_color

    # @property

    # @property
    # def brightness(self) -> int:
    #     """Return the brightness of this light between 0..255."""
    #     _LOGGER.info("Reporting brightness %s", self._attr_brightness)
    #     return self._attr_brightness

    # @property
    # def color_temp_kelvin(self) -> int:
    #     """return color temp in kelvin."""
    #     return self._attr_color_temp_kelvin

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

    # @property
    # def supported_color_modes(self) -> set[ColorMode]:
    #     """Return the supported color modes."""
    #     return self._attr_supported_color_modes

    # @property
    # def color_mode(self) -> ColorMode:
    #     """Return the current color mode."""
    #     return self._attr_color_mode

    # def can_set_color(self):
    #     """Return true if light can set color by any means."""
    #     return True

    # def can_set_temp(self):
    #     """Return true if light can set color temp."""
    #     return True
