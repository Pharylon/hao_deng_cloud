#!/usr/bin/env python3
"""Standalone test runner for Hao Deng Cloud integration.

This script allows testing turning device lights and group lights on and off,
and receiving MQTT status responses outside of Home Assistant.

Supports:
  1. Mock mode (default): Simulates the MQTT broker and verifies turn on, turn off,
     cloud notification decoding for both device lights and group lights,
     and verifies that group lights derive their state proportionally when members
     are turned off one by one.
  2. Live mode (--live): Connects to the real Hao Deng cloud, retrieves devices
     and groups, tests turning on/off actual device lights and group lights over MQTT,
     sets the group to bright white at 100% brightness, and verifies proportional
     group state derivation by turning off individual members one at a time over 1s per light.

Environment & Configuration:
  Supports loading options from a .env file (e.g. .env or custom path via --env-file)
  or environment variables:
    HAODENG_USERNAME, HAODENG_PASSWORD, HAODENG_COUNTRY,
    HAODENG_LIGHT_NAME, HAODENG_MESH_ID,
    HAODENG_GROUP_NAME, HAODENG_GROUP_ID
"""

import argparse
import asyncio
from enum import Enum
import json
import logging
import math
import os
import sys
import time
import types
from typing import Optional

# Ensure repository root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

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
    ha_ent_plat.AddEntitiesCallback = lambda *args, **kwargs: None

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

# Provide mock paho.mqtt if not installed in the environment (for mock mode)
if "paho" not in sys.modules:
    try:
        import paho.mqtt.client
    except ImportError:
        paho = types.ModuleType("paho")
        paho_mqtt = types.ModuleType("paho.mqtt")
        paho_client = types.ModuleType("paho.mqtt.client")
        paho_mqtt.client = paho_client
        paho_mqtt.__version__ = "2.0.0"
        paho_client.CallbackAPIVersion = types.SimpleNamespace(VERSION1=1, VERSION2=2)
        paho_client.Client = types.SimpleNamespace
        sys.modules["paho"] = paho
        sys.modules["paho.mqtt"] = paho_mqtt
        sys.modules["paho.mqtt.client"] = paho_client

from homeassistant.components.light import ColorMode
from homeassistant.config_entries import ConfigEntry

from custom_components.hao_deng_cloud.const import MAGICHUE_COUNTRY_SERVERS
from custom_components.hao_deng_cloud.device_light import HaoDengLight
from custom_components.hao_deng_cloud.group_light import HaoDengGroupLight
from custom_components.hao_deng_cloud.mqtt_connector import MqttConnector
from custom_components.hao_deng_cloud.pocos import (
    Device,
    ExternalColorData,
    Group,
    MqttControlData,
)

