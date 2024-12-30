"""Tuya TS0121 plug."""

from zigpy.quirks.v2 import QuirkBuilder

from zhaquirks.tuya import (
    TuyaNewManufCluster,
    TuyaZBE000Cluster,
    TuyaZBElectricalMeasurement,
    TuyaZBExternalSwitchTypeCluster,
    TuyaZBMeteringCluster,
    TuyaZBOnOffAttributeCluster,
)

(
    QuirkBuilder(model="TS0121")
    .replaces(TuyaZBOnOffAttributeCluster)
    .replaces(TuyaZBMeteringCluster)
    .replaces(TuyaZBElectricalMeasurement)
    .add_to_registry()
)

(
    QuirkBuilder(model="TS0121")
    .replaces(TuyaZBOnOffAttributeCluster)
    .replaces(TuyaZBMeteringCluster)
    .replaces(TuyaZBElectricalMeasurement)
    .replaces(TuyaZBE000Cluster)
    .replaces(TuyaZBExternalSwitchTypeCluster)
    .add_to_registry()
)

(
    QuirkBuilder("_TZ3000_5ity3zyu", "TS0121")
    .replaces(TuyaZBOnOffAttributeCluster)
    .replaces(TuyaZBMeteringCluster)
    .replaces(TuyaZBElectricalMeasurement)
    .replaces(TuyaNewManufCluster)
    .add_to_registry()
)
