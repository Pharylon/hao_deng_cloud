import asyncio
import json
import logging
import math
import uuid

import paho.mqtt.client as mqtt

from .color_helper import hsl_to_rgb
from .const import MAGICHUE_COUNTRY_SERVERS
from .pocos import MqttControlData, MqttLightPayload

# The callback for when a PUBLISH message is received from the server.

_LOGGER = logging.getLogger(__name__)

lock = asyncio.Lock()

__SLEEP_TIME__ = 0.05


def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed: " + str(mid) + " " + str(granted_qos))


class MqttConnector:
    hardware: MqttControlData
    software: MqttControlData
    client: mqtt.Client
    client_connected: bool = False

    def __init__(self, controlData: list[MqttControlData], country_code: str):
        self.subscriptions = []
        self._country_code = country_code
        for x in controlData:
            if x.deviceType == "HARDWARE":
                self.hardware = x
            elif x.deviceType == "SOFTWARE":
                self.software = x

    def get_server_addr(self):
        """Get the server address for the country code."""
        for server in MAGICHUE_COUNTRY_SERVERS:
            if server["nationCode"] == self._country_code:
                return server["brokerApi"]
        return None

    def connect(self):
        def on_connect(client, userdata, flags, rc):
            self.client_connected = True
            _LOGGER.info(f"Connected with result code {rc}")
            # print("/LCTLdnl8aKqCI/2c9459fd87084f1201873d5b002507bb/subStatus")
            # print(f"/{self.software.productKey}/{self.software.deviceName}/subStatus")
            client.subscribe(
                f"/{self.hardware.productKey}/{self.hardware.deviceName}/subStatus", 1
            )

        def on_message(client, userdata, msg):
            data = json.loads(msg.payload.decode("ASCII"))
            for d in data:
                _LOGGER.info("ON_MESSAGE: A: %d, D: %s", d["a"], d["d"])
                for s in self.subscriptions:
                    rgb = self.convert_notification_data_to_rgb(d["d"])
                    s(d["a"], rgb)

        mqttc = mqtt.Client(uuid.uuid4().hex)
        mqttc.on_connect = on_connect
        mqttc.on_message = on_message
        mqttc.on_subscribe = on_subscribe
        # mqttc.username_pw_set("504251892088442880&UserPush", "abc")
        mqttc.username_pw_set(
            f"{self.software.deviceName}&{self.software.productKey}",
            self.software.devicePwd,
        )
        mqttc.connect(self.get_server_addr(), 1883, 60)
        self.client = mqttc
        mqttc.loop_start()

    async def set_color(self, deviceId: int, red: int, green: int, blue: int):
        async with lock:
            if (
                red > 255
                or green > 255
                or blue > 255
                or red < 0
                or green < 0
                or blue < 0
            ):
                _LOGGER.error("Invalid RGB values")
                return
            while red + green + blue > 630:
                print(
                    f"Total RGB values too high ({red}/{green}/{blue}). Lowering them for safety"
                )
                red = red - 1
                green = green - 1
                blue = blue - 1
            _LOGGER.info(
                "SET_COLOR for ID %s Red: %s Green %s Blue %s",
                deviceId,
                red,
                green,
                blue,
            )
            hexValue = f"{int(red):02x}{int(green):02x}{int(blue):02x}".upper()
            payload = MqttLightPayload(deviceId, "E2", f"0560{hexValue}00000200")
            payloadJson = json.dumps(payload.__dict__)
            self.client.publish(
                f"/{self.software.productKey}/{self.software.deviceName}/control",
                payloadJson,
            )
            # Sleep is necessary to avoid race condition when updating multiple lights at once.
            # It's unclear if this is an issue with MagicHue or paho-mqtt
            await asyncio.sleep(__SLEEP_TIME__)

    async def turn_on(self, deviceId: int):
        """Turn the light on."""
        async with lock:
            _LOGGER.info("TURN_ON for ID %s", deviceId)
            payload = MqttLightPayload(deviceId, "D0", "0501FF000000000300")
            payloadJson = json.dumps(payload.__dict__)
            response = self.client.publish(
                f"/{self.software.productKey}/{self.software.deviceName}/control",
                payloadJson,
                1,
            )
            response.wait_for_publish(5)
            # Sleep is necessary to avoid race condition when updating multiple lights at once.
            # It's unclear if this is an issue with MagicHue or paho-mqtt
            await asyncio.sleep(__SLEEP_TIME__)

    async def turn_off(self, deviceId: int):
        """Turn the light off."""
        async with lock:
            _LOGGER.info("TURN_OFF for ID %s", deviceId)
            payload = MqttLightPayload(deviceId, "D0", "050100000000000300")
            payloadJson = json.dumps(payload.__dict__)
            response = self.client.publish(
                f"/{self.software.productKey}/{self.software.deviceName}/control",
                payloadJson,
                1,
            )
            response.wait_for_publish(5)
            # Sleep is necessary to avoid race condition when updating multiple lights at once.
            # It's unclear if this is an issue with MagicHue or paho-mqtt
            await asyncio.sleep(__SLEEP_TIME__)

    async def set_color_temp(self, deviceId: int, color_temp: int, brigthness: int):
        """Set color temperature of light."""
        async with lock:
            color_temp = color_temp or 5000
            if 2000 <= color_temp <= 6535:
                # Calculate the proportion of the input number within its range
                proportion = (color_temp - 2000) / (6535 - 2000)
                # Scale the proportion to the output range (0-100)
                translated_number = proportion * 100
                hex_value = f"{int(translated_number):02x}"
                brightness_value = f"{int(math.ceil(brigthness * 64 / 255)):02x}"
                payload = MqttLightPayload(
                    deviceId, "E2", f"0562{hex_value}{brightness_value}0000000200"
                )
                payloadJson = json.dumps(payload.__dict__)
                self.client.publish(
                    f"/{self.software.productKey}/{self.software.deviceName}/control",
                    payloadJson,
                )
                # Sleep is necessary to avoid race condition when updating multiple lights at once.
                # It's unclear if this is an issue with MagicHue or paho-mqtt
                await asyncio.sleep(__SLEEP_TIME__)

    def convert_notification_data_to_rgb(self, data: str) -> tuple[int, int, int]:
        hue = data[6:8]
        hue_percent = int(hue, 16) / 255
        hue_percent = int(hue, 16) / 255
        hue_360 = 360 * hue_percent
        saturation = data[4:6]
        saturation_percent = int(saturation, 16) / 63
        brightness = data[2:4]
        bright_percent = int(brightness, 16) / 100 / 2
        if saturation_percent == 0 or bright_percent == 0:
            return (0, 0, 0)
        return hsl_to_rgb(hue_360, saturation_percent, bright_percent)

    def subscribe(self, callback):
        self.subscriptions.append(callback)

    def request_status(self):
        payloadJson = json.dumps({"type":"immediateNOW","ver":1})
        self.client.publish(f"/{self.software.productKey}/{self.software.deviceName}/request", payloadJson)
