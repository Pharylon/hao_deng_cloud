"""Unit tests for MqttConnector."""

import asyncio
import json
import sys
import types
import unittest
from unittest.mock import MagicMock

# Provide mock paho.mqtt if not installed in the environment
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
        paho_client.Client = MagicMock
        sys.modules["paho"] = paho
        sys.modules["paho.mqtt"] = paho_mqtt
        sys.modules["paho.mqtt.client"] = paho_client

from custom_components.hao_deng_cloud.pocos import (
    Device,
    ExternalColorData,
    MqttControlData,
)
from custom_components.hao_deng_cloud.mqtt_connector import MqttConnector


def create_sample_control_data() -> list[MqttControlData]:
    """Create sample hardware and software MqttControlData."""
    hw_raw = {
        "deviceName": "hw_test_device",
        "devicePwd": "hw_password_123",
        "productKey": "HW_PROD_KEY",
        "deviceType": "HARDWARE",
        "macAddress": "AA:BB:CC:DD:EE:01",
        "loadDeviceUrl": "http://example.com/hw",
    }
    sw_raw = {
        "deviceName": "sw_test_device",
        "devicePwd": "sw_password_456",
        "productKey": "SW_PROD_KEY",
        "deviceType": "SOFTWARE",
        "macAddress": "AA:BB:CC:DD:EE:02",
        "loadDeviceUrl": "http://example.com/sw",
    }
    return [MqttControlData(hw_raw), MqttControlData(sw_raw)]


def create_sample_device(mesh_address: int = 1, groups: list[int] = None) -> Device:
    """Create sample Device."""
    if groups is None:
        groups = [10]
    raw = {
        "uniID": "uni_device_001",
        "userID": "user_123",
        "placeUniID": "place_001",
        "macAddress": "AA:BB:CC:DD:EE:FF",
        "displayName": "Living Room Light",
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
    }
    return Device(raw)


