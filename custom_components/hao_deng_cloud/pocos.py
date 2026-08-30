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
        self.uniID = str(json["uniID"])
        self.userID = json["userID"]
        self.placeUniID = json["placeUniID"]
        self.macAddress = json["macAddress"]
        self.displayName = json["displayName"]
        self.meshAddress = int(json["meshAddress"])
        self.deviceType = int(json["deviceType"])
        self.controlType = int(json["controlType"])
        self.wiringType = int(json["wiringType"])
        raw_groups = [
            json.get("group1ID"),
            json.get("group2ID"),
            json.get("group3ID"),
            json.get("group4ID"),
            json.get("group5ID"),
            json.get("group6ID"),
            json.get("group7ID"),
            json.get("group8ID"),
        ]
        parsed_groups = []
        for g in raw_groups:
            if g is not None:
                try:
                    val = int(g)
                    if val > 0:
                        parsed_groups.append(val)
                except (ValueError, TypeError):
                    pass
        self.groups = parsed_groups


class Group:
    uniID: str
    CDPID: str
    userID: str
    placeUniID: str
    groupID: int
    groupName: str
    lastUpdateDate: str

    def __init__(self, json) -> None:
        """Initialize."""
        self.uniID = str(json["uniID"])
        self.CDPID = json.get("CDPID")
        self.userID = json["userID"]
        self.placeUniID = json["placeUniID"]
        try:
            self.groupID = int(json["groupID"]) if json.get("groupID") is not None else 0
        except (ValueError, TypeError):
            self.groupID = 0
        self.groupName = json["groupName"]
        self.lastUpdateDate = json.get("lastUpdateDate")


class ExternalColorData:
    isHsv: bool
    hsv: list[int]
    colorTempBrightness: list[int]

    def __init__(
        self,
        isHsl: bool,
        hsv: list[int],
        colorTempBrightness: list[int],
        isAvailable: bool,
    ) -> None:
        self.isAvailable = isAvailable
        self.isHsv = isHsl
        self.hsv = hsv
        self.colorTempBrightness = colorTempBrightness
