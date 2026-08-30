"""Group light entity for Hao Deng Cloud integration."""

import colorsys
import logging
import math

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .base_light import HaoDengBaseLight
from .device_light import HaoDengLight
from .mqtt_connector import MqttConnector
from .pocos import Group

_LOGGER = logging.getLogger(__name__)


class HaoDengGroupLight(HaoDengBaseLight):
    """Hao Deng Group Light."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        group: Group,
        mqtt_connector: MqttConnector,
        members: list[HaoDengLight] = None,
    ) -> None:
        """Initialize the group light."""
        _LOGGER.debug(
            "Initializing Group Light %s (GroupID: %s)",
            group.groupName,
            group.groupID,
        )
        super().__init__(
            config_entry=config_entry,
            mesh_id=group.groupID,
            unique_id=f"group_{group.uniID}",
            name=group.groupName,
            mqtt_connector=mqtt_connector,
            initial_available=True,
        )
        self._group = group
        self._members: list[HaoDengLight] = []
        if members:
            for member in members:
                self.add_member(member)
        self._update_from_group()
        _LOGGER.debug(
            "Group Light %s (GroupID: %s) configured with %d members: %s",
            group.groupName,
            group.groupID,
            len(self._members),
            [m.name for m in self._members],
        )

    @property
    def mesh_group(self) -> Group:
        """Return the underlying Group object."""
        return self._group

    @property
    def members(self) -> list[HaoDengLight]:
        """Return member lights belonging to this group."""
        return self._members

    def add_member(self, member: HaoDengLight) -> None:
        """Add a member device light to this group."""
        if member not in self._members:
            self._members.append(member)
            member.add_group_listener(self._update_from_group)

    @staticmethod
    def _kelvin_to_rgb(kelvin: float) -> tuple[float, float, float]:
        """Convert color temperature in Kelvin to RGB (0..255)."""
        temp = kelvin / 100.0
        # Red
        if temp <= 66:
            red = 255.0
        else:
            red = temp - 60.0
            red = 329.698727446 * (red ** -0.1332047592)
            red = max(0.0, min(255.0, red))

        # Green
        if temp <= 66:
            green = temp
            green = 99.4708025861 * math.log(green) - 161.1195681661
        else:
            green = temp - 60.0
            green = 288.1221695283 * (green ** -0.0755148492)
        green = max(0.0, min(255.0, green))

        # Blue
        if temp >= 66:
            blue = 255.0
        elif temp <= 19:
            blue = 0.0
        else:
            blue = temp - 10.0
            blue = 138.5177312231 * math.log(blue) - 305.0447927307
            blue = max(0.0, min(255.0, blue))

        return red, green, blue

    def _derive_group_color(self, on_members: list[HaoDengLight]) -> None:
        """Derive smeared / averaged color or color temperature from active members."""
        ct_members = [
            m
            for m in on_members
            if m.color_mode == ColorMode.COLOR_TEMP
            or (m.color_mode != ColorMode.HS and m.color_temp_kelvin is not None)
        ]
        hs_members = [
            m
            for m in on_members
            if m.color_mode == ColorMode.HS
            or (m.color_mode != ColorMode.COLOR_TEMP and m.hs_color is not None)
        ]

        # Case 1: All active members are in Color Temp mode
        if ct_members and not hs_members:
            total_weight = 0.0
            weighted_temp = 0.0
            for m in ct_members:
                weight = max(float(m.brightness or 255), 1.0)
                temp = float(m.color_temp_kelvin or 4000)
                weighted_temp += temp * weight
                total_weight += weight

            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_color_temp_kelvin = int(round(weighted_temp / total_weight))
            self._attr_hs_color = None
            return

        # Case 2: All active members in HS mode OR mixed Color Temp + HS modes
        total_weight = 0.0
        weighted_r = 0.0
        weighted_g = 0.0
        weighted_b = 0.0

        for m in on_members:
            weight = max(float(m.brightness or 255), 1.0)
            if m.color_mode == ColorMode.COLOR_TEMP or (
                m.color_mode != ColorMode.HS and m.color_temp_kelvin is not None
            ):
                temp = float(m.color_temp_kelvin or 4000)
                r, g, b = self._kelvin_to_rgb(temp)
            elif m.hs_color is not None:
                h, s = m.hs_color
                r_f, g_f, b_f = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, 1.0)
                r, g, b = r_f * 255.0, g_f * 255.0, b_f * 255.0
            else:
                # Default neutral white
                r, g, b = 255.0, 255.0, 255.0

            weighted_r += r * weight
            weighted_g += g * weight
            weighted_b += b * weight
            total_weight += weight

        if total_weight > 0:
            avg_r = (weighted_r / total_weight) / 255.0
            avg_g = (weighted_g / total_weight) / 255.0
            avg_b = (weighted_b / total_weight) / 255.0
            h_norm, s_norm, _ = colorsys.rgb_to_hsv(avg_r, avg_g, avg_b)
            self._attr_color_mode = ColorMode.HS
            self._attr_hs_color = (round(h_norm * 360.0, 1), round(s_norm * 100.0, 1))
            self._attr_color_temp_kelvin = None

    def _update_from_group(self) -> None:
        """Update group state derived from member device lights."""
        if not self._members:
            return

        # Group is on if any member is on
        on_members = [m for m in self._members if m.is_on]
        self._attr_is_on = len(on_members) > 0

        # Group is available if any member is available
        self._attr_available = any(m.available for m in self._members)

        if on_members:
            # Group brightness represents total group output across all members:
            # e.g., if 3 of 4 lights are on at 100%, group brightness is 75%
            total_brightness = sum(
                (m.brightness if (m.is_on and m.brightness is not None) else 0)
                for m in self._members
            )
            self._attr_brightness = total_brightness / len(self._members)

            # Derive smeared / averaged color or color temp across active members
            self._derive_group_color(on_members)
        else:
            self._attr_brightness = 0

        _LOGGER.debug(
            "Group '%s' state derived from %d members (%d on): is_on=%s, brightness=%s, color_mode=%s",
            self._attr_name,
            len(self._members),
            len(on_members),
            self._attr_is_on,
            self._attr_brightness,
            self._attr_color_mode,
        )

        if getattr(self, "hass", None) is not None:
            self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the group and propagate state to member entities in HA."""
        await super().async_turn_on(**kwargs)
        for member in self._members:
            member._attr_is_on = True
            if ATTR_BRIGHTNESS in kwargs:
                member._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            elif self._attr_brightness:
                member._attr_brightness = self._attr_brightness
            if ATTR_HS_COLOR in kwargs:
                member._attr_color_mode = ColorMode.HS
                member._attr_hs_color = kwargs[ATTR_HS_COLOR]
            elif ATTR_COLOR_TEMP_KELVIN in kwargs:
                member._attr_color_mode = ColorMode.COLOR_TEMP
                member._attr_color_temp_kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            if getattr(member, "hass", None) is not None:
                member.async_write_ha_state()
        self._update_from_group()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the group and propagate state to member entities in HA."""
        await super().async_turn_off(**kwargs)
        for member in self._members:
            member._attr_is_on = False
            if getattr(member, "hass", None) is not None:
                member.async_write_ha_state()
        self._update_from_group()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Use globally unique cloud ID instead of local groupID to prevent cross-place merges
                ("hao_deng_cloud", self._attr_unique_id)
            },
            name=self.name,
            manufacturer="Hao Deng",
            model="Hao Deng Light Group",
            sw_version="1.0.0",
        )
