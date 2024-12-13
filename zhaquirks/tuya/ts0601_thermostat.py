"""Tuya TS0601 Thermostat."""

from zigpy.quirks.v2.homeassistant import UnitOfEnergy, UnitOfPower, UnitOfTemperature
from zigpy.quirks.v2.homeassistant.sensor import SensorDeviceClass, SensorStateClass
from zigpy.types import t

from zhaquirks.tuya.builder import TuyaQuirkBuilder


class SystemMode(t.enum8):
    """Tuya SystemMode enum."""

    Off = 0x00
    Heat = 0x01


class PresetMode(t.enum8):
    """Tuya PresetMode enum."""

    Manual = 0x00
    Home = 0x01
    Away = 0x02


class SensorMode(t.enum8):
    """Tuya SensorMode enum."""

    Air = 0x00
    Floor = 0x01
    Both = 0x02


class RunningState(t.enum8):
    """Tuya RunningState enum."""

    Idle = 0x00
    Heat = 0x01


(
    TuyaQuirkBuilder("_TZE204_p3lqqy2r", "TS0601")
    .tuya_enum(
        dp_id=1,
        attribute_name="system_mode",
        enum_class=SystemMode,
        translation_key="system_mode",
        fallback_name="System mode",
    )
    .tuya_enum(
        dp_id=2,
        attribute_name="preset_mode",
        enum_class=PresetMode,
        translation_key="preset_mode",
        fallback_name="Preset mode",
    )
    .tuya_number(
        dp_id=16,
        type=t.int16s,
        attribute_name="current_heating_setpoint",
        min_value=5,
        max_value=35,
        step=1,
        unit=UnitOfTemperature.CELSIUS,
        translation_key="heating_setpoint",
        fallback_name="Heating setpoint",
    )
    .tuya_sensor(
        dp_id=36,
        attribute_name="local_temperature",
        type=t.int16s,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        translation_key="local_temperature",
        fallback_name="Air temperature",
    )
    .tuya_sensor(
        dp_id=101,
        attribute_name="local_temperature_floor",
        type=t.int16s,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfTemperature.CELSIUS,
        translation_key="local_temperature_floor",
        fallback_name="Floor temperature",
    )
    .tuya_enum(
        dp_id=102,
        attribute_name="temperature_sensor_select",
        enum_class=SensorMode,
        translation_key="sensor_mode",
        fallback_name="Sensor mode",
    )
    .tuya_enum(
        dp_id=104,
        attribute_name="running_state",
        enum_class=RunningState,
        translation_key="running_state",
        fallback_name="Heating status",
    )
    .tuya_binary_sensor(
        dp_id=106,
        attribute_name="window_detection",
        translation_key="window_detection",
        fallback_name="Open window detection",
    )
    .tuya_number(
        dp_id=107,
        type=t.int16s,
        attribute_name="max_temperature_protection",
        min_value=20,
        max_value=95,
        step=1,
        unit=UnitOfTemperature.CELSIUS,
        translation_key="max_temperature_protection",
        fallback_name="Max temperature",
    )
    .tuya_number(
        dp_id=109,
        type=t.int16s,
        attribute_name="local_temperature_calibration",
        min_value=-9,
        max_value=9,
        step=1,
        unit=UnitOfTemperature.CELSIUS,
        translation_key="temperature_calibration",
        fallback_name="Temperature calibration",
    )
    .tuya_sensor(
        dp_id=122,
        attribute_name="power",
        type=t.int16s,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        unit=UnitOfPower.WATT,
        translation_key="power",
        fallback_name="Power",
    )
    .tuya_sensor(
        dp_id=123,
        attribute_name="energy",
        type=t.int16s,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        translation_key="energy",
        fallback_name="Energy",
    )
    .skip_configuration()
    .add_to_registry()
)
