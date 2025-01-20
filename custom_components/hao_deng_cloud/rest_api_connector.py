"""REST API Connector."""

import binascii
import hashlib
import logging
import time
import urllib
import uuid

import aiohttp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import MAGICHUE_COUNTRY_SERVERS
from .pocos import Device, MqttControlData

MAGICHUE_NATION_DATA_ENDPOINT = "apixp/MeshData/loadNationDataNew/ZG?language=en"
MAGICHUE_USER_LOGIN_ENDPOINT = "apixp/User001/LoginForUser/ZG"
MAGICHUE_GET_MESH_ENDPOINT = "apixp/MeshData/GetMyMeshPlaceItems/ZG?userId="
MAGICHUE_GET_MESH_DEVICES_ENDPOINT = (
    "apixp/MeshData/GetMyMeshDeviceItems/ZG?placeUniID=&userId="
)
MAGICHUE_GET_MQTT_ENDPOINT: str = "apixp/Mqtt/getMasterControlData/ZG?placeUniID="

_LOGGER = logging.getLogger(__name__)


def get_country_server(country):
    """Get Country server for REST API."""
    for item in MAGICHUE_COUNTRY_SERVERS:
        if item["nationCode"] == country:
            return item["serverApi"]
    return MAGICHUE_COUNTRY_SERVERS[0]["serverApi"]  # return US server by default


