"""Tests for Tuya Sensor quirks."""

from zigpy.zcl.clusters.general import Basic

import zhaquirks
from zhaquirks.tuya.mcu import TuyaMCUCluster

zhaquirks.setup()


async def test_handle_get_data(zigpy_device_from_v2_quirk):
    """Test handle_get_data for multiple attributes - normal battery."""

    quirked = zigpy_device_from_v2_quirk("_TZE204_dwcarsat", "TS0601")
    ep = quirked.endpoints[1]

    assert ep.basic is not None
    assert isinstance(ep.basic, Basic)

    assert ep.tuya_manufacturer is not None
    assert isinstance(ep.tuya_manufacturer, TuyaMCUCluster)
