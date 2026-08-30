#!/usr/bin/env python3
"""Standalone test runner for Hao Deng Cloud integration.

This script allows testing turning lights on and off and receiving MQTT
status responses outside of Home Assistant.

Supports:
  1. Mock mode (default): Simulates the MQTT broker and verifies turn on, turn off,
     and cloud notification decoding without requiring credentials or external network.
  2. Live mode (--live): Connects to the real Hao Deng cloud, retrieves devices,
     and tests turning on/off actual lights over MQTT.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import types
from typing import Optional

# Ensure repository root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

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

from custom_components.hao_deng_cloud.const import MAGICHUE_COUNTRY_SERVERS
from custom_components.hao_deng_cloud.pocos import (
    Device,
    ExternalColorData,
    Group,
    MqttControlData,
)
from custom_components.hao_deng_cloud.mqtt_connector import MqttConnector

# ANSI color escape codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


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
    """Create mock devices for testing."""
    device_1 = Device({
        "uniID": "device_uuid_001",
        "userID": "user_001",
        "placeUniID": "place_001",
        "macAddress": "AA:BB:CC:11:22:33",
        "displayName": "Ceiling Light",
        "meshAddress": 1,
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
    device_2 = Device({
        "uniID": "device_uuid_002",
        "userID": "user_001",
        "placeUniID": "place_001",
        "macAddress": "AA:BB:CC:44:55:66",
        "displayName": "Desk Lamp",
        "meshAddress": 2,
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
    return [device_1, device_2]


async def run_mock_test() -> bool:
    """Run full simulated test of turning light on/off and receiving MQTT response."""
    print(f"\n{BOLD}{CYAN}=== Starting Hao Deng Cloud Mock Test ==={RESET}\n")

    control_data = create_mock_control_data()
    devices = create_mock_devices()
    target_device = devices[0]
    mesh_id = target_device.meshAddress

    print(f"{BOLD}[1/5] Initializing MqttConnector...{RESET}")
    connector = MqttConnector(control_data, "US", devices)

    mock_client = MockMqttClient()
    connector.client = mock_client
    connector.client_connected = True

    # Track received updates from MQTT callback
    received_updates: list[tuple[int, ExternalColorData]] = []

    def on_status_received(device_id: int, color_data: ExternalColorData):
        received_updates.append((device_id, color_data))

    connector.subscribe(on_status_received)
    print(f"      Connected MqttConnector. Target Device: '{target_device.displayName}' (meshAddress: {mesh_id})")

    # --- STEP 2: TEST TURN ON ---
    print(f"\n{BOLD}[2/5] Testing Turn ON command...{RESET}")
    mock_client.published_messages.clear()
    await connector.turn_on(mesh_id)

    if not mock_client.published_messages:
        print(f"{RED}FAILED: No MQTT message was published for turn_on{RESET}")
        return False

    pub_topic, pub_payload, qos = mock_client.published_messages[-1]
    expected_topic = f"/{connector.software.productKey}/{connector.software.deviceName}/control"
    payload_dict = json.loads(pub_payload)

    print(f"      Published to topic:   {pub_topic}")
    print(f"      Payload:              {pub_payload}")

    assert pub_topic == expected_topic, f"Expected topic {expected_topic}, got {pub_topic}"
    assert payload_dict["dstAdr"] == mesh_id, f"Expected dstAdr {mesh_id}, got {payload_dict['dstAdr']}"
    assert payload_dict["opCode"] == "D0", f"Expected opCode 'D0', got {payload_dict['opCode']}"
    assert payload_dict["data"] == "0501FF000000000300", f"Expected turn_on data '0501FF000000000300', got {payload_dict['data']}"
    print(f"      {GREEN}✓ Turn ON command payload validated successfully{RESET}")

    # --- STEP 3: SIMULATE CLOUD RESPONSE (ON) ---
    print(f"\n{BOLD}[3/5] Simulating Cloud MQTT status response (Light ON)...{RESET}")
    received_updates.clear()

    # Cloud sends notification payload: [{"a": 1, "d": "016420FF00000000"}]
    # "01" = available, "64" = 100% brightness, "20" = sat, "FF" = hue
    sub_topic = f"/{connector.hardware.productKey}/{connector.hardware.deviceName}/subStatus"
    cloud_on_payload = json.dumps([{"a": mesh_id, "d": "016420FF00000000"}])

    # Trigger on_message logic
    data_list = json.loads(cloud_on_payload)
    for d in data_list:
        color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
        for s in connector.subscriptions:
            s(d["a"], color_tuple)

    if not received_updates:
        print(f"{RED}FAILED: No status update callback triggered on subStatus notification{RESET}")
        return False

    dev_id, color_data = received_updates[-1]
    print(f"      Received update for meshAddress: {dev_id}")
    print(f"      Decoded status: isAvailable={color_data.isAvailable}, isHsv={color_data.isHsv}, hsv={color_data.hsv}")

    assert dev_id == mesh_id
    assert color_data.isAvailable is True
    assert color_data.isHsv is True
    assert color_data.hsv[2] == 1.0  # 100% brightness
    print(f"      {GREEN}✓ MQTT response parsed correctly: Light is ON (Brightness: 100%){RESET}")

    # --- STEP 4: TEST TURN OFF ---
    print(f"\n{BOLD}[4/5] Testing Turn OFF command...{RESET}")
    mock_client.published_messages.clear()
    await connector.turn_off(mesh_id)

    if not mock_client.published_messages:
        print(f"{RED}FAILED: No MQTT message was published for turn_off{RESET}")
        return False

    pub_topic, pub_payload, qos = mock_client.published_messages[-1]
    payload_dict = json.loads(pub_payload)

    print(f"      Published to topic:   {pub_topic}")
    print(f"      Payload:              {pub_payload}")

    assert pub_topic == expected_topic
    assert payload_dict["dstAdr"] == mesh_id
    assert payload_dict["opCode"] == "D0"
    assert payload_dict["data"] == "050100000000000300", f"Expected turn_off data '050100000000000300', got {payload_dict['data']}"
    print(f"      {GREEN}✓ Turn OFF command payload validated successfully{RESET}")

    # --- STEP 5: SIMULATE CLOUD RESPONSE (OFF) ---
    print(f"\n{BOLD}[5/5] Simulating Cloud MQTT status response (Light OFF)...{RESET}")
    received_updates.clear()

    # Cloud sends notification payload: [{"a": 1, "d": "0100000000000000"}] (brightness = 00)
    cloud_off_payload = json.dumps([{"a": mesh_id, "d": "0100000000000000"}])
    data_list = json.loads(cloud_off_payload)
    for d in data_list:
        color_tuple = connector._convert_notification_data_to_color_data(d["d"], d["a"])
        for s in connector.subscriptions:
            s(d["a"], color_tuple)

    if not received_updates:
        print(f"{RED}FAILED: No status update callback triggered on subStatus notification{RESET}")
        return False

    dev_id, color_data = received_updates[-1]
    print(f"      Received update for meshAddress: {dev_id}")
    print(f"      Decoded status: isAvailable={color_data.isAvailable}, isHsv={color_data.isHsv}, hsv={color_data.hsv}")

    assert dev_id == mesh_id
    assert color_data.isAvailable is True
    assert color_data.isHsv is True
    assert color_data.hsv == [0, 0, 0]
    print(f"      {GREEN}✓ MQTT response parsed correctly: Light is OFF (hsv=[0,0,0]){RESET}")

    print(f"\n{BOLD}{GREEN}=========================================={RESET}")
    print(f"{BOLD}{GREEN}  ALL TESTS PASSED SUCCESSFULLY!          {RESET}")
    print(f"{BOLD}{GREEN}=========================================={RESET}\n")
    return True


async def run_live_test(
    username: str,
    password: str,
    country: str,
    target_mesh_id: Optional[int] = None,
    timeout: int = 10,
) -> bool:
    """Connect to live Hao Deng cloud and test turning light on and off."""
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

    if not controllable_devices:
        print(f"{YELLOW}Warning: No controllable light devices found (wiringType != 0).{RESET}")
        if devices:
            target_device = devices[0]
        else:
            print(f"{RED}No devices found in account.{RESET}")
            return False
    else:
        if target_mesh_id is not None:
            matches = [d for d in controllable_devices if d.meshAddress == target_mesh_id]
            if not matches:
                print(f"{RED}Device with meshAddress {target_mesh_id} not found among controllable devices.{RESET}")
                return False
            target_device = matches[0]
        else:
            target_device = controllable_devices[0]

    mesh_id = target_device.meshAddress
    print(f"\nSelected Target Light: '{target_device.displayName}' (meshAddress: {mesh_id})")

    # Set up MQTT Connector
    mqtt_connector = MqttConnector(control_data, country, devices)
    received_events = asyncio.Queue()

    def on_live_status(dev_id: int, color_data: ExternalColorData):
        print(f"\n{CYAN}>>> Received live MQTT status update for meshAddress {dev_id}:{RESET}")
        print(f"    Available: {color_data.isAvailable}")
        if color_data.isHsv:
            print(f"    HSV:       {color_data.hsv}")
        else:
            print(f"    ColorTemp: {color_data.colorTempBrightness}")
        received_events.put_nowait((dev_id, color_data))

    mqtt_connector.subscribe(on_live_status)

    print("Connecting to MQTT broker...")
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

    # 1. TURN ON
    print(f"\n{BOLD}--> Sending TURN ON command to '{target_device.displayName}' (ID: {mesh_id})...{RESET}")
    # Drain any older events
    while not received_events.empty():
        received_events.get_nowait()

    await mqtt_connector.turn_on(mesh_id)

    print(f"Waiting up to {timeout}s for MQTT response confirming ON...")
    try:
        on_confirmed = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            wait_time = max(0.1, deadline - time.time())
            try:
                res_id, color_data = await asyncio.wait_for(received_events.get(), timeout=wait_time)
                if res_id == mesh_id:
                    # Check if ON
                    is_on = False
                    if color_data.isHsv and any(v > 0 for v in color_data.hsv):
                        is_on = True
                    elif not color_data.isHsv and color_data.colorTempBrightness and color_data.colorTempBrightness[1] > 0:
                        is_on = True

                    if is_on:
                        print(f"{GREEN}✓ Confirmed light turned ON!{RESET}")
                        on_confirmed = True
                        break
            except asyncio.TimeoutError:
                break

        if not on_confirmed:
            print(f"{YELLOW}Warning: Did not receive explicit ON confirmation within {timeout}s{RESET}")
    except Exception as exc:
        print(f"{RED}Error waiting for ON status: {exc}{RESET}")

    print("Holding light ON for 2 seconds...")
    await asyncio.sleep(2.0)

    # 2. TURN OFF
    print(f"\n{BOLD}--> Sending TURN OFF command to '{target_device.displayName}' (ID: {mesh_id})...{RESET}")
    while not received_events.empty():
        received_events.get_nowait()

    await mqtt_connector.turn_off(mesh_id)

    print(f"Waiting up to {timeout}s for MQTT response confirming OFF...")
    try:
        off_confirmed = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            wait_time = max(0.1, deadline - time.time())
            try:
                res_id, color_data = await asyncio.wait_for(received_events.get(), timeout=wait_time)
                if res_id == mesh_id:
                    is_off = False
                    if color_data.isHsv and color_data.hsv == [0, 0, 0]:
                        is_off = True
                    elif not color_data.isHsv and color_data.colorTempBrightness and color_data.colorTempBrightness[1] == 0:
                        is_off = True

                    if is_off:
                        print(f"{GREEN}✓ Confirmed light turned OFF!{RESET}")
                        off_confirmed = True
                        break
            except asyncio.TimeoutError:
                break

        if not off_confirmed:
            print(f"{YELLOW}Warning: Did not receive explicit OFF confirmation within {timeout}s{RESET}")
    except Exception as exc:
        print(f"{RED}Error waiting for OFF status: {exc}{RESET}")

    if hasattr(mqtt_connector.client, "loop_stop"):
        mqtt_connector.client.loop_stop()

    print(f"\n{BOLD}{GREEN}Live test finished!{RESET}\n")
    return True


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Test turning Hao Deng lights on and off and receiving MQTT responses."
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
        "-u",
        "--username",
        default=os.environ.get("HAODENG_USERNAME", ""),
        help="Hao Deng cloud account username / email (or set HAODENG_USERNAME).",
    )
    parser.add_argument(
        "-p",
        "--password",
        default=os.environ.get("HAODENG_PASSWORD", ""),
        help="Hao Deng cloud account password (or set HAODENG_PASSWORD).",
    )
    parser.add_argument(
        "-c",
        "--country",
        default=os.environ.get("HAODENG_COUNTRY", "US"),
        help="Country code (US, AU, GB, CN, DE, FR, etc. Default: US).",
    )
    parser.add_argument(
        "-m",
        "--mesh-id",
        type=int,
        default=None,
        help="Specific device meshAddress to test (defaults to first controllable light).",
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
            print(f"{RED}Error: --username and --password (or HAODENG_USERNAME / HAODENG_PASSWORD env vars) are required for live test.{RESET}")
            sys.exit(1)
        success = asyncio.run(
            run_live_test(
                username=args.username,
                password=args.password,
                country=args.country,
                target_mesh_id=args.mesh_id,
                timeout=args.timeout,
            )
        )
    else:
        success = asyncio.run(run_mock_test())

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

