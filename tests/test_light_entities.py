"""Unit tests for Hao Deng light entities (device lights, group lights, and base light)."""

import asyncio
from enum import Enum
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

# Provide mock homeassistant if not installed in the environment
if "homeassistant" not in sys.modules:
    ha = types.ModuleType("homeassistant")
    ha_components = types.ModuleType("homeassistant.components")
    ha_light = types.ModuleType("homeassistant.components.light")
    ha_config_entries = types.ModuleType("homeassistant.config_entries")
    ha_core = types.ModuleType("homeassistant.core")
    ha_helpers = types.ModuleType("homeassistant.helpers")
    ha_dev_reg = types.ModuleType("homeassistant.helpers.device_registry")
    ha_ent_plat = types.ModuleType("homeassistant.helpers.entity_platform")

    class ColorMode(str, Enum):
        UNKNOWN = "unknown"
        HS = "hs"
        COLOR_TEMP = "color_temp"

    class LightEntity:
        def __init__(self):
            self._attr_name = None
            self._attr_unique_id = None
            self._attr_is_on = False
            self._attr_brightness = None
            self._attr_color_mode = None
            self._attr_supported_color_modes = None
            self._attr_available = True
            self._attr_should_poll = False
            self._attr_hs_color = None
            self._attr_color_temp_kelvin = None
            self._attr_min_color_temp_kelvin = None
            self._attr_max_color_temp_kelvin = None

        @property
        def name(self):
            return self._attr_name

        @property
        def unique_id(self):
            return self._attr_unique_id

        @property
        def is_on(self):
            return self._attr_is_on

        @property
        def available(self):
            return self._attr_available

        def schedule_update_ha_state(self):
            pass

        def async_write_ha_state(self):
            pass

    class DeviceInfo(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            for k, v in kwargs.items():
                setattr(self, k, v)

    class ConfigEntry:
        def __init__(self, data=None):
            self.data = data or {}

    class HomeAssistant:
        pass

    ha_light.ATTR_BRIGHTNESS = "brightness"
    ha_light.ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
    ha_light.ATTR_HS_COLOR = "hs_color"
    ha_light.ColorMode = ColorMode
    ha_light.LightEntity = LightEntity

    ha_dev_reg.DeviceInfo = DeviceInfo
    ha_config_entries.ConfigEntry = ConfigEntry
    ha_core.HomeAssistant = HomeAssistant
    ha_ent_plat.AddEntitiesCallback = MagicMock

    ha.components = ha_components
    ha.components.light = ha_light
    ha.config_entries = ha_config_entries
    ha.core = ha_core
    ha.helpers = ha_helpers
    ha.helpers.device_registry = ha_dev_reg
    ha.helpers.entity_platform = ha_ent_plat

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.components"] = ha_components
    sys.modules["homeassistant.components.light"] = ha_light
    sys.modules["homeassistant.config_entries"] = ha_config_entries
    sys.modules["homeassistant.core"] = ha_core
    sys.modules["homeassistant.helpers"] = ha_helpers
    sys.modules["homeassistant.helpers.device_registry"] = ha_dev_reg
    sys.modules["homeassistant.helpers.entity_platform"] = ha_ent_plat

# Provide mock paho.mqtt if not installed in the environment
if "paho" not in sys.modules:
    paho = types.ModuleType("paho")
    paho_mqtt = types.ModuleType("paho.mqtt")
    paho_client = types.ModuleType("paho.mqtt.client")
    paho_mqtt.client = paho_client
    paho_mqtt.__version__ = "2.0.0"
    paho_client.CallbackAPIVersion = types.SimpleNamespace(VERSION1=1, VERSION2=2)
    paho_client.Client = MagicMock
    sys.modules["paho"] = paho
    sys.modules["paho.mqtt"] = paho_mqtt
    sys.modules["paho.mqtt.client"] = paho_client

from homeassistant.components.light import ColorMode
from homeassistant.config_entries import ConfigEntry

from custom_components.hao_deng_cloud.base_light import HaoDengBaseLight
from custom_components.hao_deng_cloud.device_light import HaoDengDeviceLight, HaoDengLight
from custom_components.hao_deng_cloud.group_light import HaoDengGroupLight
from custom_components.hao_deng_cloud.pocos import Device, ExternalColorData, Group


def create_sample_device(mesh_address: int = 1) -> Device:
    """Create a sample Device."""
    return Device({
        "uniID": "dev_uni_123",
        "userID": "user_001",
        "placeUniID": "place_001",
        "macAddress": "AA:BB:CC:11:22:33",
        "displayName": "Kitchen Ceiling",
        "meshAddress": mesh_address,
        "deviceType": 1,
        "controlType": 1,
        "wiringType": 1,
        "group1ID": 10,
        "group2ID": 0,
        "group3ID": 0,
        "group4ID": 0,
        "group5ID": 0,
        "group6ID": 0,
        "group7ID": 0,
        "group8ID": 0,
    })


def create_sample_group(group_id: int = 10) -> Group:
    """Create a sample Group."""
    return Group({
        "uniID": "group_uni_456",
        "CDPID": "cdp_001",
        "userID": "user_001",
        "placeUniID": "place_001",
        "groupID": group_id,
        "groupName": "Kitchen All",
        "lastUpdateDate": "2026-01-01",
    })


class TestLightEntities(unittest.IsolatedAsyncioTestCase):
    """Test suite for Hao Deng light classes."""

    def setUp(self):
        self.mock_config_entry = ConfigEntry(
            data={"username": "test@example.com", "password": "pw", "country": "US"}
        )
        self.mock_mqtt = MagicMock()
        self.mock_mqtt.subscribe = MagicMock()
        self.mock_mqtt.set_color = AsyncMock()
        self.mock_mqtt.set_color_temp = AsyncMock()
        self.mock_mqtt.turn_on = AsyncMock()
        self.mock_mqtt.turn_off = AsyncMock()
        self.mock_mqtt.request_status = MagicMock()

    def test_device_light_initialization(self):
        """Test physical device light initialization and properties."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        self.assertEqual(light.unique_id, "dev_uni_123")
        self.assertEqual(light.name, "Kitchen Ceiling")
        self.assertEqual(light._mesh_id, 7)
        self.assertFalse(light.available)  # Device lights start unavailable until update
        self.assertEqual(light._device, device)

        # Check device info
        dev_info = light.device_info
        self.assertEqual(dev_info.name, "Kitchen Ceiling")
        self.assertEqual(dev_info.manufacturer, "Hao Deng")
        self.assertEqual(dev_info.model, "Hao Deng Light")
        self.assertEqual(dev_info.identifiers, {("hao_deng_cloud", "dev_uni_123")})

        # Check MQTT subscription was registered
        self.mock_mqtt.subscribe.assert_called_once()

    def test_group_light_initialization(self):
        """Test group light initialization and properties."""
        group = create_sample_group(group_id=25)
        group_light = HaoDengGroupLight(self.mock_config_entry, group, self.mock_mqtt)

        self.assertEqual(group_light.unique_id, "group_group_uni_456")
        self.assertEqual(group_light.name, "Kitchen All")
        self.assertEqual(group_light._mesh_id, 25)
        self.assertTrue(group_light.available)  # Group lights start available
        self.assertEqual(group_light._group, group)

        # Check device info
        dev_info = group_light.device_info
        self.assertEqual(dev_info.name, "Kitchen All")
        self.assertEqual(dev_info.manufacturer, "Hao Deng")
        self.assertEqual(dev_info.model, "Hao Deng Light Group")
        self.assertEqual(
            dev_info.identifiers, {("hao_deng_cloud", "group_group_uni_456")}
        )

        # Check MQTT subscription was registered
        self.mock_mqtt.subscribe.assert_called_once()

    def test_aliases_and_inheritance(self):
        """Test alias and inheritance hierarchies."""
        self.assertIs(HaoDengDeviceLight, HaoDengLight)
        self.assertTrue(issubclass(HaoDengLight, HaoDengBaseLight))
        self.assertTrue(issubclass(HaoDengGroupLight, HaoDengBaseLight))

    def test_update_hsv_status(self):
        """Test status update with HSV color data."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        # Simulate update callback from MQTT
        color_data_on = ExternalColorData(
            isHsl=True,
            hsv=[180.0, 0.75, 0.8],
            colorTempBrightness=None,
            isAvailable=True,
        )
        light._update_light(color_data_on)

        self.assertTrue(light.is_on)
        self.assertTrue(light.available)
        self.assertEqual(light._attr_color_mode, ColorMode.HS)
        self.assertEqual(light._attr_hs_color, [180.0, 75.0])
        self.assertEqual(light._attr_brightness, 0.8 * 255)

        # Simulate update callback when light is turned off (hsv=[0, 0, 0])
        color_data_off = ExternalColorData(
            isHsl=True,
            hsv=[0, 0, 0],
            colorTempBrightness=None,
            isAvailable=True,
        )
        light._update_light(color_data_off)
        self.assertFalse(light.is_on)

    def test_update_color_temp_status(self):
        """Test status update with color temperature data."""
        group = create_sample_group(group_id=25)
        group_light = HaoDengGroupLight(self.mock_config_entry, group, self.mock_mqtt)

        color_data_ct = ExternalColorData(
            isHsl=False,
            hsv=None,
            colorTempBrightness=[4000, 0.6],
            isAvailable=True,
        )
        group_light._update_light(color_data_ct)

        self.assertTrue(group_light.is_on)
        self.assertEqual(group_light._attr_color_mode, ColorMode.COLOR_TEMP)
        self.assertEqual(group_light._attr_color_temp_kelvin, 4000)
        self.assertEqual(group_light._attr_brightness, 153)

    def test_update_unavailable_data(self):
        """Test status update when isAvailable is False."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        color_data_unavail = ExternalColorData(
            isHsl=True,
            hsv=[0, 0, 0],
            colorTempBrightness=None,
            isAvailable=False,
        )
        light._update_light(color_data_unavail)
        # Should remain unavailable
        self.assertFalse(light.available)

    async def test_async_turn_on_basic(self):
        """Test basic async_turn_on."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        await light.async_turn_on()

        self.assertTrue(light.is_on)
        self.mock_mqtt.turn_on.assert_awaited_once_with(7)
        self.mock_mqtt.request_status.assert_called_once()

    async def test_async_turn_on_with_hs_color(self):
        """Test async_turn_on with HS color."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        await light.async_turn_on(hs_color=(120, 100), brightness=255)

        self.assertTrue(light.is_on)
        self.assertEqual(light._attr_color_mode, ColorMode.HS)
        self.mock_mqtt.set_color.assert_awaited_once()
        args = self.mock_mqtt.set_color.await_args[0]
        self.assertEqual(args[0], 7)  # mesh_id

    async def test_async_turn_on_with_color_temp(self):
        """Test async_turn_on with color temperature."""
        group = create_sample_group(group_id=25)
        group_light = HaoDengGroupLight(self.mock_config_entry, group, self.mock_mqtt)

        await group_light.async_turn_on(color_temp_kelvin=3500, brightness=200)

        self.assertTrue(group_light.is_on)
        self.assertEqual(group_light._attr_color_mode, ColorMode.COLOR_TEMP)
        self.mock_mqtt.set_color_temp.assert_awaited_once_with(25, 3500, 200)

    async def test_async_turn_off(self):
        """Test async_turn_off."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        await light.async_turn_off()

        self.assertFalse(light.is_on)
        self.mock_mqtt.turn_off.assert_awaited_once_with(7)

    def test_get_base_colors(self):
        """Test get_base_colors normalization."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        base_colors = light.get_base_colors((128, 64, 0))
        self.assertEqual(base_colors[0], 255)
        self.assertGreater(base_colors[1], 120)


if __name__ == "__main__":
    unittest.main()
