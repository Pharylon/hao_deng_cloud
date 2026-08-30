"""Group light entity for Hao Deng Cloud integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .base_light import HaoDengBaseLight
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

