"""Page 02h (Module & Lane Thresholds): alarm/warning thresholds for the
same monitors read live in Lower Memory (test_lower_memory.py).

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules (Table 8-4).
"""

import pytest

import cmis
import cmis_helpers


def test_page02_thresholds(bridge, module_info):
    """Select Page 02h and sanity-check every decoded threshold quad
    (module-level Temp/VCC, lane-level TxPower/Bias/RxPower) is
    internally ordered correctly (High Alarm >= High Warning >= Low
    Warning >= Low Alarm) -- this doesn't need to know the module's
    actual thresholds to catch a byte-order/field-offset bug. Note: the
    lane-quad byte ordering (cmis.PAGE02_TX_POWER_THRESHOLDS etc.) is
    flagged in cmis.py as an inference pending independent confirmation
    -- if only the lane quads fail this check, that's the most likely
    place to look first."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 02h isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_THRESHOLDS)
    data = cmis_helpers.read_upper_memory(bridge)

    decoded = cmis.parse_page02_thresholds(data)
    print(f"decoded Page 02h thresholds: {decoded}")

    for name, quad in decoded.items():
        assert quad["high_alarm"] >= quad["high_warning"] >= quad["low_warning"] >= quad["low_alarm"], (
            f"{name} threshold quad is not monotonically ordered "
            f"(high_alarm >= high_warning >= low_warning >= low_alarm): {quad} -- "
            f"likely a decoding bug (wrong byte order/offset), not a real module config"
        )
