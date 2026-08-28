"""Page 14h (Module Performance Diagnostics Results): the DiagnosticsSelector
mux register plus its 64-byte Diagnostics Data window (Section 8.12).

Writing DiagnosticsSelector is safe to do live -- it only changes which
read-only result set the Diagnostics Data window currently shows, it
doesn't affect the datapath itself (unlike Page 13h's loopback controls).

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped for Flat Memory modules and modules that don't
advertise Pages 13h/14h (Page 01h byte 142 bit 5).
"""

import pytest

import cmis
import cmis_helpers


def test_page14_error_counters(bridge, module_info):
    """Select the Host Lane 1-4 error-counter view and decode it -- this
    project can fully decode this selector (plain U64 counters, Table
    8-116) without needing CMIS's F16 float format, unlike the BER/SNR
    selectors (see cmis.parse_page14_status()'s docstring)."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 14h isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["diagnostic_pages_supported"]:
        pytest.skip("module does not advertise Pages 13h/14h (Page 01h byte 142 bit 5 = 0)")

    status = cmis_helpers.read_page14_status(bridge, selector=cmis.DIAG_SELECTOR_HOST_COUNTERS_1_4)
    print(f"[cmis-discover] Page 14h selector={status['selector']:#04x} "
          f"({status['selector_name']}), loss_of_reference_clock={status['loss_of_reference_clock']}")
    if status["selector"] != cmis.DIAG_SELECTOR_HOST_COUNTERS_1_4:
        print(f"[cmis-discover] module reverted the selector write (reads back as "
              f"{status['selector']:#04x}) -- likely doesn't support this selector value")
        return

    for lane_index, counters in enumerate(status["lane_counters"]):
        print(f"[cmis-discover]   host lane {lane_index + 1}: {counters}")


def test_page14_ber(bridge, module_info):
    """Select the real-time BER selector and decode it via CMIS's F16
    format (cmis.decode_f16()) -- the byte-order convention used here
    (little-endian, matching this page's error counters) is flagged as
    an inference in cmis.parse_page14_ber()'s docstring, not an
    independently confirmed fact."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 14h isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["diagnostic_pages_supported"]:
        pytest.skip("module does not advertise Pages 13h/14h (Page 01h byte 142 bit 5 = 0)")

    status = cmis_helpers.read_page14_status(bridge, selector=cmis.DIAG_SELECTOR_BER_REALTIME)
    if status["selector"] != cmis.DIAG_SELECTOR_BER_REALTIME:
        print(f"[cmis-discover] module reverted the BER selector write (reads back as "
              f"{status['selector']:#04x}) -- likely doesn't support this selector value")
        return

    ber = status["ber"]
    for lane in range(8):
        print(f"[cmis-discover]   host lane {lane + 1} BER: {ber['host_ber'][lane]:.3e}, "
              f"media lane {lane + 1} BER: {ber['media_ber'][lane]:.3e}")
        assert ber["host_ber"][lane] >= 0.0 and ber["media_ber"][lane] >= 0.0
