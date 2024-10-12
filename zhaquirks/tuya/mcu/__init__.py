"""Tuya MCU communications."""

from collections.abc import Callable
import dataclasses
import datetime
from enum import Enum
import logging
from typing import Any, Optional, Union

from zigpy.quirks import _DEVICE_REGISTRY
from zigpy.quirks.registry import DeviceRegistry
from zigpy.quirks.v2 import QuirkBuilder, QuirksV2RegistryEntry
from zigpy.quirks.v2.homeassistant import EntityPlatform, EntityType
from zigpy.quirks.v2.homeassistant.binary_sensor import BinarySensorDeviceClass
from zigpy.quirks.v2.homeassistant.number import NumberDeviceClass
from zigpy.quirks.v2.homeassistant.sensor import SensorDeviceClass, SensorStateClass
import zigpy.types as t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.general import LevelControl, OnOff
from zigpy.zcl.clusters.measurement import SoilMoisture, TemperatureMeasurement
from zigpy.zcl.clusters.smartenergy import Metering

from zhaquirks import Bus, DoublingPowerConfigurationCluster

# add EnchantedDevice import for custom quirks backwards compatibility
from zhaquirks.tuya import (
    TUYA_CLUSTER_ID,
    TUYA_MCU_COMMAND,
    TUYA_MCU_VERSION_RSP,
    TUYA_SET_DATA,
    TUYA_SET_TIME,
    EnchantedDevice,  # noqa: F401
    NoManufacturerCluster,
    PowerConfiguration,
    PowerOnState,
    TuyaCommand,
    TuyaDatapointData,
    TuyaEnchantableCluster,
    TuyaLocalCluster,
    TuyaNewManufCluster,
    TuyaPowerConfigurationCluster2AAA,
    TuyaTimePayload,
)

# New manufacturer attributes
ATTR_MCU_VERSION = 0xEF00

# manufacturer commands
TUYA_MCU_CONNECTION_STATUS = 0x25

_LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class DPToAttributeMapping:
    """Container for datapoint to cluster attribute update mapping."""

    ep_attribute: str
    attribute_name: Union[str, tuple]
    converter: Optional[
        Callable[
            [
                Any,
            ],
            Any,
        ]
    ] = None
    dp_converter: Optional[
        Callable[
            [
                Any,
            ],
            Any,
        ]
    ] = None
    endpoint_id: Optional[int] = None


class TuyaClusterData(t.Struct):
    """Tuya cluster data."""

    endpoint_id: int
    cluster_name: str
    cluster_attr: str
    attr_value: int  # Maybe also others types?
    expect_reply: bool
    manufacturer: int


class MoesBacklight(t.enum8):
    """MOES switch backlight mode enum."""

    off = 0x00
    light_when_on = 0x01
    light_when_off = 0x02
    freeze = 0x03


class TuyaPowerConfigurationCluster(
    TuyaLocalCluster, DoublingPowerConfigurationCluster
):
    """PowerConfiguration cluster for battery-operated tuya devices reporting percentage."""


class TuyaAttributesCluster(TuyaLocalCluster):
    """Manufacturer specific cluster for Tuya converting attributes <-> commands."""

    def read_attributes(
        self, attributes, allow_cache=False, only_cache=False, manufacturer=None
    ):
        """Ignore remote reads as the "get_data" command doesn't seem to do anything."""

        self.debug("read_attributes --> attrs: %s", attributes)
        return super().read_attributes(
            attributes, allow_cache=True, only_cache=True, manufacturer=manufacturer
        )

    async def write_attributes(self, attributes, manufacturer=None):
        """Defer attributes writing to the set_data tuya command."""

        await super().write_attributes(attributes, manufacturer)

        records = self._write_attr_records(attributes)

        for record in records:
            self.debug("write_attributes --> record: %s", record)

            cluster_data = TuyaClusterData(
                endpoint_id=self.endpoint.endpoint_id,
                cluster_name=self.ep_attribute,
                cluster_attr=self.attributes[record.attrid].name,
                attr_value=record.value.value,
                expect_reply=False,
                manufacturer=manufacturer,
            )
            self.endpoint.device.command_bus.listener_event(
                TUYA_MCU_COMMAND,
                cluster_data,
            )

        return [[foundation.WriteAttributesStatusRecord(foundation.Status.SUCCESS)]]


