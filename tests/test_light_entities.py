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
        def brightness(self):
            return self._attr_brightness

        @property
        def color_mode(self):
            return self._attr_color_mode

        @property
        def hs_color(self):
            return self._attr_hs_color

        @property
        def color_temp_kelvin(self):
            return self._attr_color_temp_kelvin

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


def create_sample_device(mesh_address: int = 1, groups: list[int] = None) -> Device:
    """Create a sample Device."""
    if groups is None:
        groups = [10]
    return Device({
        "uniID": f"dev_uni_{mesh_address}",
        "userID": "user_001",
        "placeUniID": "place_001",
        "macAddress": f"AA:BB:CC:11:22:{mesh_address:02x}",
        "displayName": f"Kitchen Light {mesh_address}",
        "meshAddress": mesh_address,
        "deviceType": 1,
        "controlType": 1,
        "wiringType": 1,
        "group1ID": groups[0] if len(groups) > 0 else 0,
        "group2ID": groups[1] if len(groups) > 1 else 0,
        "group3ID": groups[2] if len(groups) > 2 else 0,
        "group4ID": groups[3] if len(groups) > 3 else 0,
        "group5ID": groups[4] if len(groups) > 4 else 0,
        "group6ID": groups[5] if len(groups) > 5 else 0,
        "group7ID": groups[6] if len(groups) > 6 else 0,
        "group8ID": groups[7] if len(groups) > 7 else 0,
    })


