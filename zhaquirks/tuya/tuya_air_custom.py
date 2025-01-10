"""Tuya Air Quality sensor."""

from zigpy.quirks.v2 import QuirkBuilder
import zigpy.types as t
from zigpy.zcl.clusters.measurement import (
    PM25,
    CarbonDioxideConcentration,
    FormaldehydeConcentration,
)
from zigpy.zcl.foundation import BaseAttributeDefs, ZCLAttributeDef

from zhaquirks.tuya import TuyaLocalCluster
from zhaquirks.tuya.builder import TuyaQuirkBuilder, TuyaTemperatureMeasurement


class TuyaCO2Concetration(CarbonDioxideConcentration, TuyaLocalCluster):
    """Tuya Carbon Dioxide concentration measurement."""


class TuyaFormaldehydeConcetration(FormaldehydeConcentration, TuyaLocalCluster):
    """Tuya Formaldehyde concentration measurement."""


class TuyaPM25Concetration(PM25, TuyaLocalCluster):
    """Tuya PM25 concentration measurement."""


class CustomTemperature(t.Struct):
    """Custom temperature wrapper."""

    field_1: t.int16s_be
    temperature: t.int16s_be

    @classmethod
    def from_value(cls, value):
        """Convert from a raw value to a Struct data."""
        return cls.deserialize(value.serialize())[0]


class TuyaAirQualityVOC(TuyaLocalCluster):
    """Tuya VOC level cluster."""

    cluster_id = 0x042E
    name = "VOC Level"
    ep_attribute = "voc_level"

    class AttributeDefs(BaseAttributeDefs):
        """Attribute Definitions."""

        measured_value = ZCLAttributeDef(
            id=0x0000,
            type=t.Single,
            access="rp",
            is_manufacturer_specific=True,
        )
        min_measured_value = ZCLAttributeDef(
            id=0x0001,
            type=t.Single,
            access="rp",
            is_manufacturer_specific=True,
        )
        max_measured_value = ZCLAttributeDef(
            id=0x0002,
            type=t.Single,
            access="rp",
            is_manufacturer_specific=True,
        )
        tolerance = ZCLAttributeDef(
            id=0x0003,
            type=t.Single,
            access="rp",
            is_manufacturer_specific=True,
        )


class CustomTuyaQuirkBuilder(TuyaQuirkBuilder):
    """Custom Tuya Quirk Builder."""

    def tuya_co2(
        self,
        dp_id: int,
        co2_cfg: TuyaLocalCluster = TuyaCO2Concetration,
        scale: float = 1e-6,
    ) -> QuirkBuilder:
        """Add a Tuya CO2 Configuration."""
        self.tuya_dp(
            dp_id,
            co2_cfg.ep_attribute,
            CarbonDioxideConcentration.AttributeDefs.measured_value.name,
            converter=lambda x: x * scale,
        )
        self.adds(co2_cfg)
        return self

    def tuya_formaldehyde(
        self,
        dp_id: int,
        form_cfg: TuyaLocalCluster = TuyaFormaldehydeConcetration,
        scale: float = 1e-6,
    ) -> QuirkBuilder:
        """Add a Tuya Formaldehyde Configuration."""
        self.tuya_dp(
            dp_id,
            form_cfg.ep_attribute,
            FormaldehydeConcentration.AttributeDefs.measured_value.name,
            converter=lambda x: x * scale,
        )
        self.adds(form_cfg)
        return self

    def tuya_pm25(
        self,
        dp_id: int,
        pm25_cfg: TuyaLocalCluster = TuyaPM25Concetration,
        scale: float = 1,
    ) -> QuirkBuilder:
        """Add a Tuya PM25 Configuration."""
        self.tuya_dp(
            dp_id,
            pm25_cfg.ep_attribute,
            PM25.AttributeDefs.measured_value.name,
            converter=lambda x: x * scale,
        )
        self.adds(pm25_cfg)
        return self

    def tuya_voc(
        self,
        dp_id: int,
        voc_cfg: TuyaLocalCluster = TuyaAirQualityVOC,
        scale: float = 1e-6,
    ) -> QuirkBuilder:
        """Add a Tuya VOC Configuration."""
        self.tuya_dp(
            dp_id,
            voc_cfg.ep_attribute,
            TuyaAirQualityVOC.AttributeDefs.measured_value.name,
            converter=lambda x: x * scale,
        )
        self.adds(voc_cfg)


(
    TuyaQuirkBuilder("_TZE200_7bztmfm1", "TS0601")
    .applies_to("_TZE200_mja3fuja", "TS0601")
    .applies_to("_TZE200_dwcarsat", "TS0601")
    .applies_to("_TZE204_dwcarsat", "TS0601")
    .applies_to("_TZE200_8ygsuhe1", "TS0601")  # Tuya Air quality device with GPP
    .applies_to("_TZE200_ryfmq5rl", "TS0601")
    .applies_to("_TZE200_yvx5lh6k", "TS0601")
    .applies_to("_TZE204_yvx5lh6k", "TS0601")
    .applies_to("_TZE200_c2fmom5z", "TS0601")
    .applies_to("_TZE204_c2fmom5z", "TS0601")
    .tuya_co2(dp_id=2)
    .tuya_dp(
        dp_id=18,
        ep_attribute=TuyaTemperatureMeasurement.ep_attribute,
        attribute_name=TuyaTemperatureMeasurement.AttributeDefs.measured_value.name,
        converter=lambda x: CustomTemperature.from_value(x).temperature * 10,
    )
    .adds(TuyaTemperatureMeasurement)
    .tuya_humidity(dp_id=19, scale=10)
    .tuya_pm25(dp_id=20)
    .tuya_voc(dp_id=21)
    .tuya_dp(
        dp_id=22,
        ep_attribute=TuyaFormaldehydeConcetration.ep_attribute,
        attribute_name=TuyaFormaldehydeConcetration.AttributeDefs.measured_value.name,
        converter=lambda x: (24.45 * (x / 100.0) / 30.026) * 1e-6,
    )
    .adds(TuyaFormaldehydeConcetration)
    .skip_configuration()
    .add_to_registry()
)