class TuyaMCUCluster(TuyaAttributesCluster, TuyaNewManufCluster):
    """Manufacturer specific cluster for sending Tuya MCU commands."""

    set_time_offset = 1970  # MCU timestamp from 1/1/1970
    set_time_local_offset = None

    class MCUVersion(t.Struct):
        """Tuya MCU version response Zcl payload."""

        status: t.uint8_t
        tsn: t.uint8_t
        version_raw: t.uint8_t

        @property
        def version(self) -> str:
            """Format the raw version to X.Y.Z."""

            if self.version_raw:
                # MCU version is 1 byte length
                # is converted from HEX -> BIN -> XX.XX.XXXX -> DEC (x.y.z)
                # example: 0x98 -> 10011000 -> 10.01.1000 -> 2.1.8
                # https://developer.tuya.com/en/docs/iot-device-dev/firmware-version-description?id=K9zzuc5n2gff8#title-1-Zigbee%20firmware%20versions
                major = self.version_raw >> 6
                minor = (self.version_raw & 63) >> 4
                release = self.version_raw & 15

                return f"{major}.{minor}.{release}"

            return None

    class TuyaConnectionStatus(t.Struct):
        """Tuya connection status data."""

        tsn: t.uint8_t
        status: t.LVBytes

    attributes = TuyaNewManufCluster.attributes.copy()
    attributes.update(
        {
            # MCU version
            ATTR_MCU_VERSION: ("mcu_version", t.uint48_t, True),
        }
    )

    client_commands = TuyaNewManufCluster.client_commands.copy()
    client_commands.update(
        {
            TUYA_MCU_VERSION_RSP: foundation.ZCLCommandDef(
                "mcu_version_response",
                {"version": MCUVersion},
                True,
                is_manufacturer_specific=True,
            ),
        }
    )
    client_commands.update(
        {
            TUYA_MCU_CONNECTION_STATUS: foundation.ZCLCommandDef(
                "mcu_connection_status",
                {"payload": TuyaConnectionStatus},
                True,
                is_manufacturer_specific=True,
            ),
        }
    )

    server_commands = TuyaNewManufCluster.server_commands.copy()
    server_commands.update(
        {
            TUYA_MCU_CONNECTION_STATUS: foundation.ZCLCommandDef(
                "mcu_connection_status_rsp",
                {"payload": TuyaConnectionStatus},
                False,
                is_manufacturer_specific=True,
            ),
        }
    )

    def __init__(self, *args, **kwargs):
        """Init."""
        super().__init__(*args, **kwargs)
        # Cluster for endpoint: 1 (listen MCU commands)
        self.endpoint.device.command_bus = Bus()
        self.endpoint.device.command_bus.add_listener(self)

    def from_cluster_data(self, data: TuyaClusterData) -> Optional[TuyaCommand]:
        """Convert from cluster data to a tuya data payload."""

        dp_mapping = self.get_dp_mapping(data.endpoint_id, data.cluster_attr)
        self.debug("from_cluster_data: %s", dp_mapping)
        if len(dp_mapping) == 0:
            self.warning(
                "No cluster_dp found for %s, %s",
                data.endpoint_id,
                data.cluster_attr,
            )
            return []

        tuya_commands = []
        for dp, mapping in dp_mapping.items():
            cmd_payload = TuyaCommand()
            cmd_payload.status = 0
            cmd_payload.tsn = self.endpoint.device.application.get_sequence()

            val = data.attr_value
            if mapping.dp_converter:
                args = []
                if isinstance(mapping.attribute_name, tuple):
                    endpoint = self.endpoint
                    if mapping.endpoint_id:
                        endpoint = endpoint.device.endpoints[mapping.endpoint_id]
                    cluster = getattr(endpoint, mapping.ep_attribute)
                    for attr in mapping.attribute_name:
                        args.append(
                            val if attr == data.cluster_attr else cluster.get(attr)
                        )
                else:
                    args.append(val)
                val = mapping.dp_converter(*args)
            self.debug("value: %s", val)

            dpd = TuyaDatapointData(dp, val)
            self.debug("raw: %s", dpd.data.raw)
            cmd_payload.datapoints = [dpd]

            tuya_commands.append(cmd_payload)
        return tuya_commands

    def tuya_mcu_command(self, cluster_data: TuyaClusterData):
        """Tuya MCU command listener. Only manufacturer endpoint must listen to MCU commands."""

        self.debug(
            "tuya_mcu_command: cluster_data=%s",
            cluster_data,
        )

        tuya_commands = self.from_cluster_data(cluster_data)
        self.debug("tuya_commands: %s", tuya_commands)
        if len(tuya_commands) == 0:
            self.warning(
                "no MCU command for data %s",
                cluster_data,
            )
            return

        for tuya_command in tuya_commands:
            self.create_catching_task(
                self.command(
                    TUYA_SET_DATA,
                    tuya_command,
                    expect_reply=cluster_data.expect_reply,
                    manufacturer=cluster_data.manufacturer,
                )
            )

        endpoint = self.endpoint.device.endpoints[cluster_data.endpoint_id]
        cluster = getattr(endpoint, cluster_data.cluster_name)
        cluster.update_attribute(cluster_data.cluster_attr, cluster_data.attr_value)

    def get_dp_mapping(
        self, endpoint_id: int, attribute_name: str
    ) -> Optional[tuple[int, DPToAttributeMapping]]:
        """Search for the DP in dp_to_attribute."""

        result = {}
        for dp, dp_mapping in self.dp_to_attribute.items():
            if (
                attribute_name == dp_mapping.attribute_name
                or (
                    isinstance(dp_mapping.attribute_name, tuple)
                    and attribute_name in dp_mapping.attribute_name
                )
            ) and (
                (
                    dp_mapping.endpoint_id is None
                    and endpoint_id == self.endpoint.endpoint_id
                )
                or (endpoint_id == dp_mapping.endpoint_id)
            ):
                self.debug("get_dp_mapping --> found DP: %s", dp)
                result[dp] = dp_mapping
        return result

    def handle_mcu_version_response(self, payload: MCUVersion) -> foundation.Status:
        """Handle MCU version response."""

        self.debug("MCU version: %s", payload.version)
        self.update_attribute("mcu_version", payload.version)
        return foundation.Status.SUCCESS

    def handle_set_time_request(self, payload: t.uint16_t) -> foundation.Status:
        """Handle set_time requests (0x24)."""

        self.debug("handle_set_time_request payload: %s", payload)
        payload_rsp = TuyaTimePayload()

        utc_now = datetime.datetime.utcnow()  # noqa: DTZ003
        now = datetime.datetime.now()

        offset_time = datetime.datetime(self.set_time_offset, 1, 1)
        offset_time_local = datetime.datetime(
            self.set_time_local_offset or self.set_time_offset, 1, 1
        )

        utc_timestamp = int((utc_now - offset_time).total_seconds())
        local_timestamp = int((now - offset_time_local).total_seconds())

        payload_rsp.extend(utc_timestamp.to_bytes(4, "big", signed=False))
        payload_rsp.extend(local_timestamp.to_bytes(4, "big", signed=False))

        self.debug("handle_set_time_request response: %s", payload_rsp)
        self.create_catching_task(
            super().command(TUYA_SET_TIME, payload_rsp, expect_reply=False)
        )

        return foundation.Status.SUCCESS

    def handle_mcu_connection_status(
        self, payload: TuyaConnectionStatus
    ) -> foundation.Status:
        """Handle gateway connection status requests (0x25)."""

        payload_rsp = TuyaMCUCluster.TuyaConnectionStatus()
        payload_rsp.tsn = payload.tsn
        payload_rsp.status = b"\x01"  # 0x00 not connected to internet | 0x01 connected to internet | 0x02 time out

        self.create_catching_task(
            super().command(TUYA_MCU_CONNECTION_STATUS, payload_rsp, expect_reply=False)
        )

        return foundation.Status.SUCCESS