class RestApiConnector:
    """REST API Connector."""

    def __init__(
        self, username: str, password: str, country: str, installation_id: str = None
    ) -> None:
        """Initialize the class."""

        self._username = username
        self._password = password
        self._country = country
        self._api_base_addr = (
            "http://" + get_country_server(country) + ":8081/MeshClouds/"
        )

        self._md5password = hashlib.md5(password.encode()).hexdigest()

        self._user_id = None
        self._auth_token = None
        self._device_secret = None
        self._installation_id = installation_id
        self.mqtt_info: list[MqttControlData] = None
        self.devices: list[Device]
        self._placeUniID = ""

        if not self._installation_id:
            self._installation_id = str(uuid.uuid4())

        # if country and country != "":
        #     MAGICHUE_COUNTRY_SERVER = get_country_server(country)
        #     MAGICHUE_CONNECTURL = "http://" + MAGICHUE_COUNTRY_SERVER
        #     _LOGGER.info(
        #         "Zengge server set to: " + country + " - " + MAGICHUE_COUNTRY_SERVER
        #     )

        # self.credentials()

    def generate_timestampcheckcode(self):
        """Generate a time stamp check code."""
        SECRET_KEY = "0FC154F9C01DFA9656524A0EFABC994F"
        timestamp = str(int(time.time() * 1000))
        value = ("ZG" + timestamp).encode()
        backend = default_backend()
        key = (SECRET_KEY).encode()
        encryptor = Cipher(algorithms.AES(key), modes.ECB(), backend).encryptor()
        padder = padding.PKCS7(algorithms.AES(key).block_size).padder()
        padded_data = padder.update(value) + padder.finalize()
        encrypted_text = encryptor.update(padded_data) + encryptor.finalize()
        checkcode = binascii.hexlify(encrypted_text).decode()
        return timestamp, checkcode

    async def connect(self) -> None:
        """Login to the server."""
        timestampcheckcode = self.generate_timestampcheckcode()
        timestamp = timestampcheckcode[0]
        checkcode = timestampcheckcode[1]
        payload = {
            "userID": self._username,
            "password": self._md5password,
            "appSys": "Android",
            "timestamp": timestamp,
            "appVer": "",
            "checkcode": checkcode,
        }

        headers = {
            "User-Agent": "HaoDeng/1.5.7(ANDROID,10,en-US)",
            "Accept-Language": "en-US",
            "Accept": "application/json",
            "token": "",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
        }

        uri = self._api_base_addr + MAGICHUE_USER_LOGIN_ENDPOINT
        print("URI: %s" % uri)

        async with aiohttp.ClientSession() as session:
            async with session.post(uri, headers=headers, json=payload) as response:
                if (
                    response.status != 200
                ):  # Previous code:   if response.status_code != 200:
                    raise Exception(
                        "Device retrieval for mesh failed - %s"
                        % response.json()["error"]
                    )
                else:
                    resultJSON = (await response.json())[
                        "result"
                    ]  # Previous Code:  responseJSON = response.json()['result'] #Previous Code:
                    print(resultJSON)
                    self._user_id = resultJSON["userId"]
                    self._auth_token = resultJSON["auth_token"]
                    self._device_secret = resultJSON["deviceSecret"]
        await self._credentials()

    async def _credentials(self):
        if self._auth_token is not None and self._user_id is not None:
            headers = {
                "User-Agent": "HaoDeng/1.5.7(ANDROID,10,en-US)",
                "Accept-Language": "en-US",
                "Accept": "application/json",
                "token": self._auth_token,
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip",
            }

            uri = (
                self._api_base_addr
                + MAGICHUE_GET_MESH_ENDPOINT
                + urllib.parse.quote_plus(self._user_id)
            )
            _LOGGER.info("URI: %s", uri)
            async with aiohttp.ClientSession() as session:
                async with session.get(uri, headers=headers) as response:
                    if (
                        response.status != 200
                    ):  # Previous code:   if response.status_code != 200:
                        raise Exception(
                            "Device retrieval for mesh failed - %s"
                            % response.json()["error"]
                        )
                    else:
                        resultJSON = (await response.json())[
                            "result"
                        ]  # Previous Code:  responseJSON = response.json()['result'] #Previous Code:
                        self._placeUniID = resultJSON[0]["placeUniID"]
        else:
            raise Exception(
                "No login session detected! - %s" % response.json()["error"]
            )

    async def get_mqtt_control_data(self) -> list[MqttControlData]:
        """Get MQTT Control Data."""
        if (self._auth_token) is None or self._user_id is None:
            raise Exception("No login session detected!")  # noqa: TRY002
        headers = {
            "User-Agent": "HaoDeng/1.5.7(ANDROID,10,en-US)",
            "Accept-Language": "en-US",
            "Accept": "application/json",
            "token": self._auth_token,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
        }
        print("Place Unit ID %s" % self._placeUniID)
        endpoint = self._api_base_addr + MAGICHUE_GET_MQTT_ENDPOINT.replace(
            "placeUniID=", "placeUniID=" + self._placeUniID
        )
        async with aiohttp.ClientSession() as session:  # noqa: SIM117
            async with session.get(endpoint, headers=headers, timeout=30) as response:
                if response.status != 200:
                    raise Exception(
                        "Device retrieval for mesh failed - {}".format(
                            response.json()["error"]
                        )
                    )  # noqa: TRY002
                responseJSON = (await response.json())["result"]
                myList = []
                for x in responseJSON:
                    mqtt_info = MqttControlData(x)
                    myList.append(mqtt_info)
                    # print(mqtt_info.deviceName, mqtt_info.productKey, mqtt_info.deviceType)
                self.mqtt_info = myList
                return myList

    async def devices(self) -> list[Device]:
        """Get a list of devices for the integration."""
        if self._auth_token is not None and self._user_id is not None:
            headers = {
                "User-Agent": "HaoDeng/1.5.7(ANDROID,10,en-US)",
                "Accept-Language": "en-US",
                "Accept": "application/json",
                "token": self._auth_token,
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip",
            }

            placeUniID = self._placeUniID
            endpointAddr = self._api_base_addr + MAGICHUE_GET_MESH_DEVICES_ENDPOINT
            endpointAddr = endpointAddr.replace(
                "placeUniID=", "placeUniID=" + placeUniID
            )
            endpointAddr = endpointAddr.replace(
                "userId=", "userId=" + urllib.parse.quote_plus(self._user_id)
            )

            # response = requests.get(MAGICHUE_CONNECTURL + MAGICHUE_GET_MESH_DEVICES_ENDPOINTNEW, headers=headers)
            async with aiohttp.ClientSession() as session:  # noqa: SIM117
                async with session.get(
                    endpointAddr,
                    headers=headers,
                ) as response:
                    if response.status != 200:
                        raise Exception(  # noqa: TRY002
                            "Device retrieval for mesh failed - {}".format(
                                response.json()["error"]
                            )
                        )
                    responseJSON = (await response.json())[
                        "result"
                    ]  # Previous Code:  responseJSON = response.json()['result'] #Previous Code:
                    myList = []
                    for x in responseJSON:
                        device = Device(x)
                        myList.append(device)
                    self.devices = myList
                    return myList
        else:
            raise Exception(  # noqa: TRY002
                "No login session detected! - {}".format(response.json()["error"])
            )
