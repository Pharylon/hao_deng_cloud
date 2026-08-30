"""Group light entity for Hao Deng Cloud integration."""

import logging

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
        _LOGGER.info(
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
        _LOGGER.info(
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

            # Derive color mode and color / color temp from the first active member
            first_on = on_members[0]
            self._attr_color_mode = first_on.color_mode
            if first_on.color_mode == ColorMode.HS:
                self._attr_hs_color = first_on.hs_color
            elif first_on.color_mode == ColorMode.COLOR_TEMP:
                self._attr_color_temp_kelvin = first_on.color_temp_kelvin
        else:
            self._attr_brightness = 0

        _LOGGER.debug(
            "Group '%s' state derived from %d members (%d on): is_on=%s, brightness=%s",
            self._attr_name,
            len(self._members),
            len(on_members),
            self._attr_is_on,
            self._attr_brightness,
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