class TuyaOnOff(TuyaEnchantableCluster, OnOff, TuyaLocalCluster):
    """Tuya MCU OnOff cluster."""

    async def command(
        self,
        command_id: Union[foundation.GeneralCommand, int, t.uint8_t],
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        expect_reply: bool = True,
        tsn: Optional[Union[int, t.uint8_t]] = None,
    ):
        """Override the default Cluster command."""

        self.debug(
            "Sending Tuya Cluster Command... Cluster Command is %x, Arguments are %s",
            command_id,
            args,
        )

        # (off, on)
        if command_id in (0x0000, 0x0001):
            cluster_data = TuyaClusterData(
                endpoint_id=self.endpoint.endpoint_id,
                cluster_name=self.ep_attribute,
                cluster_attr="on_off",
                attr_value=bool(command_id),
                expect_reply=expect_reply,
                manufacturer=manufacturer,
            )
            self.endpoint.device.command_bus.listener_event(
                TUYA_MCU_COMMAND,
                cluster_data,
            )
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        self.warning("Unsupported command_id: %s", command_id)
        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(command_id=command_id, status=foundation.Status.UNSUP_CLUSTER_COMMAND)


class TuyaOnOffNM(NoManufacturerCluster, TuyaOnOff):
    """Tuya OnOff cluster with NoManufacturerID."""


