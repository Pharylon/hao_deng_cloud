import asyncio
import json
import logging
import math
import uuid
import time

import paho.mqtt.client as mqtt
import paho.mqtt

from .const import MAGICHUE_COUNTRY_SERVERS
from .pocos import Device, MqttControlData, MqttLightPayload, ExternalColorData

# The callback for when a PUBLISH message is received from the server.

_LOGGER = logging.getLogger(__name__)

lock = asyncio.Lock()


def on_subscribe(client, userdata, mid, granted_qos):
    _LOGGER.debug("Subscribed: %s %s", str(mid), str(granted_qos))


class MqttConnector:
    hardware: MqttControlData
    software: MqttControlData
    client: mqtt.Client
    client_connected: bool = False

    def __init__(
        self,
        controlData: list[MqttControlData],
        country_code: str,
        devices: list[Device] = None,
    ):
        self.subscriptions = []
        self._country_code = country_code
        self._queue: dict[str, MqttLightPayload] = {}
        self._update_timestamps: dict[int, float] = {}
        for x in controlData:
            if x.deviceType == "HARDWARE":
                self.hardware = x
            elif x.deviceType == "SOFTWARE":
                self.software = x
        self._groups: dict[int, list[int]] = {}
        self._control_types: dict[int, int] = {}
        if devices:
            for d in devices:
                self._control_types[d.meshAddress] = d.controlType
                for g in d.groups:
                    if g not in self._groups:
                        self._groups[g] = []
                    self._groups[g].append(d.meshAddress)
            # Derive controlType for group addresses from first member device
            for g_id, member_addrs in self._groups.items():
                if member_addrs and member_addrs[0] in self._control_types:
                    self._control_types[g_id] = self._control_types[member_addrs[0]]

    def _get_control_type_hex(self, device_id: int) -> str:
        """Get the 2-digit hex control type prefix for a device or group address."""
        ct = self._control_types.get(device_id, 5)
        return f"{ct:02X}"

    def get_server_addr(self):
        """Get the server address for the country code."""
        for server in MAGICHUE_COUNTRY_SERVERS:
            if server["nationCode"] == self._country_code:
                return server["brokerApi"]
        return None

    def connect(self):
        def on_connect(client, userdata, flags, rc):
            self.client_connected = True
            _LOGGER.debug(f"Connected with result code {rc}")
            # print("/LCTLdnl8aKqCI/2c9459fd87084f1201873d5b002507bb/subStatus")
            # print(f"/{self.software.productKey}/{self.software.deviceName}/subStatus")
            client.subscribe(
                f"/{self.hardware.productKey}/{self.hardware.deviceName}/subStatus", 1
            )

        def on_message(client, userdata, msg):
            data = json.loads(msg.payload.decode("ASCII"))
            for d in data:
                #_LOGGER.info("ON_MESSAGE: A: %d, D: %s", d["a"], d["d"])
                self._update_timestamps[d["a"]] = time.time()
                color_tuple = self._convert_notification_data_to_color_data(
                    d["d"], d["a"]
                )
                for s in self.subscriptions:
                    s(d["a"], color_tuple)

        mqttc: mqtt.Client
        if paho.mqtt.__version__[0] > '1':
            mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, uuid.uuid4().hex)
        else:
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
        # _LOGGER.info("SET COLOR for %s: %s %s %s", deviceId, red, green, blue)
        if red > 255 or green > 255 or blue > 255 or red < 0 or green < 0 or blue < 0:
            _LOGGER.error("Invalid RGB values")
            return
        while red + green + blue > 630:
            red = red - 1
            green = green - 1
            blue = blue - 1
        hexValue = f"{int(red):02x}{int(green):02x}{int(blue):02x}".upper()
        ct = self._get_control_type_hex(deviceId)
        payload = MqttLightPayload(deviceId, "E2", f"{ct}60{hexValue}00000200")
        # _LOGGER.info("Adding to que %s", payload.dstAdr)
        await self._add_to_queue(payload)

    async def turn_on(self, deviceId: int):
        """Turn the light on."""
        _LOGGER.debug("TURN_ON for ID %s", deviceId)
        ct = self._get_control_type_hex(deviceId)
        payload = MqttLightPayload(deviceId, "D0", f"{ct}01FF000000000300")
        await self._add_to_queue(payload)

    async def turn_off(self, deviceId: int):
        """Turn the light off."""
        _LOGGER.debug("TURN_OFF for ID %s", deviceId)
        ct = self._get_control_type_hex(deviceId)
        payload = MqttLightPayload(deviceId, "D0", f"{ct}0100000000000300")
        await self._add_to_queue(payload)

    async def set_color_temp(self, deviceId: int, color_temp: int, brigthness: int):
        """Set color temperature of light."""
        color_temp = color_temp or 5000
        if 2500 <= color_temp <= 6535:
            # Calculate the proportion of the input number within its range
            proportion = (color_temp - 2500) / (6535 - 2500)
            # Scale the proportion to the output range (0-100)
            translated_number = proportion * 100
            hex_value = f"{int(translated_number):02x}".upper()
            brightness_percent = int(math.ceil(brigthness * 100 / 255))
            brightness_hexe = f"{brightness_percent:02x}".upper()
            ct = self._get_control_type_hex(deviceId)
            payload = MqttLightPayload(
                deviceId, "E2", f"{ct}62{hex_value}{brightness_hexe}0000000200"
            )
            await self._add_to_queue(payload)

    def _convert_notification_to_color_temp(
        self, data: str, id: int
    ) -> ExternalColorData:
        colorTemp_hex = data[6:8]
        colorTemp_percent = int(colorTemp_hex, 16) / 100
        output_range = 6535 - 2500
        color_temp = int(colorTemp_percent * output_range + 2500)
        brightness = data[2:4]
        bright_percent = int(brightness, 16) / 100
        ecd = ExternalColorData(
            False, None, [color_temp, bright_percent], data[0:2] != "00"
        )
        # _LOGGER.info(
        #     "%s - Converting notification of %s to %s", id, data, repr(ecd.__dict__)
        # )

        return ecd

    def _convert_notification_data_to_color_data(
        self, data: str, id: int
    ) -> ExternalColorData:
        try:
            saturation = data[4:6]
            saturation_percent = int(saturation, 16) / 63
            if saturation_percent > 1:
                return self._convert_notification_to_color_temp(data, id)
            hue = data[6:8]
            hue_percent = int(hue, 16) / 255
            hue_360 = 360 * hue_percent
            brightness = data[2:4]
            bright_percent = int(brightness, 16) / 100
            # _LOGGER.info("Incoming Bright %s %s", brightness, bright_percent)
            if saturation_percent == 0 or bright_percent == 0:
                return ExternalColorData(True, [0, 0, 0], [0, 0], data[0:2] != "00")
            # rgb = hsl_to_rgb(hue_360, saturation_percent, bright_percent)
            ecd = ExternalColorData(
                True,
                [hue_360, saturation_percent, bright_percent],
                None,
                data[0:2] != "00",
            )
            # _LOGGER.info(
            #     "%s - Converting notification of %s to %s", id, data, repr(ecd.__dict__)
            # )
            return ecd
        except Exception as e:
            _LOGGER.error(e)
            return ExternalColorData(False, [0, 0, 0], None, False)

    def subscribe(self, callback):
        self.subscriptions.append(callback)

    def request_status(self):
        payloadJson = json.dumps({"type": "immediateNOW", "ver": 1})
        self.client.publish(
            f"/{self.software.productKey}/{self.software.deviceName}/request",
            payloadJson,
        )

    async def _send_queue(self):
        if len(self._queue) > 0:
            queue_items = list(self._queue.values())
            for p in queue_items:
                payloadJson = json.dumps(p.__dict__)
                _LOGGER.debug("Sending payload for id %s: %s", p.dstAdr, payloadJson)
                self.client.publish(
                    f"/{self.software.productKey}/{self.software.deviceName}/control",
                    payloadJson,
                    qos=1,
                )
            self._ensure_queue_sent(queue_items)
            await asyncio.sleep(0.1)

    def _ensure_queue_sent(self, queue_items: list[MqttLightPayload]):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 'RuntimeError: There is no current event loop...'
            loop = None
        if loop and loop.is_running():
            loop.create_task(self._wait_and_retry_queue(queue_items))

    async def _wait_and_retry_queue(self, queue_items: list[MqttLightPayload]):
        await asyncio.sleep(3)
        for queue_item in queue_items:
            dst_adr = queue_item.dstAdr
            # Check if this destination address is a group
            if dst_adr in self._groups:
                group_members = self._groups[dst_adr]
                if group_members:
                    all_updated = all(
                        time.time() - self._update_timestamps.get(addr, 0) <= 5
                        for addr in group_members
                    )
                    if not all_updated:
                        _LOGGER.warning(
                            "Didn't get updates for all lights in group %s, resending",
                            dst_adr,
                        )
                        payloadJson = json.dumps(queue_item.__dict__)
                        self.client.publish(
                            f"/{self.software.productKey}/{self.software.deviceName}/control",
                            payloadJson,
                            qos=1,
                        )
                        await asyncio.sleep(0.1)
                    else:
                        _LOGGER.debug(
                            "All lights in group %s updated after send", dst_adr
                        )
            else:
                last_update = self._update_timestamps.get(dst_adr, 0)
                if time.time() - last_update > 5:
                    # We sent an update, but didn't receive a corresponding update from the broker, retry
                    _LOGGER.warning("Didn't get update for %s, resending", dst_adr)
                    payloadJson = json.dumps(queue_item.__dict__)
                    self.client.publish(
                        f"/{self.software.productKey}/{self.software.deviceName}/control",
                        payloadJson,
                        qos=1,
                    )
                    await asyncio.sleep(0.1)
                else:
                    _LOGGER.debug("Light %s updated after send", dst_adr)

    async def _add_to_queue(self, payload: MqttLightPayload):
        async with lock:
            self._queue.update({payload.dstAdr: payload})
        await asyncio.sleep(0.01)
        async with lock:
            await self._send_queue()
            self._queue = {}