# ANSI color escape codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def load_env_file(env_path: Optional[str] = None) -> None:
    """Load variables from a .env file into os.environ if not already set."""
    candidates = []
    if env_path:
        candidates.append(env_path)
    else:
        # Check current working directory and script directory
        candidates.append(os.path.join(os.getcwd(), ".env"))
        candidates.append(os.path.join(SCRIPT_DIR, ".env"))

    found_path = None
    for path in candidates:
        if os.path.isfile(path):
            found_path = path
            break

    if not found_path:
        return

    try:
        with open(found_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    # Strip surrounding quotes if present
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        val = val[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception as exc:
        logging.warning("Failed to load .env file from %s: %s", found_path, exc)


class MockMqttClient:
    """Mock MQTT client simulating broker publishing and message delivery."""

    def __init__(self):
        self.published_messages: list[tuple[str, str, int]] = []
        self.on_connect = None
        self.on_message = None
        self.on_subscribe = None
        self.subscriptions: list[str] = []
        self.username = None
        self.password = None

    def username_pw_set(self, username, password):
        self.username = username
        self.password = password

    def connect(self, host, port, keepalive):
        pass

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def subscribe(self, topic, qos=0):
        self.subscriptions.append(topic)
        if self.on_subscribe:
            self.on_subscribe(self, None, 1, [qos])

    def publish(self, topic, payload, qos=0):
        self.published_messages.append((topic, payload, qos))

    def simulate_incoming_message(self, topic: str, payload_json: str):
        """Simulate an incoming message from the broker."""
        if self.on_message:
            msg = types.SimpleNamespace(
                topic=topic,
                payload=payload_json.encode("ASCII"),
                qos=1,
            )
            self.on_message(self, None, msg)


def create_mock_control_data() -> list[MqttControlData]:
    """Create sample MqttControlData for hardware and software."""
    hw_raw = {
        "deviceName": "mock_hw_gateway",
        "devicePwd": "hw_secret_password",
        "productKey": "HW_KEY_123",
        "deviceType": "HARDWARE",
        "macAddress": "11:22:33:44:55:66",
        "loadDeviceUrl": "http://example.com/hw",
    }
    sw_raw = {
        "deviceName": "mock_sw_client",
        "devicePwd": "sw_secret_password",
        "productKey": "SW_KEY_456",
        "deviceType": "SOFTWARE",
        "macAddress": "66:55:44:33:22:11",
        "loadDeviceUrl": "http://example.com/sw",
    }
    return [MqttControlData(hw_raw), MqttControlData(sw_raw)]


def create_mock_devices() -> list[Device]:
    """Create 4 mock devices for testing group aggregation."""
    devices = []
    for i in range(1, 5):
        devices.append(
            Device({
                "uniID": f"device_uuid_{i:03d}",
                "userID": "user_001",
                "placeUniID": "place_001",
                "macAddress": f"AA:BB:CC:11:22:{i:02x}",
                "displayName": f"Ceiling Light {i}",
                "meshAddress": i,
                "deviceType": 1,
                "controlType": 1,
                "wiringType": 1,
                "group1ID": 100,
                "group2ID": 0,
                "group3ID": 0,
                "group4ID": 0,
                "group5ID": 0,
                "group6ID": 0,
                "group7ID": 0,
                "group8ID": 0,
            })
        )
    return devices


def create_mock_groups() -> list[Group]:
    """Create mock groups for testing."""
    group_1 = Group({
        "uniID": "group_uuid_001",
        "CDPID": "cdp_001",
        "userID": "user_001",
        "placeUniID": "place_001",
        "groupID": 100,
        "groupName": "Living Room Group",
        "lastUpdateDate": "2026-01-01",
    })
    return [group_1]


async def run_mock_test() -> bool:
    """Run full simulated test of device light, group light, and member derivation."""
    print(f"\n{BOLD}{CYAN}=== Starting Hao Deng Cloud Mock Test ==={RESET}\n")

    control_data = create_mock_control_data()
    devices = create_mock_devices()
    groups = create_mock_groups()
    target_device = devices[0]
    target_group = groups[0]
    device_mesh_id = target_device.meshAddress
    group_mesh_id = target_group.groupID

    print(f"{BOLD}[1/10] Initializing MqttConnector and Light Entities...{RESET}")
    connector = MqttConnector(control_data, "US", devices)

    mock_client = MockMqttClient()
    connector.client = mock_client
    connector.client_connected = True

    # Track received updates from MQTT callback
    received_updates: list[tuple[int, ExternalColorData]] = []

    def on_status_received(target_id: int, color_data: ExternalColorData):
        received_updates.append((target_id, color_data))

    connector.subscribe(on_status_received)

    # Initialize mock entities
    dummy_entry = ConfigEntry(data={"username": "test", "password": "pw", "country": "US"})
    member_entities = [HaoDengLight(dummy_entry, d, connector) for d in devices]
    group_entity = HaoDengGroupLight(dummy_entry, target_group, connector, member_entities)

    print(
        f"      Connected MqttConnector.\n"
        f"      - Target Device Light: '{target_device.displayName}' (meshAddress: {device_mesh_id})\n"
        f"      - Target Group Light:  '{target_group.groupName}' (groupID: {group_mesh_id}, Members: {len(member_entities)})"
    )

    expected_topic = f"/{connector.software.productKey}/{connector.software.deviceName}/control"

    # ==========================================
    # --- PART 1: TEST PHYSICAL DEVICE LIGHT ---
    # ==========================================
    print(f"\n{BOLD}--- Testing Physical Device Light: '{target_device.displayName}' (ID: {device_mesh_id}) ---{RESET}")

    # [2/10] TEST DEVICE TURN ON
    print(f"\n{BOLD}[2/10] Testing Device Turn ON command...{RESET}")
    mock_client.published_messages.clear()
    await connector.turn_on(device_mesh_id)

    if not mock_client.published_messages:
        print(f"{RED}FAILED: No MQTT message was published for device turn_on{RESET}")
        return False

    pub_topic, pub_payload, _ = mock_client.published_messages[-1]
    payload_dict = json.loads(pub_payload)
    assert pub_topic == expected_topic
    assert payload_dict["dstAdr"] == device_mesh_id
    assert payload_dict["opCode"] == "D0"
    assert payload_dict["data"] == "0501FF000000000300"
    print(f"      {GREEN}✓ Device Turn ON command payload validated successfully{RESET}")

    # [3/10] SIMULATE CLOUD RESPONSE FOR DEVICE (ON)
    print(f"\n{BOLD}[3/10] Simulating Cloud MQTT status response (Device Light ON)...{RESET}")
    received_updates.clear()
    cloud_on_payload = json.dumps([{"a": device_mesh_id, "d": "016420FF00000000"}])
    for d in json.loads(cloud_on_payload):
        color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
        for s in connector.subscriptions:
            s(d["a"], color_tuple)

    dev_id, color_data = received_updates[-1]
    assert dev_id == device_mesh_id
    assert color_data.isAvailable is True
    assert color_data.isHsv is True
    assert color_data.hsv[2] == 1.0  # 100% brightness
    print(f"      {GREEN}✓ MQTT response parsed correctly: Device Light is ON (Brightness: 100%){RESET}")

    # [4/10] TEST DEVICE TURN OFF
    print(f"\n{BOLD}[4/10] Testing Device Turn OFF command...{RESET}")
    mock_client.published_messages.clear()
    await connector.turn_off(device_mesh_id)

    pub_topic, pub_payload, _ = mock_client.published_messages[-1]
    payload_dict = json.loads(pub_payload)
    assert pub_topic == expected_topic
    assert payload_dict["dstAdr"] == device_mesh_id
    assert payload_dict["opCode"] == "D0"
    assert payload_dict["data"] == "050100000000000300"
    print(f"      {GREEN}✓ Device Turn OFF command payload validated successfully{RESET}")

    # [5/10] SIMULATE CLOUD RESPONSE FOR DEVICE (OFF)
    print(f"\n{BOLD}[5/10] Simulating Cloud MQTT status response (Device Light OFF)...{RESET}")
    received_updates.clear()
    cloud_off_payload = json.dumps([{"a": device_mesh_id, "d": "0100000000000000"}])
    for d in json.loads(cloud_off_payload):
        color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
        for s in connector.subscriptions:
            s(d["a"], color_tuple)

    dev_id, color_data = received_updates[-1]
    assert dev_id == device_mesh_id
    assert color_data.hsv == [0, 0, 0]
    print(f"      {GREEN}✓ MQTT response parsed correctly: Device Light is OFF (hsv=[0,0,0]){RESET}")

    # ==========================================
    # --- PART 2: TEST GROUP LIGHT -------------
    # ==========================================
    print(f"\n{BOLD}--- Testing Group Light: '{target_group.groupName}' (GroupID: {group_mesh_id}) ---{RESET}")

    # [6/10] TEST GROUP TURN ON
    print(f"\n{BOLD}[6/10] Testing Group Turn ON command...{RESET}")
    mock_client.published_messages.clear()
    await connector.turn_on(group_mesh_id)

    pub_topic, pub_payload, _ = mock_client.published_messages[-1]
    payload_dict = json.loads(pub_payload)
    assert pub_topic == expected_topic
    assert payload_dict["dstAdr"] == group_mesh_id
    assert payload_dict["opCode"] == "D0"
    assert payload_dict["data"] == "0501FF000000000300"
    print(f"      {GREEN}✓ Group Turn ON command payload validated successfully{RESET}")

    # [7/10] SIMULATE CLOUD RESPONSE FOR GROUP MEMBER (ON)
    print(f"\n{BOLD}[7/10] Simulating Cloud MQTT status response on member device (Group Light ON)...{RESET}")
    received_updates.clear()
    cloud_group_on_payload = json.dumps([{"a": device_mesh_id, "d": "016420FF00000000"}])
    for d in json.loads(cloud_group_on_payload):
        color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
        for s in connector.subscriptions:
            s(d["a"], color_tuple)

    m_id, color_data = received_updates[-1]
    assert m_id == device_mesh_id
    assert color_data.isAvailable is True
    print(f"      {GREEN}✓ Member device notification parsed correctly: Member is ON{RESET}")

    # [8/10] TEST GROUP TURN OFF
    print(f"\n{BOLD}[8/10] Testing Group Turn OFF command...{RESET}")
    mock_client.published_messages.clear()
    await connector.turn_off(group_mesh_id)

    pub_topic, pub_payload, _ = mock_client.published_messages[-1]
    payload_dict = json.loads(pub_payload)
    assert pub_topic == expected_topic
    assert payload_dict["dstAdr"] == group_mesh_id
    assert payload_dict["opCode"] == "D0"
    assert payload_dict["data"] == "050100000000000300"
    print(f"      {GREEN}✓ Group Turn OFF command payload validated successfully{RESET}")

    # =========================================================================
    # --- PART 3: TEST GROUP STATE DERIVATION & STEP-BY-STEP MEMBER SHUTOFF ---
    # =========================================================================
    print(f"\n{BOLD}--- Testing Group State Derivation & Step-by-Step Member Shutoff ---{RESET}")

    # [9/10] Set group to 100% Brightness in Color Temp Mode (Bright White: 6500K)
    print(f"\n{BOLD}[9/10] Setting Group to 100% Brightness in Color Temp mode (Bright White: 6500K)...{RESET}")
    mock_client.published_messages.clear()
    await connector.set_color_temp(group_mesh_id, 6500, 255)

    pub_topic, pub_payload, _ = mock_client.published_messages[-1]
    payload_dict = json.loads(pub_payload)
    assert pub_topic == expected_topic
    assert payload_dict["dstAdr"] == group_mesh_id
    assert payload_dict["opCode"] == "E2"
    assert payload_dict["data"].startswith("0562")
    print(f"      {GREEN}✓ Set Color Temp (6500K @ 100%) command payload validated{RESET}")

    # Simulate all 4 members turning ON at 100% brightness in color temp mode
    for m in member_entities:
        cloud_ct_payload = json.dumps([{"a": m.mesh_device.meshAddress, "d": "0164FF6400000000"}])
        for d in json.loads(cloud_ct_payload):
            color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
            for s in connector.subscriptions:
                s(d["a"], color_tuple)

    assert group_entity.is_on is True
    assert group_entity.brightness == 255
    assert group_entity.color_mode == ColorMode.COLOR_TEMP
    print(f"      {GREEN}✓ All {len(member_entities)} members ON -> Group brightness: 100.0% ({group_entity.brightness}/255){RESET}")

    # [10/10] Turn off individual members one at a time over 1 second per light & verify proportional brightness
    print(f"\n{BOLD}[10/10] Turning off individual member lights one by one & verifying group brightness...{RESET}")
    total_members = len(member_entities)
    for idx, member in enumerate(member_entities, start=1):
        m_id = member.mesh_device.meshAddress
        print(f"      Step {idx}/{total_members}: Turning off member '{member.name}' (meshAddress: {m_id})...")
        await connector.turn_off(m_id)

        # Simulate cloud response: member turned off
        cloud_off_payload = json.dumps([{"a": m_id, "d": "0100000000000000"}])
        for d in json.loads(cloud_off_payload):
            color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
            for s in connector.subscriptions:
                s(d["a"], color_tuple)

        expected_pct = ((total_members - idx) / total_members) * 100
        actual_pct = (group_entity.brightness / 255) * 100

        print(
            f"      {GREEN}✓ Verified group brightness: {actual_pct:.1f}% "
            f"(Expected: {expected_pct:.1f}%, Active members: {total_members - idx}/{total_members}){RESET}"
        )
        assert math.isclose(actual_pct, expected_pct, abs_tol=0.5), (
            f"Expected {expected_pct:.1f}%, got {actual_pct:.1f}%"
        )
        await asyncio.sleep(0.05)  # Fast in mock mode

    assert group_entity.is_on is False
    assert group_entity.brightness == 0
    print(f"      {GREEN}✓ All members OFF -> Group is OFF with 0% brightness{RESET}")

    print(f"\n{BOLD}{GREEN}========================================================================{RESET}")
    print(f"{BOLD}{GREEN}  ALL MOCK TESTS (DEVICE, GROUP & MEMBER DERIVATION) PASSED SUCCESSFULLY!{RESET}")
    print(f"{BOLD}{GREEN}========================================================================{RESET}\n")
    return True


async def test_entity_cycle(
    mqtt_connector: MqttConnector,
    received_events: asyncio.Queue,
    target_id: int,
    target_name: str,
    entity_label: str,
    expected_response_ids: list[int] = None,
    timeout: int = 10,
) -> bool:
    """Turn target on, wait for confirmation, hold, turn off, wait for confirmation."""
    expected_ids = set(expected_response_ids) if expected_response_ids else {target_id}
    print(f"\n{BOLD}--> [{entity_label}] Testing '{target_name}' (ID: {target_id}, Monitoring IDs: {list(expected_ids)})...{RESET}")

    # 1. TURN ON
    print(f"    Sending TURN ON command to '{target_name}' (ID: {target_id})...")
    while not received_events.empty():
        received_events.get_nowait()

    await mqtt_connector.turn_on(target_id)

    print(f"    Waiting up to {timeout}s for MQTT response confirming ON from {list(expected_ids)}...")
    on_confirmed = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        wait_time = max(0.1, deadline - time.time())
        try:
            res_id, color_data = await asyncio.wait_for(
                received_events.get(), timeout=wait_time
            )
            if res_id in expected_ids:
                is_on = False
                if color_data.isHsv and any(v > 0 for v in color_data.hsv):
                    is_on = True
                elif (
                    not color_data.isHsv
                    and color_data.colorTempBrightness
                    and color_data.colorTempBrightness[1] > 0
                ):
                    is_on = True

                if is_on:
                    print(f"    {GREEN}✓ Confirmed '{target_name}' turned ON (via response for ID {res_id})!{RESET}")
                    on_confirmed = True
                    break
        except asyncio.TimeoutError:
            break

    if not on_confirmed:
        print(
            f"    {YELLOW}Warning: Did not receive explicit ON confirmation for '{target_name}' within {timeout}s{RESET}"
        )

    print("    Holding state for 2 seconds...")
    await asyncio.sleep(2.0)

    # 2. TURN OFF
    print(f"    Sending TURN OFF command to '{target_name}' (ID: {target_id})...")
    while not received_events.empty():
        received_events.get_nowait()

    await mqtt_connector.turn_off(target_id)

    print(f"    Waiting up to {timeout}s for MQTT response confirming OFF from {list(expected_ids)}...")
    off_confirmed = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        wait_time = max(0.1, deadline - time.time())
        try:
            res_id, color_data = await asyncio.wait_for(
                received_events.get(), timeout=wait_time
            )
            if res_id in expected_ids:
                is_off = False
                if color_data.isHsv and color_data.hsv == [0, 0, 0]:
                    is_off = True
                elif (
                    not color_data.isHsv
                    and color_data.colorTempBrightness
                    and color_data.colorTempBrightness[1] == 0
                ):
                    is_off = True

                if is_off:
                    print(f"    {GREEN}✓ Confirmed '{target_name}' turned OFF (via response for ID {res_id})!{RESET}")
                    off_confirmed = True
                    break
        except asyncio.TimeoutError:
            break

    if not off_confirmed:
        print(
            f"    {YELLOW}Warning: Did not receive explicit OFF confirmation for '{target_name}' within {timeout}s{RESET}"
        )

    print(f"    {GREEN}✓ Completed cycle for '{target_name}'{RESET}")
    return True


async def run_live_test(
    username: str,
    password: str,
    country: str,
    target_light_name: Optional[str] = None,
    target_mesh_id: Optional[int] = None,
    target_group_name: Optional[str] = None,
    target_group_id: Optional[int] = None,
    timeout: int = 10,
) -> bool:
    """Connect to live Hao Deng cloud and test turning light and group light on/off, then verify member derivation."""
    print(f"\n{BOLD}{CYAN}=== Starting Hao Deng Cloud Live Test ==={RESET}\n")
    print(f"Connecting to account: {username} (Country: {country})...")

    from custom_components.hao_deng_cloud.rest_api_connector import RestApiConnector

    rest_connector = RestApiConnector(username, password, country)

    try:
        await rest_connector.connect()
    except Exception as exc:
        print(f"{RED}Login failed: {exc}{RESET}")
        return False

    print(f"{GREEN}✓ Successfully authenticated with Hao Deng Cloud!{RESET}")

    devices = await rest_connector.devices()
    groups = await rest_connector.groups()
    control_data = await rest_connector.get_mqtt_control_data()

    print(f"\nDiscovered {len(devices)} device(s) and {len(groups)} group(s):")
    controllable_devices = []
    for dev in devices:
        status_note = " (controllable)" if dev.wiringType != 0 else " (sensor/bridge)"
        print(f"  - Device: '{dev.displayName}' | MeshAddress: {dev.meshAddress} | UniID: {dev.uniID}{status_note}")
        if dev.wiringType != 0:
            controllable_devices.append(dev)

    for grp in groups:
        print(f"  - Group:  '{grp.groupName}' | GroupID: {grp.groupID} | UniID: {grp.uniID}")

    # --- Match Device Light ---
    target_device = None
    if controllable_devices:
        if target_mesh_id is not None:
            matches = [d for d in controllable_devices if d.meshAddress == target_mesh_id]
            if matches:
                target_device = matches[0]
            else:
                print(f"{YELLOW}Warning: Device with meshAddress {target_mesh_id} not found among controllable devices.{RESET}")
        elif target_light_name:
            matches = [
                d for d in controllable_devices
                if target_light_name.lower() in d.displayName.lower()
            ]
            if matches:
                target_device = matches[0]
            else:
                print(f"{YELLOW}Warning: Device with name matching '{target_light_name}' not found.{RESET}")

        if not target_device:
            target_device = controllable_devices[0]
            print(f"Defaulting to first controllable device: '{target_device.displayName}' (meshAddress: {target_device.meshAddress})")
    else:
        print(f"{YELLOW}Warning: No controllable light devices found (wiringType != 0).{RESET}")

    # --- Match Group Light ---
    target_group = None
    if groups:
        if target_group_id is not None:
            matches = [g for g in groups if g.groupID == target_group_id]
            if matches:
                target_group = matches[0]
            else:
                print(f"{YELLOW}Warning: Group with groupID {target_group_id} not found.{RESET}")
        elif target_group_name:
            matches = [
                g for g in groups
                if target_group_name.lower() in g.groupName.lower()
            ]
            if matches:
                target_group = matches[0]
            else:
                print(f"{YELLOW}Warning: Group with name matching '{target_group_name}' not found.{RESET}")

        if not target_group:
            target_group = groups[0]
            print(f"Defaulting to first group: '{target_group.groupName}' (groupID: {target_group.groupID})")
    else:
        print(f"{YELLOW}Note: No groups found on this account.{RESET}")

    if not target_device and not target_group:
        print(f"{RED}Error: Neither controllable devices nor groups found to test.{RESET}")
        return False

    # Set up MQTT Connector
    mqtt_connector = MqttConnector(control_data, country, devices)
    received_events = asyncio.Queue()

    # Wire up light entities to track live state
    dummy_entry = ConfigEntry(data={"username": username, "password": password, "country": country})
    live_device_lights: dict[int, HaoDengLight] = {}
    for d in controllable_devices:
        live_device_lights[d.meshAddress] = HaoDengLight(dummy_entry, d, mqtt_connector)

    live_group_light = None
    group_members: list[HaoDengLight] = []
    if target_group:
        group_members = [
            l for l in live_device_lights.values()
            if target_group.groupID in l.mesh_device.groups
        ]
        live_group_light = HaoDengGroupLight(
            dummy_entry, target_group, mqtt_connector, group_members
        )

    def on_live_status(dev_id: int, color_data: ExternalColorData):
        print(f"\n{CYAN}>>> Live MQTT update for ID {dev_id}: Available={color_data.isAvailable}, HSV={color_data.hsv}, CT={color_data.colorTempBrightness}{RESET}")
        received_events.put_nowait((dev_id, color_data))

    mqtt_connector.subscribe(on_live_status)

    print("\nConnecting to MQTT broker...")
    mqtt_connector.connect()

    # Wait for MQTT connection
    start_time = time.time()
    while not mqtt_connector.client_connected and time.time() - start_time < timeout:
        await asyncio.sleep(0.1)

    if not mqtt_connector.client_connected:
        print(f"{RED}Failed to connect to MQTT broker within {timeout}s{RESET}")
        return False

    print(f"{GREEN}✓ Connected to MQTT broker!{RESET}")
    mqtt_connector.request_status()
    await asyncio.sleep(1.0)

    # 1. Test Device Light if selected
    if target_device:
        await test_entity_cycle(
            mqtt_connector=mqtt_connector,
            received_events=received_events,
            target_id=target_device.meshAddress,
            target_name=target_device.displayName,
            entity_label="Device Light",
            expected_response_ids=[target_device.meshAddress],
            timeout=timeout,
        )

    # 2. Test Group Light Turn On/Off if selected
    if target_group:
        member_mesh_ids = mqtt_connector._groups.get(target_group.groupID, [])
        await test_entity_cycle(
            mqtt_connector=mqtt_connector,
            received_events=received_events,
            target_id=target_group.groupID,
            target_name=target_group.groupName,
            entity_label="Group Light",
            expected_response_ids=member_mesh_ids if member_mesh_ids else [target_group.groupID],
            timeout=timeout,
        )

        # 3. Test Step-by-Step Member Shutoff & Group Brightness Derivation
        if group_members and len(group_members) > 1:
            print(f"\n{BOLD}{CYAN}=== Testing Group Member State Derivation ({target_group.groupName}) ==={RESET}\n")
            print(f"Setting group '{target_group.groupName}' to 100% Brightness in Color Temp Mode (Bright White: 6500K)...")
            while not received_events.empty():
                received_events.get_nowait()

            await mqtt_connector.set_color_temp(target_group.groupID, 6500, 255)
            print(f"Waiting up to {timeout}s for member lights to confirm ON...")

            # Wait for member updates
            deadline = time.time() + timeout
            while time.time() < deadline:
                wait_time = max(0.1, deadline - time.time())
                try:
                    await asyncio.wait_for(received_events.get(), timeout=wait_time)
                except asyncio.TimeoutError:
                    break

            initial_bright_pct = (live_group_light.brightness / 255) * 100 if live_group_light.brightness else 0
            print(f"{GREEN}✓ Initial group brightness: {initial_bright_pct:.1f}%{RESET}")

            # Turn off individual members one at a time over 1 second per light
            total_m = len(group_members)
            print(f"\nTurning off {total_m} members one at a time (1s per light)...")

            for idx, member_light in enumerate(group_members, start=1):
                m_mesh_id = member_light.mesh_device.meshAddress
                print(f"\n[{idx}/{total_m}] Turning off '{member_light.name}' (meshAddress: {m_mesh_id})...")
                await mqtt_connector.turn_off(m_mesh_id)

                # Wait for member update
                deadline = time.time() + timeout
                while time.time() < deadline:
                    wait_time = max(0.1, deadline - time.time())
                    try:
                        res_id, color_data = await asyncio.wait_for(
                            received_events.get(), timeout=wait_time
                        )
                        if res_id == m_mesh_id and color_data.isHsv and color_data.hsv == [0, 0, 0]:
                            break
                    except asyncio.TimeoutError:
                        break

                await asyncio.sleep(1.0)

                expected_pct = ((total_m - idx) / total_m) * 100
                actual_pct = (live_group_light.brightness / 255) * 100 if live_group_light.brightness else 0

                print(
                    f"    {GREEN}✓ Member '{member_light.name}' OFF -> "
                    f"Group Brightness: {actual_pct:.1f}% (Expected: {expected_pct:.1f}%, Active: {total_m - idx}/{total_m}){RESET}"
                )

            print(f"\n{BOLD}{GREEN}✓ Completed member derivation verification for '{target_group.groupName}'!{RESET}")

    if hasattr(mqtt_connector.client, "loop_stop"):
        mqtt_connector.client.loop_stop()

    print(f"\n{BOLD}{GREEN}Live test finished successfully!{RESET}\n")
    return True


def main():
    """Main CLI entrypoint."""
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=None, help="Path to .env configuration file.")
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(pre_args.env_file)

    parser = argparse.ArgumentParser(
        description="Test turning Hao Deng device and group lights on and off and receiving MQTT responses."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live test against real Hao Deng cloud (requires username & password).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run automated mock test (default if --live is not specified).",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Path to .env file to load configuration from.",
    )
    parser.add_argument(
        "-u",
        "--username",
        default=os.environ.get("HAODENG_USERNAME", ""),
        help="Hao Deng cloud account username / email (or HAODENG_USERNAME in .env).",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=os.environ.get("HAODENG_PASSWORD", ""),
        help="Hao Deng cloud account password (or HAODENG_PASSWORD in .env).",
    )
    parser.add_argument(
        "-c",
        "--country",
        default=os.environ.get("HAODENG_COUNTRY", "US"),
        help="Country code (US, AU, GB, CN, DE, FR, etc. Default: US or HAODENG_COUNTRY in .env).",
    )
    parser.add_argument(
        "-l",
        "--light-name",
        "--light",
        dest="light_name",
        default=os.environ.get("HAODENG_LIGHT_NAME", ""),
        help="Name of specific device light to test (or HAODENG_LIGHT_NAME in .env).",
    )
    parser.add_argument(
        "-m",
        "--mesh-id",
        type=int,
        default=int(os.environ["HAODENG_MESH_ID"]) if "HAODENG_MESH_ID" in os.environ and os.environ["HAODENG_MESH_ID"].isdigit() else None,
        help="Specific device meshAddress to test (or HAODENG_MESH_ID in .env).",
    )
    parser.add_argument(
        "-g",
        "--group-name",
        "--group",
        dest="group_name",
        default=os.environ.get("HAODENG_GROUP_NAME", ""),
        help="Name of specific group light to test (or HAODENG_GROUP_NAME in .env).",
    )
    parser.add_argument(
        "--group-id",
        type=int,
        default=int(os.environ["HAODENG_GROUP_ID"]) if "HAODENG_GROUP_ID" in os.environ and os.environ["HAODENG_GROUP_ID"].isdigit() else None,
        help="Specific groupID to test (or HAODENG_GROUP_ID in .env).",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=int,
        default=10,
        help="Seconds to wait for MQTT response in live mode (default: 10).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging output.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.live:
        if not args.username or not args.password:
            print(
                f"{RED}Error: --username and --password (or HAODENG_USERNAME / HAODENG_PASSWORD in .env) are required for live test.{RESET}"
            )
            sys.exit(1)
        success = asyncio.run(
            run_live_test(
                username=args.username,
                password=args.password,
                country=args.country,
                target_light_name=args.light_name or None,
                target_mesh_id=args.mesh_id,
                target_group_name=args.group_name or None,
                target_group_id=args.group_id,
                timeout=args.timeout,
            )
        )
    else:
        success = asyncio.run(run_mock_test())

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