class TuyaOnOffManufCluster(TuyaMCUCluster):
    """Tuya with On/Off data points."""

    dp_to_attribute: dict[int, DPToAttributeMapping] = {
        1: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
        ),
        2: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=2,
        ),
        3: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=3,
        ),
        4: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=4,
        ),
        5: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=5,
        ),
        6: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=6,
        ),
        0x65: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=7,
        ),
        0x66: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=8,
        ),
        0x67: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=9,
        ),
        0x68: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=10,
        ),
        0x69: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=11,
        ),
        0x6A: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=12,
        ),
        0x6B: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=13,
        ),
        0x6C: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=14,
        ),
        0x6D: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=15,
        ),
        0x6E: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=16,
        ),
    }

    data_point_handlers = {
        1: "_dp_2_attr_update",
        2: "_dp_2_attr_update",
        3: "_dp_2_attr_update",
        4: "_dp_2_attr_update",
        5: "_dp_2_attr_update",
        6: "_dp_2_attr_update",
        0x65: "_dp_2_attr_update",
        0x66: "_dp_2_attr_update",
        0x67: "_dp_2_attr_update",
        0x68: "_dp_2_attr_update",
        0x69: "_dp_2_attr_update",
        0x6A: "_dp_2_attr_update",
        0x6B: "_dp_2_attr_update",
        0x6C: "_dp_2_attr_update",
        0x6D: "_dp_2_attr_update",
        0x6E: "_dp_2_attr_update",
    }


class MoesSwitchManufCluster(TuyaOnOffManufCluster):
    """On/Off Tuya cluster with extra device attributes."""

    attributes = TuyaOnOffManufCluster.attributes.copy()
    attributes.update(
        {
            0x8001: ("backlight_mode", MoesBacklight),
            0x8002: ("power_on_state", PowerOnState),
        }
    )

    dp_to_attribute: dict[int, DPToAttributeMapping] = (
        TuyaOnOffManufCluster.dp_to_attribute.copy()
    )
    dp_to_attribute.update(
        {
            14: DPToAttributeMapping(
                TuyaMCUCluster.ep_attribute,
                "power_on_state",
                converter=lambda x: PowerOnState(x),
            )
        }
    )
    dp_to_attribute.update(
        {
            15: DPToAttributeMapping(
                TuyaMCUCluster.ep_attribute,
                "backlight_mode",
                converter=lambda x: MoesBacklight(x),
            ),
        }
    )

    data_point_handlers = TuyaOnOffManufCluster.data_point_handlers.copy()
    data_point_handlers.update({14: "_dp_2_attr_update"})
    data_point_handlers.update({15: "_dp_2_attr_update"})


