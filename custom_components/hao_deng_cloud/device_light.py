"""Physical device light entity for Hao Deng Cloud integration."""

from collections.abc import Callable
import logging
import math
import time

from homeassistant.components.light import ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .base_light import HaoDengBaseLight
from .mqtt_connector import MqttConnector
from .pocos import Device, ExternalColorData

_LOGGER = logging.getLogger(__name__)


class HaoDengLight(HaoDengBaseLight):
    """Hao Deng physical device light."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        device: Device,
        mqtt_connector: MqttConnector,
    ) -> None:
        """Initialize the physical device light."""
        _LOGGER.debug("Initializing Light %s (ID %s)", device.displayName, device.uniID)
        super().__init__(
            config_entry=config_entry,
            mesh_id=device.meshAddress,
            unique_id=device.uniID,
            name=device.displayName,
            mqtt_connector=mqtt_connector,
            initial_available=False,
        )
        self._device = device
        self._group_listeners: list[Callable[[], None]] = []

        def update_light(a, d):
            if a == self._mesh_id:
                self._update_light(d)

        mqtt_connector.subscribe(update_light)

    @property
    def mesh_device(self) -> Device:
        """Return the underlying Device object."""
        return self._device

    def add_group_listener(self, listener: Callable[[], None]) -> None:
        """Register a callback when this light's state is updated."""
        if listener not in self._group_listeners:
            self._group_listeners.append(listener)

    def _notify_group_listeners(self) -> None:
        """Notify any group lights that contain this device."""
        for listener in self._group_listeners:
            try:
                listener()
            except Exception as exc:
                _LOGGER.error("Error notifying group listener: %s", exc)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on, set options, and notify groups."""
        await super().async_turn_on(**kwargs)
        self._notify_group_listeners()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off and notify groups."""
        await super().async_turn_off(**kwargs)
        self._notify_group_listeners()

    def get_base_colors(self, rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        """Get what the colors would be at brightness 100%."""
        multiplier = max(rgb) / 255
        adjusted_colors = []
        for color in rgb:
            adjusted_value = min(math.ceil(color / multiplier), 255)
            adjusted_colors.append(adjusted_value)
        return adjusted_colors

    def _update_hsv_values(self, color_data: ExternalColorData) -> None:
        if color_data.hsv[0] == 0 and color_data.hsv[1] == 0 and color_data.hsv[2] == 0:
            self._attr_is_on = False
            return
        self._attr_is_on = True
        self._attr_brightness = color_data.hsv[2] * 255
        self._attr_hs_color = [color_data.hsv[0], color_data.hsv[1] * 100]
        self._attr_color_mode = ColorMode.HS

    def _update_light_color_temp(self, color_data: ExternalColorData) -> None:
        self._attr_is_on = color_data.colorTempBrightness[1] > 0
        if self._attr_is_on is False:
            return
        self._attr_color_mode = ColorMode.COLOR_TEMP
        self._attr_color_temp_kelvin = color_data.colorTempBrightness[0]
        self._attr_brightness = min(
            math.ceil(color_data.colorTempBrightness[1] * 255), 255
        )

    def _update_light(self, color_data: ExternalColorData) -> None:
        """Update light from fetched cloud data."""
        try:
            if color_data.isAvailable is False:
                _LOGGER.warning(
                    "Update timestamp for %s is 00, light is unavailable",
                    self._attr_name,
                )
                return
            if (
                time.time() - self._last_update < 5
                and self._attr_color_mode != ColorMode.UNKNOWN
            ):
                return
            _LOGGER.debug("Updating %s", self._attr_name)
            if color_data.isHsv:
                self._update_hsv_values(color_data)
            else:
                self._update_light_color_temp(color_data)
            self._attr_available = True

            if getattr(self, "hass", None) is not None:
                self.schedule_update_ha_state()

            # Notify group lights
            self._notify_group_listeners()
        except Exception as e:
            _LOGGER.error(
                "Error updating light %s with data %s. Error was %s",
                self._attr_name,
                repr(color_data.__dict__),
                e,
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Use globally unique cloud ID instead of local meshAddress to prevent cross-place merges
                ("hao_deng_cloud", self._attr_unique_id)
            },
            name=self.name,
            manufacturer="Hao Deng",
            model="Hao Deng Light",
            sw_version="1.0.0",
        )


# Alias for explicit naming
HaoDengDeviceLight = HaoDengLight