def create_sample_group(group_id: int = 10) -> Group:
    """Create a sample Group."""
    return Group({
        "uniID": f"group_uni_{group_id}",
        "CDPID": "cdp_001",
        "userID": "user_001",
        "placeUniID": "place_001",
        "groupID": group_id,
        "groupName": f"Kitchen Group {group_id}",
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

        self.assertEqual(light.unique_id, "dev_uni_7")
        self.assertEqual(light.name, "Kitchen Light 7")
        self.assertEqual(light._mesh_id, 7)
        self.assertFalse(light.available)  # Device lights start unavailable until update
        self.assertEqual(light.mesh_device, device)

        # Check device info
        dev_info = light.device_info
        self.assertEqual(dev_info.name, "Kitchen Light 7")
        self.assertEqual(dev_info.manufacturer, "Hao Deng")
        self.assertEqual(dev_info.model, "Hao Deng Light")
        self.assertEqual(dev_info.identifiers, {("hao_deng_cloud", "dev_uni_7")})

        # Check MQTT subscription was registered specifically for mesh_id
        self.mock_mqtt.subscribe.assert_called_once()

    def test_group_light_initialization_with_members(self):
        """Test group light initialization with member device lights."""
        group = create_sample_group(group_id=25)
        device1 = create_sample_device(mesh_address=1, groups=[25])
        device2 = create_sample_device(mesh_address=2, groups=[25])

        light1 = HaoDengLight(self.mock_config_entry, device1, self.mock_mqtt)
        light2 = HaoDengLight(self.mock_config_entry, device2, self.mock_mqtt)

        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light1, light2]
        )

        self.assertEqual(group_light.unique_id, "group_group_uni_25")
        self.assertEqual(group_light.name, "Kitchen Group 25")
        self.assertEqual(group_light._mesh_id, 25)
        self.assertEqual(len(group_light.members), 2)
        self.assertEqual(group_light.mesh_group, group)

        # Group light does not subscribe directly to MQTT
        # (the 2 subscribe calls are only from light1 and light2)
        self.assertEqual(self.mock_mqtt.subscribe.call_count, 2)

        # Check device info
        dev_info = group_light.device_info
        self.assertEqual(dev_info.name, "Kitchen Group 25")
        self.assertEqual(dev_info.manufacturer, "Hao Deng")
        self.assertEqual(dev_info.model, "Hao Deng Light Group")
        self.assertEqual(
            dev_info.identifiers, {("hao_deng_cloud", "group_group_uni_25")}
        )

    def test_aliases_and_inheritance(self):
        """Test alias and inheritance hierarchies."""
        self.assertIs(HaoDengDeviceLight, HaoDengLight)
        self.assertTrue(issubclass(HaoDengLight, HaoDengBaseLight))
        self.assertTrue(issubclass(HaoDengGroupLight, HaoDengBaseLight))

    def test_update_hsv_status_and_group_propagation(self):
        """Test device status update propagating to group light."""
        group = create_sample_group(group_id=10)
        device = create_sample_device(mesh_address=7, groups=[10])
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)
        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light]
        )

        # Device is off initially
        self.assertFalse(light.is_on)
        self.assertFalse(group_light.is_on)

        # Simulate update callback from MQTT on device
        color_data_on = ExternalColorData(
            isHsl=True,
            hsv=[180.0, 0.75, 0.8],
            colorTempBrightness=None,
            isAvailable=True,
        )
        light._update_light(color_data_on)

        # Verify device light state
        self.assertTrue(light.is_on)
        self.assertTrue(light.available)
        self.assertEqual(light.color_mode, ColorMode.HS)
        self.assertEqual(light.hs_color, [180.0, 75.0])
        self.assertEqual(light.brightness, 0.8 * 255)

        # Verify group light state derived from device light
        self.assertTrue(group_light.is_on)
        self.assertTrue(group_light.available)
        self.assertEqual(group_light.color_mode, ColorMode.HS)
        self.assertEqual(group_light.hs_color, (180.0, 75.0))
        self.assertEqual(group_light.brightness, 0.8 * 255)

        # Simulate device light turning off
        color_data_off = ExternalColorData(
            isHsl=True,
            hsv=[0, 0, 0],
            colorTempBrightness=None,
            isAvailable=True,
        )
        light._update_light(color_data_off)

        self.assertFalse(light.is_on)
        self.assertFalse(group_light.is_on)

    async def test_member_async_turn_on_and_off_updates_group(self):
        """Test that async_turn_on and async_turn_off on a member entity updates the group light."""
        group = create_sample_group(group_id=10)
        dev1 = create_sample_device(mesh_address=1, groups=[10])
        dev2 = create_sample_device(mesh_address=2, groups=[10])

        light1 = HaoDengLight(self.mock_config_entry, dev1, self.mock_mqtt)
        light2 = HaoDengLight(self.mock_config_entry, dev2, self.mock_mqtt)

        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light1, light2]
        )

        # Initially group is off
        self.assertFalse(group_light.is_on)
        self.assertEqual(group_light.brightness, 0)

        # Turn on light 1 via UI call (async_turn_on)
        await light1.async_turn_on(brightness=200)

        # Group light should immediately derive ON state and 50% proportional brightness (100 / 255)
        self.assertTrue(group_light.is_on)
        self.assertAlmostEqual(group_light.brightness, 100.0, delta=1.0)

        # Turn on light 2 via UI call (async_turn_on)
        await light2.async_turn_on(brightness=200)

        # Group light is 100% of the 200 brightness (200 / 255)
        self.assertTrue(group_light.is_on)
        self.assertAlmostEqual(group_light.brightness, 200.0, delta=1.0)

        # Turn off light 1 via UI call (async_turn_off)
        await light1.async_turn_off()

        # Group light remains on at 100 brightness
        self.assertTrue(group_light.is_on)
        self.assertAlmostEqual(group_light.brightness, 100.0, delta=1.0)

        # Turn off light 2 via UI call (async_turn_off)
        await light2.async_turn_off()

        # Group light is off
        self.assertFalse(group_light.is_on)
        self.assertEqual(group_light.brightness, 0)

    async def test_group_async_turn_on_and_off_updates_members(self):
        """Test that turning group on or off in HA updates all member entities in HA."""
        group = create_sample_group(group_id=10)
        dev1 = create_sample_device(mesh_address=1, groups=[10])
        dev2 = create_sample_device(mesh_address=2, groups=[10])

        light1 = HaoDengLight(self.mock_config_entry, dev1, self.mock_mqtt)
        light2 = HaoDengLight(self.mock_config_entry, dev2, self.mock_mqtt)

        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light1, light2]
        )

        # Turn on group
        await group_light.async_turn_on(brightness=255, color_temp_kelvin=6000)

        self.assertTrue(group_light.is_on)
        self.assertTrue(light1.is_on)
        self.assertTrue(light2.is_on)
        self.assertEqual(light1.brightness, 255)
        self.assertEqual(light2.brightness, 255)
        self.assertEqual(light1.color_mode, ColorMode.COLOR_TEMP)
        self.assertEqual(light2.color_mode, ColorMode.COLOR_TEMP)

        # Turn off group
        await group_light.async_turn_off()

        self.assertFalse(group_light.is_on)
        self.assertFalse(light1.is_on)
        self.assertFalse(light2.is_on)

    def test_pocos_group_and_device_integer_normalization(self):
        """Test that group and device group IDs are normalized to integer even if given as string."""
        dev = Device({
            "uniID": "123",
            "userID": "u",
            "placeUniID": "p",
            "macAddress": "m",
            "displayName": "d",
            "meshAddress": "5",
            "deviceType": "1",
            "controlType": "1",
            "wiringType": "1",
            "group1ID": "32771",
            "group2ID": 0,
            "group3ID": None,
            "group4ID": 0,
            "group5ID": 0,
            "group6ID": 0,
            "group7ID": 0,
            "group8ID": 0,
        })
        grp = Group({
            "uniID": "g1",
            "userID": "u",
            "placeUniID": "p",
            "groupID": "32771",
            "groupName": "Great Room",
        })

        self.assertEqual(dev.meshAddress, 5)
        self.assertEqual(dev.groups, [32771])
        self.assertEqual(grp.groupID, 32771)
        self.assertIn(grp.groupID, dev.groups)

    def test_group_color_averaging_all_color_temp(self):
        """Test color temperature averaging across multiple CT members."""
        group = create_sample_group(group_id=10)
        dev1 = create_sample_device(mesh_address=1, groups=[10])
        dev2 = create_sample_device(mesh_address=2, groups=[10])

        light1 = HaoDengLight(self.mock_config_entry, dev1, self.mock_mqtt)
        light2 = HaoDengLight(self.mock_config_entry, dev2, self.mock_mqtt)

        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light1, light2]
        )

        light1._update_light(
            ExternalColorData(isHsl=False, hsv=None, colorTempBrightness=[3000, 1.0], isAvailable=True)
        )
        light2._update_light(
            ExternalColorData(isHsl=False, hsv=None, colorTempBrightness=[5000, 1.0], isAvailable=True)
        )

        self.assertEqual(group_light.color_mode, ColorMode.COLOR_TEMP)
        self.assertEqual(group_light.color_temp_kelvin, 4000)
        self.assertIsNone(group_light.hs_color)

    def test_group_color_averaging_all_hs(self):
        """Test optical/additive HS color mixing across multiple HS members (Red + Blue -> Magenta)."""
        group = create_sample_group(group_id=10)
        dev1 = create_sample_device(mesh_address=1, groups=[10])
        dev2 = create_sample_device(mesh_address=2, groups=[10])

        light1 = HaoDengLight(self.mock_config_entry, dev1, self.mock_mqtt)
        light2 = HaoDengLight(self.mock_config_entry, dev2, self.mock_mqtt)

        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light1, light2]
        )

        # Red (0°, 100%)
        light1._update_light(
            ExternalColorData(isHsl=True, hsv=[0.0, 1.0, 1.0], colorTempBrightness=None, isAvailable=True)
        )
        # Blue (240°, 100%)
        light2._update_light(
            ExternalColorData(isHsl=True, hsv=[240.0, 1.0, 1.0], colorTempBrightness=None, isAvailable=True)
        )

        self.assertEqual(group_light.color_mode, ColorMode.HS)
        self.assertIsNotNone(group_light.hs_color)
        # Red + Blue mixes to Magenta (300°, 100%)
        h, s = group_light.hs_color
        self.assertAlmostEqual(h, 300.0, delta=2.0)
        self.assertAlmostEqual(s, 100.0, delta=2.0)
        self.assertIsNone(group_light.color_temp_kelvin)

    def test_group_color_averaging_mixed_hs_and_ct(self):
        """Test color mixing when some members are in Color Temp and some are in HS (Red + Cool White -> Pink)."""
        group = create_sample_group(group_id=10)
        dev1 = create_sample_device(mesh_address=1, groups=[10])
        dev2 = create_sample_device(mesh_address=2, groups=[10])

        light1 = HaoDengLight(self.mock_config_entry, dev1, self.mock_mqtt)
        light2 = HaoDengLight(self.mock_config_entry, dev2, self.mock_mqtt)

        group_light = HaoDengGroupLight(
            self.mock_config_entry, group, self.mock_mqtt, members=[light1, light2]
        )

        # Red HS
        light1._update_light(
            ExternalColorData(isHsl=True, hsv=[0.0, 1.0, 1.0], colorTempBrightness=None, isAvailable=True)
        )
        # 6500K Cool White
        light2._update_light(
            ExternalColorData(isHsl=False, hsv=None, colorTempBrightness=[6500, 1.0], isAvailable=True)
        )

        self.assertEqual(group_light.color_mode, ColorMode.HS)
        self.assertIsNotNone(group_light.hs_color)
        h, s = group_light.hs_color
        # Red hue preserved (0°), saturation halved (approx 50% pink)
        self.assertAlmostEqual(h, 0.0, delta=5.0)
        self.assertAlmostEqual(s, 50.0, delta=10.0)

    def test_group_step_by_step_shutoff_proportional_brightness(self):
        """Test that turning off 4 member lights one by one scales group brightness 100% -> 75% -> 50% -> 25% -> 0%."""
        group = create_sample_group(group_id=100)
        members = [
            HaoDengLight(self.mock_config_entry, create_sample_device(mesh_address=i, groups=[100]), self.mock_mqtt)
            for i in range(1, 5)
        ]
        group_light = HaoDengGroupLight(self.mock_config_entry, group, self.mock_mqtt, members=members)

        # Initially all 4 members turned ON at 100% brightness (255) in Color Temp mode
        for m in members:
            m._update_light(
                ExternalColorData(
                    isHsl=False,
                    hsv=None,
                    colorTempBrightness=[6500, 1.0],  # 100% brightness
                    isAvailable=True,
                )
            )

        # 4/4 lights on: 100% brightness (255)
        self.assertTrue(group_light.is_on)
        self.assertEqual(group_light.brightness, 255)
        self.assertEqual(group_light.color_mode, ColorMode.COLOR_TEMP)

        # Turn off 1st member (1/4 off -> 75% group brightness)
        members[0]._update_light(
            ExternalColorData(isHsl=True, hsv=[0, 0, 0], colorTempBrightness=None, isAvailable=True)
        )
        self.assertTrue(group_light.is_on)
        self.assertAlmostEqual(group_light.brightness / 255 * 100, 75.0, delta=0.5)

        # Turn off 2nd member (2/4 off -> 50% group brightness)
        members[1]._update_light(
            ExternalColorData(isHsl=True, hsv=[0, 0, 0], colorTempBrightness=None, isAvailable=True)
        )
        self.assertTrue(group_light.is_on)
        self.assertAlmostEqual(group_light.brightness / 255 * 100, 50.0, delta=0.5)

        # Turn off 3rd member (3/4 off -> 25% group brightness)
        members[2]._update_light(
            ExternalColorData(isHsl=True, hsv=[0, 0, 0], colorTempBrightness=None, isAvailable=True)
        )
        self.assertTrue(group_light.is_on)
        self.assertAlmostEqual(group_light.brightness / 255 * 100, 25.0, delta=0.5)

        # Turn off 4th member (4/4 off -> 0% group brightness, is_on = False)
        members[3]._update_light(
            ExternalColorData(isHsl=True, hsv=[0, 0, 0], colorTempBrightness=None, isAvailable=True)
        )
        self.assertFalse(group_light.is_on)
        self.assertEqual(group_light.brightness, 0)

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
        self.assertFalse(light.available)

    async def test_async_turn_on_basic(self):
        """Test basic async_turn_on on device and group lights."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        await light.async_turn_on()
        self.assertTrue(light.is_on)
        self.mock_mqtt.turn_on.assert_awaited_once_with(7)

        group = create_sample_group(group_id=25)
        group_light = HaoDengGroupLight(self.mock_config_entry, group, self.mock_mqtt)
        await group_light.async_turn_on()
        self.assertTrue(group_light.is_on)
        self.mock_mqtt.turn_on.assert_awaited_with(25)

    async def test_async_turn_on_with_hs_color(self):
        """Test async_turn_on with HS color."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        await light.async_turn_on(hs_color=(120, 100), brightness=255)

        self.assertTrue(light.is_on)
        self.assertEqual(light.color_mode, ColorMode.HS)
        self.mock_mqtt.set_color.assert_awaited_once()
        args = self.mock_mqtt.set_color.await_args[0]
        self.assertEqual(args[0], 7)  # mesh_id

    async def test_async_turn_on_with_color_temp(self):
        """Test async_turn_on with color temperature."""
        group = create_sample_group(group_id=25)
        group_light = HaoDengGroupLight(self.mock_config_entry, group, self.mock_mqtt)

        await group_light.async_turn_on(color_temp_kelvin=3500, brightness=200)

        self.assertTrue(group_light.is_on)
        self.assertEqual(group_light.color_mode, ColorMode.COLOR_TEMP)
        self.mock_mqtt.set_color_temp.assert_awaited_once_with(25, 3500, 200)

    async def test_async_turn_off(self):
        """Test async_turn_off on device and group."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        await light.async_turn_off()
        self.assertFalse(light.is_on)
        self.mock_mqtt.turn_off.assert_awaited_once_with(7)

    def test_get_base_colors(self):
        """Test get_base_colors normalization on HaoDengLight."""
        device = create_sample_device(mesh_address=7)
        light = HaoDengLight(self.mock_config_entry, device, self.mock_mqtt)

        base_colors = light.get_base_colors((128, 64, 0))
        self.assertEqual(base_colors[0], 255)
        self.assertGreater(base_colors[1], 120)


if __name__ == "__main__":
    unittest.main()