class TuyaLevelControl(LevelControl, TuyaLocalCluster):
    """Tuya MCU Level cluster for dimmable device."""

    async def command(
        self,
        command_id: Union[foundation.GeneralCommand, int, t.uint8_t],
        *args,
        manufacturer: Optional[Union[int, t.uint16_t]] = None,
        expect_reply: bool = True,
        tsn: Optional[Union[int, t.uint8_t]] = None,
        **kwargs: Any,
    ):
        """Override the default Cluster command."""
        self.debug(
            "Sending Tuya Cluster Command. Cluster Command is %x, Arguments are %s, %s",
            command_id,
            args,
            kwargs,
        )

        # getting the level value
        if kwargs and "level" in kwargs:
            level = kwargs["level"]
        elif args:
            level = args[0]
        else:
            level = 0

        on_off = bool(level)  # maybe must be compared against `minimum_level` attribute

        # (move_to_level_with_on_off --> send the on_off command first, but only if needed)
        if command_id == 0x0004 and self.endpoint.on_off.get("on_off") != on_off:
            cluster_data = TuyaClusterData(
                endpoint_id=self.endpoint.endpoint_id,
                cluster_name="on_off",
                cluster_attr="on_off",
                attr_value=on_off,
                expect_reply=expect_reply,
                manufacturer=manufacturer,
            )
            self.endpoint.device.command_bus.listener_event(
                TUYA_MCU_COMMAND,
                cluster_data,
            )

        # level 0 --> switched off
        if command_id == 0x0004 and not on_off:
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        # (move_to_level, move, move_to_level_with_on_off)
        if command_id in (0x0000, 0x0001, 0x0004):
            cluster_data = TuyaClusterData(
                endpoint_id=self.endpoint.endpoint_id,
                cluster_name=self.ep_attribute,
                cluster_attr="current_level",
                attr_value=level,
                expect_reply=expect_reply,
                manufacturer=manufacturer,
            )
            self.endpoint.device.command_bus.listener_event(
                TUYA_MCU_COMMAND,
                cluster_data,
            )
            return foundation.GENERAL_COMMANDS[
                foundation.GeneralCommand.Default_Response
            ].schema(command_id=command_id, status=foundation.Status.SUCCESS)

        self.warning("Unsupported command_id: %s", command_id)
        return foundation.GENERAL_COMMANDS[
            foundation.GeneralCommand.Default_Response
        ].schema(command_id=command_id, status=foundation.Status.UNSUP_CLUSTER_COMMAND)


class TuyaInWallLevelControl(TuyaAttributesCluster, TuyaLevelControl):
    """Tuya Level cluster for inwall dimmable device."""

    # Not sure if these are 'inwall' specific attributes or common to dimmers
    attributes = TuyaLevelControl.attributes.copy()
    attributes.update(
        {
            0xEF01: ("minimum_level", t.uint32_t, True),
            0xEF02: ("bulb_type", t.enum8, True),
        }
    )


class TuyaLevelControlManufCluster(TuyaMCUCluster):
    """Tuya with Level Control data points."""

    dp_to_attribute: dict[int, DPToAttributeMapping] = {
        1: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
        ),
        2: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "current_level",
            converter=lambda x: (x * 255) // 1000,
            dp_converter=lambda x: (x * 1000) // 255,
        ),
        3: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "minimum_level",
            converter=lambda x: (x * 255) // 1000,
            dp_converter=lambda x: (x * 1000) // 255,
        ),
        4: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "bulb_type",
        ),
        7: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=2,
        ),
        8: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "current_level",
            converter=lambda x: (x * 255) // 1000,
            dp_converter=lambda x: (x * 1000) // 255,
            endpoint_id=2,
        ),
        9: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "minimum_level",
            converter=lambda x: (x * 255) // 1000,
            dp_converter=lambda x: (x * 1000) // 255,
            endpoint_id=2,
        ),
        10: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "bulb_type",
            endpoint_id=2,
        ),
        15: DPToAttributeMapping(
            TuyaOnOff.ep_attribute,
            "on_off",
            endpoint_id=3,
        ),
        16: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "current_level",
            converter=lambda x: (x * 255) // 1000,
            dp_converter=lambda x: (x * 1000) // 255,
            endpoint_id=3,
        ),
        17: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "minimum_level",
            converter=lambda x: (x * 255) // 1000,
            dp_converter=lambda x: (x * 1000) // 255,
            endpoint_id=3,
        ),
        18: DPToAttributeMapping(
            TuyaLevelControl.ep_attribute,
            "bulb_type",
            endpoint_id=3,
        ),
    }

    data_point_handlers = {
        1: "_dp_2_attr_update",
        2: "_dp_2_attr_update",
        3: "_dp_2_attr_update",
        4: "_dp_2_attr_update",
        7: "_dp_2_attr_update",
        8: "_dp_2_attr_update",
        9: "_dp_2_attr_update",
        10: "_dp_2_attr_update",
        15: "_dp_2_attr_update",
        16: "_dp_2_attr_update",
        17: "_dp_2_attr_update",
        18: "_dp_2_attr_update",
    }


class TuyaTemperatureMeasurement(TemperatureMeasurement, TuyaLocalCluster):
    """Tuya local TemperatureMeasurement cluster."""


class TuyaSoilMoisture(SoilMoisture, TuyaLocalCluster):
    """Tuya local SoilMoisture cluster with a device RH_MULTIPLIER factor if required."""


