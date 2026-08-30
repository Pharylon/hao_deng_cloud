"""Physical device light entity for Hao Deng Cloud integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .base_light import HaoDengBaseLight
from .mqtt_connector import MqttConnector
from .pocos import Device

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
        _LOGGER.info("Initializing Light %s", device.displayName)
        super().__init__(
            config_entry=config_entry,
            mesh_id=device.meshAddress,
            unique_id=device.uniID,
            name=device.displayName,
            mqtt_connector=mqtt_connector,
            initial_available=False,
        )
        self._device = device

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

