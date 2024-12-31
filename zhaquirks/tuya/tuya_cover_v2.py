"""Tuya TRV."""

from zigpy.quirks.v2 import EntityPlatform
from zigpy.types import t
from zigpy.zcl.clusters.closures import WindowCovering

from zhaquirks.tuya import TuyaLocalCluster
from zhaquirks.tuya.builder import TuyaQuirkBuilder


class TuyaCoverState(t.enum8):
    """Tuya Cover State enum."""

    Open = 0x00
    Stop = 0x01
    Close = 0x02


class TuyaOpeningMode(t.enum8):
    """Tuya Opening Mode enum."""

    Tilt = 0x00
    Lift = 0x01


class TuyaWorkState(t.enum8):
    """Tuya Work State enum."""

    Standby = 0x00
    Success = 0x01
    Learning = 0x02


class TuyaMotorDirection(t.enum8):
    """Tuya Motor Direction enum."""

    Left = 0x00
    Right = 0x01


class TuyaSetUpperLimit(t.enum8):
    """Tuya Set Upper Limit enum."""

    Stop = 0x00
    Start = 0x01


class TuyaCoveringCluster(WindowCovering, TuyaLocalCluster):
    """Tuya Window Covering Cluster."""


(
    TuyaQuirkBuilder("_TZE200_cpbo62rn", "TS0601")
    .applies_to("_TZE200_libht6ua", "TS0601")
    .tuya_enum(
        dp_id=1,
        attribute_name="state",
        enum_class=TuyaCoverState,
        translation_key="state",
        fallback_name="State",
    )
    .tuya_dp(
        dp_id=2,
        ep_attribute=TuyaCoveringCluster.ep_attribute,
        attribute_name=WindowCovering.AttributeDefs.current_position_lift_percentage.name,
        converter=lambda x: 100 - x,
    )
    .tuya_dp(
        dp_id=3,
        ep_attribute=TuyaCoveringCluster.ep_attribute,
        attribute_name=WindowCovering.AttributeDefs.current_position_lift_percentage.name,
        converter=lambda x: 100 - x,
    )
    .tuya_dp(
        dp_id=4,
        ep_attribute=TuyaCoveringCluster.ep_attribute,
        attribute_name=WindowCovering.AttributeDefs.window_covering_mode.name,
        converter=lambda x: WindowCovering.WindowCoveringType.Rollershade
        if x == TuyaOpeningMode.Lift
        else WindowCovering.WindowCoveringType.Shutter,
        dp_converter=lambda x: TuyaOpeningMode.Lift
        if x == WindowCovering.WindowCoveringType.Rollershade
        else TuyaOpeningMode.Tilt,
    )
    .tuya_enum(
        dp_id=7,
        attribute_name="work_state",
        enum_class=TuyaWorkState,
        entity_platform=EntityPlatform.SENSOR,
        translation_key="work_state",
        fallback_name="Work state",
    )
    .tuya_battery(dp_id=13)
    .tuya_enum(
        dp_id=101,
        attribute_name="motor_direction",
        enum_class=TuyaMotorDirection,
        translation_key="motor_direction",
        fallback_name="Motor direction",
    )
    .tuya_enum(
        dp_id=102,
        attribute_name="set_upper_limit",
        enum_class=TuyaSetUpperLimit,
        translation_key="set_upper_limit",
        fallback_name="Set upper limit",
    )
    # 107 is factory reset, but z2m just throws an error saying you can't
)
