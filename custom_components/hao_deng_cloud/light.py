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
    """Hao Deng Light."""

    def __init__(
        self, config_entry: ConfigEntry, device: Device, mqtt_connector: MqttConnector
    ) -> None:
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
                self._update_light(d)

        mqtt_connector.subscribe(update_light)

    def get_base_colors(self, rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        """Get what the colors would be at brightness 100%."""
        multiplier = max(rgb) / 255
        # brightest_color_value = max(rgb[0], rgb[1], rgb[2])
        adjusted_colors = []
        for color in rgb:
            adjusted_value = min(math.ceil(color / multiplier), 255)
            adjusted_colors.append(adjusted_value)
        return adjusted_colors

    def _update_hsv_values(self, color_data: ExternalColorData):
        # _LOGGER.info(
        #     "Updating HSV of %s %s %s ",
        #     color_data.hsv[0],
        #     color_data.hsv[1],
        #     color_data.hsv[2],
        # )
        if color_data.hsv[0] == 0 and color_data.hsv[1] == 0 and color_data.hsv[2] == 0:
            self._attr_is_on = False
            return
        # _LOGGER.info("%s is on", self._attr_name)
        self._attr_is_on = True
        # _LOGGER.info("New Bright  PRE %s", color_data.hsv[2])
        self._attr_brightness = color_data.hsv[2] * 255
        self._attr_hs_color = [color_data.hsv[0], color_data.hsv[1] * 100]
        # _LOGGER.info("New Bright %s", self._attr_brightness)
        # _LOGGER.info("New Hs %s", self._attr_hs_color)
        self._attr_color_mode = ColorMode.HS

    def _update_light_color_temp(self, color_data: ExternalColorData):
        self._attr_is_on = color_data.colorTempBrightness[1] > 0
        if self._attr_is_on is False:
            return
        self._attr_color_mode = ColorMode.COLOR_TEMP
        self._attr_color_temp_kelvin = color_data.colorTempBrightness[0]
        self._attr_brightness = min(
            math.ceil(color_data.colorTempBrightness[1] * 255), 255
        )

    def _update_light(self, color_data: ExternalColorData):
        """Update light from fetched cloud data."""
        try:
            # _LOGGER.info(
            #     "Received Update for %s: %s ",
            #     self._attr_name,
            #     repr(color_data.__dict__),
            # )
            if (
                color_data.isAvailable is False
                and color_data.colorTempBrightness[0] == 2500
                and color_data.colorTempBrightness[1] == 0
            ):
                _LOGGER.warning(
                    "Update timestamp for %s is 00, light is unavailable",
                    self._attr_name,
                )
                return
            if (
                time.time() - self._last_update < 5
                and self._attr_color_mode != ColorMode.UNKNOWN
            ):
                # _LOGGER.info("Skipping update, too soon after we issued a command")
                return
            _LOGGER.info("Updating %s", self._attr_name)
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
        # _LOGGER.info(
        #     "Convert HSL of %s %s %s to RGB of %s %s %s",
        #     hs[0],
        #     hs[1],
        #     brightness,
        #     rgb[0],
        #     rgb[1],
        #     rgb[2],
        # )
        return rgb

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on, set options."""
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        self._attr_brightness = self._attr_brightness or 255
        if ATTR_HS_COLOR in kwargs:
            # _LOGGER.info("Setting Color ON %s", repr(kwargs[ATTR_HS_COLOR]))
            self._attr_color_mode = ColorMode.HS
            # _LOGGER.info("HS %s", kwargs[ATTR_HS_COLOR])
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
            _LOGGER.info("Just turned on %s ", self._attr_name)
            self.async_write_ha_state()
            await self._mqtt_connector.turn_on(self._mesh_id)
            if self._attr_color_mode == ColorMode.UNKNOWN:
                # Light was off, so we don't know it's color state. Ask the cloud for new color
                await asyncio.sleep(0.1)
                self._mqtt_connector.request_status()
        self._last_update = time.time()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        _LOGGER.info("TURN OFF ASYNC %s", self._attr_name)
        self._attr_is_on = False
        self.async_write_ha_state()
        await self._mqtt_connector.turn_off(self._mesh_id)
        # Send command to your RGB light to turn off
        self._last_update = time.time()

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
        )
