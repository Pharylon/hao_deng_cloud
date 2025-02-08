import asyncio
import json
import logging
import math
import uuid
import time

import paho.mqtt.client as mqtt

from .const import MAGICHUE_COUNTRY_SERVERS
from .pocos import Device, MqttControlData, MqttLightPayload, ExternalColorData

# The callback for when a PUBLISH message is received from the server.

_LOGGER = logging.getLogger(__name__)

lock = asyncio.Lock()


def on_subscribe(client, userdata, mid, granted_qos):
    _LOGGER.info("Subscribed: %s %s", str(mid), str(granted_qos))


class MqttConnector:
    hardware: MqttControlData
    software: MqttControlData
    client: mqtt.Client
    client_connected: bool = False

    def __init__(
        self,
        controlData: list[MqttControlData],
        country_code: str,
        devices: list[Device],
    ):
        self.subscriptions = []
        self._country_code = country_code
        self._queue: list[MqttLightPayload] = []
        self._update_timestamps = {}
        for x in controlData:
            if x.deviceType == "HARDWARE":
                self.hardware = x
            elif x.deviceType == "SOFTWARE":
                self.software = x
        self._groups: dict[int, list[int]] = {}
        self._devices = devices
        for d in devices:
            for g in d.groups:
                if g not in self._groups:
                    self._groups[g] = []
                self._groups[g].append(d.meshAddress)

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
                # _LOGGER.info("ON_MESSAGE: A: %d, D: %s", d["a"], d["d"])
                for s in self.subscriptions:
                    color_tuple = self._convert_notification_data_to_color_data(
                        d["d"], d["a"]
                    )
                    s(d["a"], color_tuple)
                    self._update_timestamps.update({d["a"]: time.time()})

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
        payload = MqttLightPayload(deviceId, "E2", f"0560{hexValue}00000200")
        # _LOGGER.info("Adding to que %s", payload.dstAdr)
        await self._add_to_queue(payload)

    async def turn_on(self, deviceId: int):
        """Turn the light on."""
        _LOGGER.info("TURN_ON for ID %s", deviceId)
        payload = MqttLightPayload(deviceId, "D0", "0501FF000000000300")
        await self._add_to_queue(payload)

    async def turn_off(self, deviceId: int):
        """Turn the light off."""
        _LOGGER.info("TURN_OFF for ID %s", deviceId)
        payload = MqttLightPayload(deviceId, "D0", "050100000000000300")
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
            payload = MqttLightPayload(
                deviceId, "E2", f"0562{hex_value}{brightness_hexe}0000000200"
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
                return ExternalColorData(True, [0, 0, 0], [0, 0], data[0:2] == "00")
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

    def _group_payloads_by_data(
        self, payloads: list[MqttLightPayload]
    ) -> dict[int, list[MqttLightPayload]]:
        grouped_by_data = {}
        for p in payloads:
            if p.data not in grouped_by_data:
                grouped_by_data[p.data] = []
            grouped_by_data[p.data].append(p)
        return grouped_by_data

    def _group_payloads_by_op_code(
        self, payloads: list[MqttLightPayload]
    ) -> dict[int, list[MqttLightPayload]]:
        grouped_by_op_code = {}
        for p in payloads:
            if p.opCode not in grouped_by_op_code:
                grouped_by_op_code[p.opCode] = []
            grouped_by_op_code[p.opCode].append(p)
        return grouped_by_op_code

    def _create_group_payloads(self, payloads: list[MqttLightPayload]):
        """Group all payloads by their group ID, so we can send the control message to the group instead of each individual device.
        Payloads should already have the same OpCode and Data at this stage.
        """  # noqa: D205

        final_payloads: list[MqttLightPayload] = []
        # _LOGGER.info("Payload len befor mesh addresses: %s", len(payloads))
        mesh_addresses = [x.dstAdr for x in payloads]
        # _LOGGER.info("Mesh addresses: %s", mesh_addresses)
        for group_id, group_addresses in self._groups.items():
            # _LOGGER.info("Group ID %s, group addresses: %s", group_id, group_addresses)
            if all(addr in mesh_addresses for addr in group_addresses):
                group_payload = MqttLightPayload(
                    group_id, payloads[0].opCode, payloads[0].data
                )
                final_payloads.append(group_payload)
        group_address_payloads = [x.dstAdr for x in final_payloads]
        for p in payloads:
            device = next((x for x in self._devices if x.meshAddress == p.dstAdr), None)
            if device is not None:
                already_queued = [
                    g_id for g_id in device.groups if g_id in group_address_payloads
                ]
                if len(already_queued) == 0:
                    final_payloads.append(p)
        return final_payloads

    async def _send_queue(self):
        if len(self._queue) > 0:
            grouped_by_op_code = self._group_payloads_by_op_code(self._queue)
            for op_code_group in grouped_by_op_code.values():
                grouped_by_data = self._group_payloads_by_data(op_code_group)
                for data_group in grouped_by_data.values():
                    final_paylods: list[MqttLightPayload] = self._create_group_payloads(
                        data_group
                    )
                    for p in final_paylods:
                        payloadJson = json.dumps(p.__dict__)
                        _LOGGER.info(
                            "Sending payload for id %s: %s", p.dstAdr, payloadJson
                        )
                        self.client.publish(
                            f"/{self.software.productKey}/{self.software.deviceName}/control",
                            payloadJson,
                            qos=1,
                        )
            self._ensure_queue_sent()
            await asyncio.sleep(0.1)

    def _ensure_queue_sent(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 'RuntimeError: There is no current event loop...'
            loop = None
        if loop and loop.is_running():
            loop.create_task(self._wait_and_retry_queue(self._queue))

    async def _wait_and_retry_queue(self, queue: list[MqttLightPayload]):
        await asyncio.sleep(3)
        for queue_item in queue:
            last_update = self._update_timestamps[queue_item.dstAdr]
            if time.time() - last_update > 5:
                # We sent a upate, but didn't recieve a corresponding update from the broker, retry
                _LOGGER.warning(
                    "Didn't get update for %s, resending", queue_item.dstAdr
                )
                payloadJson = json.dumps(queue_item.__dict__)
                self.client.publish(
                    f"/{self.software.productKey}/{self.software.deviceName}/control",
                    payloadJson,
                    qos=1,
                )
                await asyncio.sleep(0.1)
            else:
                _LOGGER.info("Light %s, updated after send", queue_item.dstAdr)

    async def _add_to_queue(self, payload: MqttLightPayload):
        # _LOGGER.info("Queueing %s ", payload.dstAdr)
        async with lock:
            self._queue.append(payload)
        # queue_length = len(self._queue)
        # Wait a very short period to see if other requests get put in the queue
        await asyncio.sleep(0.01)
        # new_queue_length = len(self._queue)
        # while queue_length != new_queue_length:
        #     _LOGGER.info("Adding to queue. Current length: %s", len(self._queue))
        #     queue_length = new_queue_length
        #     await asyncio.sleep(0.01)
        #     new_queue_length = len(self._queue)
        # _LOGGER.info("Done making queue. CUrrent length: %s", len(self._queue))
        async with lock:
            await self._send_queue()
            self._queue = []
