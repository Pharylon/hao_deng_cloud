from .const import DOMAIN


class MqttControlData:
    deviceName: str
    devicePwd: str
    productKey: str
    deviceType: str
    macAddress: str
    loadDeviceUrl: str

    def __init__(self, json):
        self.deviceName = json["deviceName"]
        self.devicePwd = json["devicePwd"]
        self.productKey = json["productKey"]
        self.deviceType = json["deviceType"]
        self.macAddress = json["macAddress"]
        self.loadDeviceUrl = json["loadDeviceUrl"]


class MqttLightPayload:
    dstAdr: str
    opCode: str
    data: str

    def __init__(self, dstAdr: str, opCode: str, data: str):
        self.dstAdr = dstAdr
        self.opCode = opCode
        self.data = data


class Device:
    uniID: str
    userID: str
    placeUniID: str
    macAddress: str
    displayName: str
    meshAddress: int
    deviceType: int
    controlType: int
    wiringType: int
    groups: list[int]

    def __init__(self, json) -> None:
        """Initialize."""
        self.uniID = json["uniID"]
        self.userID = json["userID"]
        self.placeUniID = json["placeUniID"]
        self.macAddress = json["macAddress"]
        self.displayName = json["displayName"]
        self.meshAddress = json["meshAddress"]
        self.deviceType = json["deviceType"]
        self.controlType = json["controlType"]
        self.wiringType = json["wiringType"]
        groups = [
            json["group1ID"],
            json["group2ID"],
            json["group3ID"],
            json["group4ID"],
            json["group5ID"],
            json["group6ID"],
            json["group7ID"],
            json["group8ID"],
        ]
        self.groups = [x for x in groups if x > 0]


class ExternalColorData:
    isRgb: bool
    rgb: list[int]
    colorTempBrightness: list[int]

    def __init__(self, isRgb: bool, rgb: list[int], colorTempBrightness: list[int]):
        self.isRgb = isRgb
        self.rgb = rgb
        self.colorTempBrightness = colorTempBrightness
