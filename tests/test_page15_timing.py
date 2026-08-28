"""Page 15h (Timing Characteristics): per-lane module transit latency
(Section 8.13).

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped for Flat Memory modules and for modules that
don't advertise this optional page (Page 01h byte 145 bit 3).
"""

import pytest

import cmis
import cmis_helpers


def test_page15_timing_characteristics(bridge, module_info):
    """Read Page 15h and print each lane's Rx/Tx transit latency. Only
    printed, not asserted on beyond basic range sanity -- the spec itself
    says this page's accuracy/update-timing semantics are undefined in
    this revision, so there's no documented "correct" value to check
    against, only "did the read/decode work at all"."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 15h isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["timing_page15h_supported"]:
        pytest.skip("module does not advertise Page 15h support (Page 01h byte 145 bit 3 = 0)")

    timing = cmis_helpers.read_page15_timing(bridge)
    for lane in range(1, 9):
        rx_ns = timing["rx_latency_ns"][lane]
        tx_ns = timing["tx_latency_ns"][lane]
        print(f"[cmis-discover] lane {lane}: rx_latency={rx_ns}ns, tx_latency={tx_ns}ns")
        assert 0 <= rx_ns <= 0xFFFF and 0 <= tx_ns <= 0xFFFF
