"""Tuya TRV."""

from datetime import UTC, datetime
import math

from zigpy.quirks.v2.homeassistant import UnitOfTemperature, UnitOfTime
from zigpy.types import t
from zigpy.zcl import foundation
from zigpy.zcl.clusters.hvac import Thermostat

from zhaquirks.tuya.builder import TuyaQuirkBuilder
from zhaquirks.tuya.mcu import TuyaAttributesCluster


class TuyaThermostat(Thermostat, TuyaAttributesCluster):
    """Tuya local thermostat cluster."""

    manufacturer_id_override: t.uint16_t = foundation.ZCLHeader.NO_MANUFACTURER_ID

    _CONSTANT_ATTRIBUTES = {
        Thermostat.AttributeDefs.ctrl_sequence_of_oper.id: Thermostat.ControlSequenceOfOperation.Heating_Only
    }

    def __init__(self, *args, **kwargs):
        """Init a TuyaThermostat cluster."""

        super().__init__(*args, **kwargs)
        self.add_unsupported_attribute(
            Thermostat.AttributeDefs.setpoint_change_source.id
        )
        self.add_unsupported_attribute(
            Thermostat.AttributeDefs.setpoint_change_source_timestamp.id
        )
        self.add_unsupported_attribute(Thermostat.AttributeDefs.pi_heating_demand.id)


class PresetMode(t.enum8):
    """Tuya PresetMode enum."""

    Manual = 0x00
    Home = 0x01
    Holiday = 0x02  # _TZE200_mudxchsu only
    HolidayAlt = 0x03  # Others


class WorkingDay(t.enum8):
    """Tuya Working Day enum."""

    MonSun = 0x00
    MonToFriSatSun = 0x01
    Separate = 0x02


class TuyaLocalTempCal:
    """Tuya local temp calibration converter.

    See: https://github.com/Koenkk/zigbee-herdsman-converters/blob/786c59b5d7d0b9f1b1022b8919455a205d20b9d5/src/lib/tuya.ts#L844
    """

    def from_device(self, sp: int) -> int:
        """Convert from device."""

        if sp > 55:
            return (sp - 0x100000000) / 10
        return sp / 10

    def to_device(self, sp: int) -> int:
        """Convert to device."""

        if sp > 0:
            return sp * 10
        if sp < 0:
            return sp * 10 + 0x100000000
        return sp


class HolidayDatetime:
    """Tuya local holiday datetime converter.

    See: https://github.com/Koenkk/zigbee-herdsman-converters/blob/8f6e15f1c5f6464766982e13281cb0d3c53ae89d/src/lib/tuya.ts#L873
    """

    start_time: datetime
    stop_time: datetime
    date_fmt: str = "%Y%m%d%H%M"

    def from_device(self, sp: str):
        """Convert from device."""
        self.start_time = datetime.strptime(sp[:12], self.date_fmt).replace(tzinfo=UTC)
        self.stop_time = datetime.strptime(sp[12:], self.date_fmt).replace(tzinfo=UTC)
        return self

    def to_device(self) -> str:
        """Convert to device."""
        return f"{self.start_time.strftime(self.date_fmt)}{self.stop_time.strftime(self.date_fmt)}"

    def from_string(self, sp: str):
        """Convert from string."""

        self.start_time = datetime.fromisoformat(sp.split("|")[0].strip())
        self.stop_time = datetime.fromisoformat(sp.split("|")[1].strip())
        return self

    def to_string(self) -> str:
        """Convert to string."""

        return f"{self.start_time.isoformat()} | {self.stop_time.isoformat()}"


