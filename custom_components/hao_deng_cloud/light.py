"""Hao Deng Light platform setup."""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .base_light import HaoDengBaseLight
from .device_light import HaoDengDeviceLight, HaoDengLight
from .group_light import HaoDengGroupLight
from .mqtt_connector import MqttConnector
from .pocos import Device, Group
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
    mesh_groups: list[Group] = await rest_connector.groups()
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

    for group in mesh_groups:
        group_light = HaoDengGroupLight(config_entry, group, mqtt_connector)
        lights.append(group_light)

    add_entities(lights)
    mqtt_connector.request_status()  # Get initial status of lights

    return True


__all__ = [
    "HaoDengBaseLight",
    "HaoDengDeviceLight",
    "HaoDengGroupLight",
    "HaoDengLight",
    "async_setup_entry",
]