class TestMqttConnector(unittest.IsolatedAsyncioTestCase):
    """Test suite for MqttConnector turning on/off and receiving responses."""

    def setUp(self):
        """Set up test environment before each test."""
        self.control_data = create_sample_control_data()
        self.device = create_sample_device(mesh_address=42, groups=[10])
        self.connector = MqttConnector(
            controlData=self.control_data,
            country_code="US",
            devices=[self.device],
        )

        # Mock the underlying paho MQTT client
        self.mock_client = MagicMock()
        self.connector.client = self.mock_client
        self.connector.client_connected = True

    def test_initialization_and_group_mapping(self):
        """Verify initialization of hardware, software, and group mappings."""
        self.assertEqual(self.connector.hardware.deviceName, "hw_test_device")
        self.assertEqual(self.connector.software.deviceName, "sw_test_device")
        self.assertEqual(self.connector._country_code, "US")
        self.assertEqual(self.connector.get_server_addr(), "us.meshbroker.magichue.net")
        self.assertIn(10, self.connector._groups)
        self.assertEqual(self.connector._groups[10], [42])

    async def test_turn_on_command_and_received_response(self):
        """Test sending turn_on and receiving the incoming status notification."""
        received_updates = []

        def callback(mesh_id: int, color_data: ExternalColorData):
            received_updates.append((mesh_id, color_data))

        self.connector.subscribe(callback)

        # 1. Test sending turn_on
        target_id = 42
        await self.connector.turn_on(target_id)

        # Check published message
        self.mock_client.publish.assert_called()
        call_args = self.mock_client.publish.call_args
        topic, payload_str = call_args[0][0], call_args[0][1]
        qos = call_args[1].get("qos", 0)

        expected_topic = f"/{self.connector.software.productKey}/{self.connector.software.deviceName}/control"
        self.assertEqual(topic, expected_topic)
        self.assertEqual(qos, 1)

        payload = json.loads(payload_str)
        self.assertEqual(payload["dstAdr"], target_id)
        self.assertEqual(payload["opCode"], "D0")
        self.assertEqual(payload["data"], "0501FF000000000300")

        # 2. Simulate MQTT broker publishing status response on subStatus
        # Status payload format: [{"a": deviceId, "d": "0164640000000000"}]
        # d format: [0:2]=isAvailable ("01"), [2:4]=brightness hex ("64" -> 100%), [4:6]=saturation hex ("64"), [6:8]=hue hex
        mock_msg = MagicMock()
        incoming_payload = json.dumps([{"a": target_id, "d": "016420FF00000000"}])
        mock_msg.payload = incoming_payload.encode("ASCII")

        # Extract on_message handler from connect or simulate it directly
        # Let's verify on_message processing
        on_message = None

        def fake_on_connect(client, userdata, flags, rc):
            pass

        # Call connect to wire up callbacks if needed, or invoke the parser directly
        # Let's test the connector's on_message logic
        color_tuple = self.connector._convert_notification_data_to_color_data(
            "016420FF00000000", target_id
        )
        for s in self.connector.subscriptions:
            s(target_id, color_tuple)

        self.assertEqual(len(received_updates), 1)
        res_id, res_color = received_updates[0]
        self.assertEqual(res_id, target_id)
        self.assertTrue(res_color.isAvailable)
        self.assertTrue(res_color.isHsv)
        self.assertIsNotNone(res_color.hsv)
        # Brightness should be 1.0 (0x64 / 100)
        self.assertEqual(res_color.hsv[2], 1.0)
        # Light is considered ON since hsv values are non-zero
        self.assertTrue(any(v > 0 for v in res_color.hsv))

    async def test_turn_off_command_and_received_response(self):
        """Test sending turn_off and receiving the incoming status notification."""
        received_updates = []

        def callback(mesh_id: int, color_data: ExternalColorData):
            received_updates.append((mesh_id, color_data))

        self.connector.subscribe(callback)

        # 1. Test sending turn_off
        target_id = 42
        await self.connector.turn_off(target_id)

        # Check published message
        self.mock_client.publish.assert_called()
        call_args = self.mock_client.publish.call_args
        topic, payload_str = call_args[0][0], call_args[0][1]
        qos = call_args[1].get("qos", 0)

        expected_topic = f"/{self.connector.software.productKey}/{self.connector.software.deviceName}/control"
        self.assertEqual(topic, expected_topic)
        self.assertEqual(qos, 1)

        payload = json.loads(payload_str)
        self.assertEqual(payload["dstAdr"], target_id)
        self.assertEqual(payload["opCode"], "D0")
        self.assertEqual(payload["data"], "050100000000000300")

        # 2. Simulate cloud response for light turned off: "0100000000000000" (brightness = 0)
        color_tuple = self.connector._convert_notification_data_to_color_data(
            "0100000000000000", target_id
        )
        for s in self.connector.subscriptions:
            s(target_id, color_tuple)

        self.assertEqual(len(received_updates), 1)
        res_id, res_color = received_updates[0]
        self.assertEqual(res_id, target_id)
        self.assertTrue(res_color.isAvailable)
        self.assertTrue(res_color.isHsv)
        # Off state: hsv is [0, 0, 0]
        self.assertEqual(res_color.hsv, [0, 0, 0])

    async def test_set_color(self):
        """Test setting RGB color command."""
        target_id = 42
        await self.connector.set_color(target_id, 255, 0, 128)

        self.mock_client.publish.assert_called()
        call_args = self.mock_client.publish.call_args
        payload = json.loads(call_args[0][1])

        self.assertEqual(payload["dstAdr"], target_id)
        self.assertEqual(payload["opCode"], "E2")
        self.assertEqual(payload["data"], "0560FF008000000200")

    async def test_set_color_temp(self):
        """Test setting color temperature command."""
        target_id = 42
        await self.connector.set_color_temp(target_id, 5000, 255)

        self.mock_client.publish.assert_called()
        call_args = self.mock_client.publish.call_args
        payload = json.loads(call_args[0][1])

        self.assertEqual(payload["dstAdr"], target_id)
        self.assertEqual(payload["opCode"], "E2")
        self.assertTrue(payload["data"].startswith("0562"))

    def test_request_status(self):
        """Test request_status publishes immediateNOW payload."""
        self.connector.request_status()

        self.mock_client.publish.assert_called()
        call_args = self.mock_client.publish.call_args
        expected_topic = f"/{self.connector.software.productKey}/{self.connector.software.deviceName}/request"
        self.assertEqual(call_args[0][0], expected_topic)
        payload = json.loads(call_args[0][1])
        self.assertEqual(payload, {"type": "immediateNOW", "ver": 1})

    def test_notification_decoding_color_temp(self):
        """Test decoding color temperature notifications (saturation > 1)."""
        # When saturation byte > 63 (0x3F), it is parsed as color temperature
        # data: "0164FF6400000000" -> sat="FF" > 63 -> color temp
        ecd = self.connector._convert_notification_data_to_color_data(
            "0164FF6400000000", 42
        )
        self.assertFalse(ecd.isHsv)
        self.assertTrue(ecd.isAvailable)
        self.assertIsNotNone(ecd.colorTempBrightness)
        self.assertGreater(ecd.colorTempBrightness[0], 2500)
        self.assertEqual(ecd.colorTempBrightness[1], 1.0)  # brightness 0x64 = 100%

    def test_notification_decoding_unavailable(self):
        """Test decoding notification when device is unavailable (prefix 00)."""
        ecd = self.connector._convert_notification_data_to_color_data(
            "0000000000000000", 42
        )
        self.assertFalse(ecd.isAvailable)


if __name__ == "__main__":
    unittest.main()