class ThermostatScheduleDaySingleDP:
    """Tuya local thermostat schedule single dp.

    See: https://github.com/Koenkk/zigbee-herdsman-converters/blob/8f6e15f1c5f6464766982e13281cb0d3c53ae89d/src/lib/tuya.ts#L899

    todo: implement to_device.
    """

    def from_device(self, v: list[int]) -> str:
        """Convert schedule to string."""
        MAX_PERIODS_IN_DAY: int = 10
        PERIOD_SIZE: int = 3
        schedule: list = []

        for i in range(MAX_PERIODS_IN_DAY):
            time: int = v[i * PERIOD_SIZE]
            total_min = time * 10
            hours = total_min / 60
            r_hours = math.floor(hours)
            minutes = (hours - r_hours) * 60
            r_min = round(minutes)
            str_hours = r_hours.rjust(2, "0")
            str_min = r_min.rjust(2, "0")
            temp_hex_array = [v[i * PERIOD_SIZE + 1], v[i * PERIOD_SIZE + 2]]
            temp_raw = int.from_bytes(temp_hex_array, byteorder="big")
            temp = temp_raw / 10
            schedule.append(f"{str_hours}:{str_min}/{temp}")
            if r_hours == 24:
                break

        return " ".join(schedule)


(
    TuyaQuirkBuilder(
        "_TZE200_sur6q7ko", "TS0601"
    )  # model: 3012732, vendor: LSC Smart Connect
    .applies_to("_TZE200_hue3yfsn", "TS0601")  # model: TV02-Zigbee, vendor: Tuya
    .applies_to("_TZE200_e9ba97vf", "TS0601")  # model: TV01-ZB, vendor: Moes
    .applies_to(
        "_TZE200_husqqvux", "TS0601"
    )  # model: TSL-TRV-TV01ZG, vendor: Tesla Smart
    .applies_to(
        "_TZE200_lnbfnyxd", "TS0601"
    )  # model: TSL-TRV-TV01ZG, vendor: Tesla Smart
    .applies_to(
        "_TZE200_fsow0qsk", "TS0601"
    )  # model: TSL-TRV-TV05ZG, vendor: Tesla Smart
    .applies_to("_TZE200_lllliz3p", "TS0601")  # model: TV02-Zigbee, vendor: Tuya
    .applies_to("_TZE200_mudxchsu", "TS0601")  # model: TV05-ZG curve, vendor: Tuya
    .applies_to("_TZE200_7yoranx2", "TS0601")  # model: TV01-ZB, vendor: Moes
    .applies_to("_TZE200_kds0pmmv", "TS0601")
    .applies_to("_TZE200_py4cm3he", "TS0601")  # model: TV06-Zigbee, vendor: Tuya
    .applies_to("_TZE200_wsbfwodu", "TS0601")  # model: HA-08 THERMO, vendor: AlecoAir
    .applies_to("_TZE200_kly8gjlz", "TS0601")  # EARU TV05-ZG (Not in z2m)
    .tuya_enum(
        dp_id=2,
        attribute_name="preset_mode",
        enum_class=PresetMode,
        translation_key="preset_mode",
        fallback_name="Preset mode",
    )
    .tuya_binary_sensor(
        dp_id=8,
        attribute_name="window_detection",
        translation_key="window_detection",
        fallback_name="Open window detection",
    )
    .tuya_switch(
        dp_id=10,
        attribute_name="frost_protection",
        translation_key="frost_protection",
        fallback_name="Frost protection",
    )
    # z2m has some strange logic here
    # https://github.com/Koenkk/zigbee-herdsman-converters/blob/786c59b5d7d0b9f1b1022b8919455a205d20b9d5/src/lib/tuya.ts#L1424
    .tuya_dp(
        dp_id=16,
        ep_attribute=TuyaThermostat.ep_attribute,
        attribute_name=TuyaThermostat.AttributeDefs.occupied_heating_setpoint.name,
        converter=lambda x: x * 10,
        dp_converter=lambda x: x // 10,
    )
    .tuya_dp(
        dp_id=24,
        ep_attribute=TuyaThermostat.ep_attribute,
        attribute_name=TuyaThermostat.AttributeDefs.local_temperature.name,
        converter=lambda x: x * 10,
    )
    .tuya_dp(
        dp_id=27,
        ep_attribute=TuyaThermostat.ep_attribute,
        attribute_name=Thermostat.AttributeDefs.local_temperature_calibration.name,
        converter=lambda x: TuyaLocalTempCal.from_device(x),
        dp_converter=lambda x: TuyaLocalTempCal.to_device(x),
    )
    .tuya_enum(
        dp_id=31,
        attribute_name="working_day",
        enum_class=WorkingDay,
        translation_key="working_day",
        fallback_name="Working day",
    )
    .tuya_number(
        dp_id=32,
        attribute_name="holiday_temperature",
        type=t.uint16_t,
        unit=UnitOfTemperature.CELSIUS,
        min_value=5,
        max_value=30,
        step=1,
        multiplier=0.1,
        translation_key="holiday_temperature",
        fallback_name="Holiday temperature",
    )
    .tuya_binary_sensor(
        dp_id=35,
        attribute_name="battery_low",
        invert=True,
        translation_key="battery_low",
        fallback_name="Battery low",
    )
    .tuya_switch(
        dp_id=40,
        attribute_name="child_lock",
        translation_key="child_lock",
        fallback_name="Child lock",
    )
    .tuya_dp_attribute(
        dp_id=45,
        attribute_name="error_status",
        type=t.CharacterString,  # Not 100% on this
    )
    .tuya_dp_attribute(
        dp_id=46,
        attribute_name="holiday_start_stop",
        converter=lambda x: HolidayDatetime().from_device(x).to_string(),
        dp_converter=lambda x: HolidayDatetime().from_string(x).to_device(),
        type=t.CharacterString,
    )
    .tuya_number(
        dp_id=101,
        attribute_name="boost_timeset_countdown",
        type=t.uint16_t,
        unit=UnitOfTime.SECONDS,
        min_value=0,
        max_value=465,
        step=1,
        translation_key="boost_timeset_countdown",
        fallback_name="Boost timeset countdown",
    )
    .tuya_number(
        dp_id=102,
        attribute_name="open_window_temperature",
        type=t.uint16_t,
        unit=UnitOfTemperature.CELSIUS,
        min_value=5,
        max_value=30,
        step=1,
        multiplier=0.1,
        translation_key="open_window_temperature",
        fallback_name="Open window temperature",
    )
    .tuya_number(
        dp_id=104,
        attribute_name="comfort_temperature",
        type=t.uint16_t,
        unit=UnitOfTemperature.CELSIUS,
        min_value=5,
        max_value=30,
        step=1,
        multiplier=0.1,
        translation_key="comfort_temperature",
        fallback_name="Comfort temperature",
    )
    .tuya_number(
        dp_id=105,
        attribute_name="eco_temperature",
        type=t.uint16_t,
        unit=UnitOfTemperature.CELSIUS,
        min_value=5,
        max_value=30,
        step=1,
        multiplier=0.1,
        translation_key="eco_temperature",
        fallback_name="Eco temperature",
    )
    .tuya_dp_attribute(
        dp_id=106,
        attribute_name="schedule",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp(
        dp_id=107,
        ep_attribute=TuyaThermostat.ep_attribute,
        attribute_name=TuyaThermostat.AttributeDefs.system_mode.name,
        converter=lambda x: Thermostat.SystemMode.Off
        if not x
        else Thermostat.SystemMode.Heat,
        dp_converter=lambda x: x != Thermostat.SystemMode.Off,
    )
    .tuya_binary_sensor(
        dp_id=115,
        attribute_name="online",
        translation_key="online",
        fallback_name="Online",
    )
    .tuya_dp_attribute(
        dp_id=108,
        attribute_name="schedule_monday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp_attribute(
        dp_id=112,
        attribute_name="schedule_tuesday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp_attribute(
        dp_id=109,
        attribute_name="schedule_wednesday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp_attribute(
        dp_id=113,
        attribute_name="schedule_thursday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp_attribute(
        dp_id=110,
        attribute_name="schedule_friday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp_attribute(
        dp_id=114,
        attribute_name="schedule_saturday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .tuya_dp_attribute(
        dp_id=111,
        attribute_name="schedule_sunday",
        converter=lambda x: ThermostatScheduleDaySingleDP.from_device(x),
        type=t.LVList,
    )  # To device not implemented, see z2m converter if desired
    .adds(TuyaThermostat)
    .skip_configuration()
    .add_to_registry()
)
