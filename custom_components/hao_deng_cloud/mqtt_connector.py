import asyncio
import json
import logging
import math
import uuid

import paho.mqtt.client as mqtt

from .color_helper import hsl_to_rgb
from .const import MAGICHUE_COUNTRY_SERVERS
from .pocos import Device, MqttControlData, MqttLightPayload

# The callback for when a PUBLISH message is received from the server.

_LOGGER = logging.getLogger(__name__)

lock = asyncio.Lock()

__SLEEP_TIME__ = 0.1


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
        self._devices: list[Device] = devices
        self._queue: list[MqttLightPayload] = []
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
                # _LOGGER.info("ON_MESSAGE: A: %d, D: %s", d["a"], d["d"])
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
        _LOGGER.info("SET COLOR")
        if red > 255 or green > 255 or blue > 255 or red < 0 or green < 0 or blue < 0:
            _LOGGER.error("Invalid RGB values")
            return
        while red + green + blue > 630:
            red = red - 1
            green = green - 1
            blue = blue - 1
        hexValue = f"{int(red):02x}{int(green):02x}{int(blue):02x}".upper()
        payload = MqttLightPayload(deviceId, "E2", f"0560{hexValue}00000200")
        _LOGGER.info("Adding to que %s", payload.dstAdr)
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
            await self._add_to_queue(payload)

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
        payloadJson = json.dumps({"type": "immediateNOW", "ver": 1})
        self.client.publish(
            f"/{self.software.productKey}/{self.software.deviceName}/request",
            payloadJson,
        )

    def _group_payloads_by_op_code(
        self, payloads: list[MqttLightPayload]
    ) -> dict[int, list[MqttLightPayload]]:
        grouped_by_op_code = {}
        for p in payloads:
            if p.opCode not in grouped_by_op_code:
                grouped_by_op_code[p.opCode] = []
            grouped_by_op_code[p.opCode].append(p)
        return grouped_by_op_code

    def _group_payloads_by_data(
        self, payloads: list[MqttLightPayload]
    ) -> dict[int, list[MqttLightPayload]]:
        grouped_by_data = {}
        for p in payloads:
            if p.data not in grouped_by_data:
                grouped_by_data[p.data] = []
            grouped_by_data[p.data].append(p)
        return grouped_by_data

    def _group_payloads_by_group_id(self, payloads: list[MqttLightPayload]):
        """Group all payloads by their group ID, so we can send the control message to the group instead of each individual device."""
        group_buckets = {}
        for p in payloads:
            for d in self._devices:
                if d.meshAddress == p.dstAdr:
                    for g in d.groups:
                        if g > 0:
                            if g not in group_buckets:
                                group_buckets[g] = []
                            group_buckets[g].append(p)
                            _LOGGER.info("Adding %s to %g", p.dstAdr, g)
        # Order the groups from largest to most to least full
        sorted_groups = sorted(
            group_buckets.items(), key=lambda item: len(item[1]), reverse=True
        )
        return sorted_groups

    def _create_group_payloads(self, payloads):
        # queue_ids = [p.dstAdr for p in self._queue]
        # print("MyQueue", queue_ids)
        final_paylods: list[MqttLightPayload] = []
        sending_destinations: list[int] = []
        grouped_requests = self._group_payloads_by_group_id(payloads)
        # print("Grouped Length ", len(grouped_requests))
        for my_tuple in grouped_requests:
            groupId: int = my_tuple[0]
            payload_list: list[MqttLightPayload] = my_tuple[1]
            # print(f"Starting Group ID {groupId} Len ", len(payload_list))
            paylods_not_queued = [
                p for p in payload_list if p.dstAdr not in sending_destinations
            ]
            if len(paylods_not_queued) > 0:
                for p in paylods_not_queued:
                    sending_destinations.extend([p.dstAdr])
                    # print("Sending Destingations", sending_destinations)
                payload_for_group = MqttLightPayload(
                    groupId, payload_list[0].opCode, payload_list[0].data
                )
                payload_for_group.dstAdr = groupId
                final_paylods.append(payload_for_group)
        # These paylods were not sent as part of a group
        # print("NOt Final_not_queued %s", len(paylods_not_queued))
        # print("SENDING DEST", sending_destinations)
        paylods_not_queued = [
            p for p in payloads if p.dstAdr not in sending_destinations
        ]
        # queue_ids = [p.dstAdr for p in self._queue]
        # print("MyQueue", queue_ids)
        # payload_ids_not_qued = [p.dstAdr for p in paylods_not_queued]
        # print("Final_not_queued ", payload_ids_not_qued)
        final_paylods.extend(paylods_not_queued)
        # print("Number of payloads to send: ", len(final_paylods))
        return final_paylods

    def _send_queue(self):
        if len(self._queue) > 0:
            grouped_by_op_code = self._group_payloads_by_op_code(self._queue)
            for op_code_group in grouped_by_op_code.values():
                grouped_by_data = self._group_payloads_by_data(op_code_group)
                for data_group in grouped_by_data.values():
                    final_paylods: list[MqttLightPayload] = self._create_group_payloads(
                        data_group
                    )
                    while len(final_paylods) > 0:
                        _LOGGER.info("Final Payload Length %s", len(final_paylods))
                        first_three = final_paylods[:3]
                        for p in first_three:
                            payloadJson = json.dumps(p.__dict__)
                            _LOGGER.info("Sending payload for id %s", p.dstAdr)
                            self.client.publish(
                                f"/{self.software.productKey}/{self.software.deviceName}/control",
                                payloadJson,
                            )
                        del final_paylods[:3]

    async def _add_to_queue(self, payload: MqttLightPayload):
        _LOGGER.info("Queueing %s ", payload.dstAdr)
        async with lock:
            self._queue.append(payload)
        # Wait a very short period to see if other requests get put in the queue
        await asyncio.sleep(0.01)
        async with lock:
            self._send_queue()
            self._queue = []
            await asyncio.sleep(__SLEEP_TIME__)