class TuyaValveWaterConsumed(Metering, TuyaLocalCluster):
    """Tuya Valve Water consumed cluster."""

    VOLUME_LITERS = 0x0007
    WATER_METERING = 0x02

    """Setting unit of measurement."""
    _CONSTANT_ATTRIBUTES = {
        0x0300: VOLUME_LITERS,
        0x0306: WATER_METERING,
    }

    def __init__(self, *args, **kwargs):
        """Init a TuyaValveWaterConsumed cluster."""
        super().__init__(*args, **kwargs)
        self.add_unsupported_attribute(Metering.AttributeDefs.instantaneous_demand.id)


class TuyaQuirkBuilder(QuirkBuilder):
    """Tuya QuirkBuilder."""

    def __init__(
        self, manufacturer: str, model: str, registry: DeviceRegistry = _DEVICE_REGISTRY
    ) -> None:
        """Init the TuyaQuirkBuilder."""
        self.tuya_data_point_handlers: dict[int, str] = {}
        self.tuya_dp_to_attribute: dict[int, DPToAttributeMapping] = {}
        self.new_attributes: dict[int, foundation.ZCLAttributeDef] = {}
        super().__init__(manufacturer, model, registry)

    def battery(
        self,
        dp_id: int,
        power_cfg: PowerConfiguration = TuyaPowerConfigurationCluster2AAA,
        scale: float = 2,
    ) -> QuirkBuilder:
        """Add a Tuya Battery Power Configuration."""
        self.tuya_dp(
            dp_id,
            power_cfg.ep_attribute,
            "battery_percentage_remaining",
            converter=lambda x: x * scale,
        )
        self.adds(power_cfg)
        return self

    def metering(
        self,
        dp_id: int,
        metering_cfg: TuyaLocalCluster = TuyaValveWaterConsumed,
    ) -> QuirkBuilder:
        """Add a Tuya Metering Configuration."""
        self.tuya_dp(
            dp_id,
            metering_cfg.ep_attribute,
            "current_summ_delivered",
        )
        self.adds(metering_cfg)

    def onoff(
        self,
        dp_id: int,
        onoff_cfg: TuyaLocalCluster = TuyaOnOffNM,
    ) -> QuirkBuilder:
        """Add a Tuya OnOff Configuration."""
        self.tuya_dp(
            dp_id,
            onoff_cfg.ep_attribute,
            "on_off",
        )
        self.adds(onoff_cfg)

    def soil_moisture(
        self,
        dp_id: int,
        soil_cfg: TuyaLocalCluster = TuyaSoilMoisture,
        scale: float = 100,
    ) -> QuirkBuilder:
        """Add a Tuya Soil Moisture Configuration."""
        self.tuya_dp(
            dp_id,
            soil_cfg.ep_attribute,
            "measured_value",
            converter=lambda x: x * scale,
        )
        self.adds(soil_cfg)
        return self

    def temperature(
        self,
        dp_id: int,
        temp_cfg: TuyaLocalCluster = TuyaTemperatureMeasurement,
        scale: float = 100,
    ) -> QuirkBuilder:
        """Add a Tuya Soil Moisture Configuration."""
        self.tuya_dp(
            dp_id,
            temp_cfg.ep_attribute,
            "measured_value",
            converter=lambda x: x * scale,
        )
        self.adds(temp_cfg)
        return self

    def tuya_attribute(
        self,
        dp_id: int,
        attribute_name: str,
        type: type = t.uint16_t,
        access: foundation.ZCLAttributeAccess = foundation.ZCLAttributeAccess.NONE,
        is_manufacturer_specific=True,
    ) -> QuirkBuilder:
        """Add an attribute to AttributeDefs."""
        attr_id: int = int.from_bytes([0xEF, dp_id])
        self.new_attributes.update(
            {
                attr_id: foundation.ZCLAttributeDef(
                    id=attr_id,
                    type=type,
                    access=access,
                    is_manufacturer_specific=is_manufacturer_specific,
                    name=attribute_name,
                )
            }
        )

        return self

    def tuya_dp(
        self,
        dp_id: int,
        ep_attribute: str,
        attribute_name: str,
        converter: Optional[Callable[[Any,], Any,]] = None,
        dp_converter: Optional[Callable[[Any,], Any,]] = None,
        endpoint_id: Optional[int] = None,
        dp_handler: str = "_dp_2_attr_update",
    ) -> QuirkBuilder:  # fmt: skip
        """Add Tuya DP Converter."""
        self.tuya_dp_to_attribute.update(
            {
                dp_id: DPToAttributeMapping(
                    ep_attribute,
                    attribute_name,
                    converter=converter,
                    dp_converter=dp_converter,
                    endpoint_id=endpoint_id,
                )
            }
        )
        self.tuya_data_point_handlers.update({dp_id: dp_handler})
        return self

    def tuya_dp_attribute(
        self,
        dp_id: int,
        attribute_name: str,
        ep_attribute: str = TuyaMCUCluster.ep_attribute,
        converter: Optional[Callable[[Any,], Any,]] = None,
        dp_converter: Optional[Callable[[Any,], Any,]] = None,
        endpoint_id: Optional[int] = None,
        dp_handler: str = "_dp_2_attr_update",
        type: type = t.uint16_t,
        access: foundation.ZCLAttributeAccess = foundation.ZCLAttributeAccess.NONE,
        is_manufacturer_specific=True,
    ) -> QuirkBuilder:  # fmt: skip
        """Add an Tuya DataPoint and corresponding AttributeDef."""
        self.tuya_attribute(
            dp_id=dp_id,
            attribute_name=attribute_name,
            type=type,
            access=access,
            is_manufacturer_specific=is_manufacturer_specific,
        )
        self.tuya_dp(
            dp_id=dp_id,
            ep_attribute=ep_attribute,
            attribute_name=attribute_name,
            dp_converter=dp_converter,
            converter=converter,
            endpoint_id=endpoint_id,
            dp_handler=dp_handler,
        )
        return self

    def tuya_switch(
        self,
        dp_id: int,
        attribute_name: str = "on_off",
        endpoint_id: int = 1,
        force_inverted: bool = False,
        invert_attribute_name: str | None = None,
        off_value: int = 0,
        on_value: int = 1,
        entity_platform=EntityPlatform.SWITCH,
        entity_type: EntityType = EntityType.CONFIG,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing SwitchMetadata and return self.

        This method allows exposing a switch entity in Home Assistant.
        """
        self.tuya_dp_attribute(
            dp_id=dp_id,
            attribute_name=attribute_name,
            type=t.Bool,
            access=foundation.ZCLAttributeAccess.Read
            | foundation.ZCLAttributeAccess.Write,
        )
        self.switch(
            attribute_name=attribute_name,
            cluster_id=TUYA_CLUSTER_ID,
            endpoint_id=endpoint_id,
            force_inverted=force_inverted,
            invert_attribute_name=invert_attribute_name,
            off_value=off_value,
            on_value=on_value,
            entity_platform=entity_platform,
            entity_type=entity_type,
            initially_disabled=initially_disabled,
            attribute_initialized_from_cache=attribute_initialized_from_cache,
            translation_key=translation_key,
            fallback_name=fallback_name,
        )
        return self

    def tuya_enum(
        self,
        dp_id: int,
        attribute_name: str,
        enum_class: type[Enum],
        access: foundation.ZCLAttributeAccess = foundation.ZCLAttributeAccess.Read
        | foundation.ZCLAttributeAccess.Write,
        endpoint_id: int = 1,
        entity_type: EntityType = EntityType.CONFIG,
        entity_platform: EntityPlatform = EntityPlatform.SELECT,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing ZCLEnumMetadata and return self.

        This method allows exposing an enum based entity in Home Assistant.
        """
        self.tuya_dp_attribute(
            dp_id=dp_id,
            attribute_name=attribute_name,
            type=enum_class,
            access=access,
        )
        self.enum(
            attribute_name=attribute_name,
            enum_class=enum_class,
            cluster_id=TUYA_CLUSTER_ID,
            endpoint_id=endpoint_id,
            entity_type=entity_type,
            entity_platform=entity_platform,
            initially_disabled=initially_disabled,
            attribute_initialized_from_cache=attribute_initialized_from_cache,
            translation_key=translation_key,
            fallback_name=fallback_name,
        )

        return self

    def tuya_number(
        self,
        dp_id: int,
        type: type,
        attribute_name: str,
        access: foundation.ZCLAttributeAccess = foundation.ZCLAttributeAccess.Read
        | foundation.ZCLAttributeAccess.Write,
        endpoint_id: int = 1,
        min_value: float | None = None,
        max_value: float | None = None,
        step: float | None = None,
        unit: str | None = None,
        mode: str | None = None,
        multiplier: float | None = None,
        device_class: NumberDeviceClass | None = None,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing NumberMetadata and return self.

        This method allows exposing a number entity in Home Assistant.
        """
        self.tuya_dp_attribute(
            dp_id=dp_id,
            attribute_name=attribute_name,
            type=type,
            access=access,
        )
        self.number(
            attribute_name=attribute_name,
            cluster_id=TUYA_CLUSTER_ID,
            endpoint_id=endpoint_id,
            min_value=min_value,
            max_value=max_value,
            step=step,
            unit=unit,
            mode=mode,
            multiplier=multiplier,
            device_class=device_class,
            initially_disabled=initially_disabled,
            attribute_initialized_from_cache=attribute_initialized_from_cache,
            translation_key=translation_key,
            fallback_name=fallback_name,
        )

        return self

    def tuya_binary_sensor(
        self,
        dp_id: int,
        attribute_name: str,
        endpoint_id: int = 1,
        device_class: BinarySensorDeviceClass | None = None,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing BinarySensorMetadata and return self.

        This method allows exposing a binary sensor entity in Home Assistant.
        """
        self.tuya_dp_attribute(
            dp_id=dp_id,
            attribute_name=attribute_name,
            type=t.Bool,
            access=foundation.ZCLAttributeAccess.Read
            | foundation.ZCLAttributeAccess.Report,
        )
        self.binary_sensor(
            attribute_name=attribute_name,
            cluster_id=TUYA_CLUSTER_ID,
            endpoint_id=endpoint_id,
            device_class=device_class,
            initially_disabled=initially_disabled,
            attribute_initialized_from_cache=attribute_initialized_from_cache,
            translation_key=translation_key,
            fallback_name=fallback_name,
        )

        return self

    def tuya_sensor(
        self,
        dp_id: int,
        attribute_name: str,
        type: type,
        endpoint_id: int = 1,
        divisor: int = 1,
        multiplier: int = 1,
        entity_type: EntityType = EntityType.STANDARD,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
        initially_disabled: bool = False,
        attribute_initialized_from_cache: bool = True,
        translation_key: str | None = None,
        fallback_name: str | None = None,
    ) -> QuirkBuilder:
        """Add an EntityMetadata containing ZCLSensorMetadata and return self.

        This method allows exposing a sensor entity in Home Assistant.
        """

        self.tuya_dp_attribute(
            dp_id=dp_id,
            attribute_name=attribute_name,
            type=type,
            access=foundation.ZCLAttributeAccess.Read
            | foundation.ZCLAttributeAccess.Report,
        )
        self.sensor(
            attribute_name=attribute_name,
            cluster_id=TUYA_CLUSTER_ID,
            endpoint_id=endpoint_id,
            divisor=divisor,
            multiplier=multiplier,
            entity_type=entity_type,
            device_class=device_class,
            state_class=state_class,
            unit=unit,
            initially_disabled=initially_disabled,
            attribute_initialized_from_cache=attribute_initialized_from_cache,
            translation_key=translation_key,
            fallback_name=fallback_name,
        )

        return self

    def add_to_registry(self) -> QuirksV2RegistryEntry:
        """Build the quirks v2 registry entry."""

        attr_dict: dict[int, foundation.ZCLAttributeDef] = self.new_attributes

        class TuyaReplacementCluster(TuyaMCUCluster):
            """Replacement Tuya Cluster."""

            data_point_handlers: dict[int, str]
            dp_to_attribute: dict[int, DPToAttributeMapping]
            attributes = TuyaMCUCluster.attributes.copy()
            attributes.update(attr_dict)

            async def write_attributes(self, attributes, manufacturer=None):
                """Overwrite to force manufacturer code."""

                return await super().write_attributes(
                    attributes, manufacturer=foundation.ZCLHeader.NO_MANUFACTURER_ID
                )

        TuyaReplacementCluster.data_point_handlers = (
            TuyaMCUCluster.data_point_handlers.copy()
        )
        TuyaReplacementCluster.data_point_handlers.update(self.tuya_data_point_handlers)
        TuyaReplacementCluster.dp_to_attribute = self.tuya_dp_to_attribute

        self.replaces(TuyaReplacementCluster)
        return super().add_to_registry()
