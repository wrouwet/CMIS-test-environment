"""Cross-checks the LIVE environmental monitors (Lower Memory bytes
14-17, read every session via the module_info fixture) against their
alarm/warning thresholds (Page 02h) -- the actual diagnostic purpose
these two register groups exist for, not just independently decoding
each in isolation (test_lower_memory.py / test_page02_thresholds.py).

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules (Page 02h
isn't supported, Table 8-4).
"""

import pytest

import cmis
import cmis_helpers


def test_temp_and_vcc_within_warning_thresholds(bridge, module_info):
    """A real module reporting live Temp/VCC outside its OWN advertised
    warning thresholds is either an active fault condition or a genuine
    decoding mismatch -- either way, worth failing loudly rather than
    silently printing, unlike this project's other threshold tests which
    only check internal ordering without a live value to compare against."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 02h isn't supported (Table 8-4)")

    took = cmis_helpers.try_select_page(bridge, bank=0x00, page=cmis.PAGE_THRESHOLDS)
    assert took, "Page 02h is mandatory for a Paged-memory module but did not read back as selected"
    thresholds = cmis.parse_page02_thresholds(cmis_helpers.read_upper_memory(bridge))

    temp_c = module_info["temperature_c"]
    vcc_v = module_info["vcc_v"]
    temp_th = thresholds["temp_c"]
    vcc_th = thresholds["vcc_v"]

    print(f"[cmis-discover] live temperature={temp_c:.2f}C, warning range="
          f"[{temp_th['low_warning']:.2f}, {temp_th['high_warning']:.2f}]C, "
          f"alarm range=[{temp_th['low_alarm']:.2f}, {temp_th['high_alarm']:.2f}]C")
    print(f"[cmis-discover] live VCC={vcc_v:.3f}V, warning range="
          f"[{vcc_th['low_warning']:.3f}, {vcc_th['high_warning']:.3f}]V, "
          f"alarm range=[{vcc_th['low_alarm']:.3f}, {vcc_th['high_alarm']:.3f}]V")

    assert temp_th["low_warning"] <= temp_c <= temp_th["high_warning"], (
        f"live temperature {temp_c:.2f}C is outside the module's own advertised "
        f"warning range [{temp_th['low_warning']:.2f}, {temp_th['high_warning']:.2f}]C -- "
        f"a real thermal condition worth investigating before assuming it's a test bug"
    )
    assert vcc_th["low_warning"] <= vcc_v <= vcc_th["high_warning"], (
        f"live VCC {vcc_v:.3f}V is outside the module's own advertised warning range "
        f"[{vcc_th['low_warning']:.3f}, {vcc_th['high_warning']:.3f}]V"
    )
