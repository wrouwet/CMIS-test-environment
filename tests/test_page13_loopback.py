"""Page 13h (Module Performance Diagnostics Control): loopback
capabilities and current loopback-enable state (Section 8.11).

Read-only by default -- actually enabling loopback is traffic-affecting
(it redirects a live lane's signal path), unlike Page 10h's DPDeinit
(where a same-value no-op write is genuinely harmless) or Page 03h's
User EEPROM (which exists specifically to be written to). One test DOES
toggle loopback for real, but only when explicitly opted into via the
CMIS_ALLOW_DISRUPTIVE_TESTS=1 environment variable -- see
test_page13_loopback_enable_disable_roundtrip()'s docstring.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped for Flat Memory modules and modules that don't
advertise Pages 13h/14h (Page 01h byte 142 bit 5).
"""

import os

import pytest

import cmis
import cmis_helpers


def _require_diag_pages(bridge, module_info):
    cmis_helpers.require_paged(module_info, "Page 13h")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["diagnostic_pages_supported"]:
        pytest.skip("module does not advertise Pages 13h/14h (Page 01h byte 142 bit 5 = 0)")


def test_page13_loopback_capabilities(bridge, module_info):
    """Read what loopback modes the module CAN do (Table 8-89) -- purely
    informational, no assertion beyond successfully decoding."""
    _require_diag_pages(bridge, module_info)

    caps = cmis_helpers.read_page13_loopback_capabilities(bridge)
    print(f"[cmis-discover] Page 13h loopback capabilities: {caps}")


def test_page13_loopback_currently_disabled(bridge, module_info):
    """Confirm no loopback is currently active -- this is the state a
    module should be in during normal operation, and finding otherwise
    (in a fresh test session with no prior loopback test having run)
    would indicate either a leftover state from a previous session/tool,
    or a real module issue worth investigating before assuming test
    results from other pages reflect normal (non-looped-back) traffic."""
    _require_diag_pages(bridge, module_info)

    controls = cmis_helpers.read_page13_loopback_controls(bridge)
    print(f"[cmis-discover] Page 13h current loopback state: {controls}")
    active = {name: [lane for lane, enabled in lanes.items() if enabled]
              for name, lanes in controls.items()}
    active = {name: lanes for name, lanes in active.items() if lanes}
    assert not active, (
        f"module reports loopback already active on entering this test session: {active} -- "
        f"either leftover state from a previous tool/session, or worth investigating "
        f"before trusting other tests' live traffic-dependent readings"
    )


def test_page13_loopback_enable_disable_roundtrip(bridge, module_info):
    """Actually enable Media-Side Output loopback on lane 1, confirm it
    reads back as active, then disable it again and confirm it reads
    back as clear -- a real command/response exercise of the ONE control
    byte this project's other Page 13h test deliberately never writes.

    This IS traffic-affecting for the duration of the test (loopback
    redirects lane 1's media-side output signal path) -- gated behind
    CMIS_ALLOW_DISRUPTIVE_TESTS=1 so it never runs by accident in a
    normal `pytest tests/` invocation. Always disables loopback again in
    a `finally`, even if the enable-side assertion fails, so a failed
    assertion here doesn't leave the module in a disrupted state.
    """
    _require_diag_pages(bridge, module_info)
    if not os.environ.get("CMIS_ALLOW_DISRUPTIVE_TESTS"):
        pytest.skip("set CMIS_ALLOW_DISRUPTIVE_TESTS=1 to run this traffic-affecting test")

    caps = cmis_helpers.read_page13_loopback_capabilities(bridge)
    if not caps["media_side_output"]:
        pytest.skip("module does not advertise Media-Side Output loopback support (Page 13h byte 128 bit 0)")

    lane1_bit = 0x01
    try:
        cmis_helpers.write_page13_loopback_control(
            bridge, cmis.PAGE13_LOOPBACK_MEDIA_OUTPUT_BYTE, lane1_bit)
        enabled = cmis_helpers.read_page13_loopback_controls(bridge)
        print(f"[cmis-discover] after enabling lane 1 media-side output loopback: {enabled}")
        assert enabled["media_side_output_loopback"][1] is True, (
            "wrote lane 1's Media-Side Output loopback enable bit, but it didn't read back as set"
        )
    finally:
        cmis_helpers.write_page13_loopback_control(bridge, cmis.PAGE13_LOOPBACK_MEDIA_OUTPUT_BYTE, 0x00)
        disabled = cmis_helpers.read_page13_loopback_controls(bridge)
        print(f"[cmis-discover] after disabling: {disabled}")
        assert disabled["media_side_output_loopback"][1] is False, (
            "failed to disable lane 1's Media-Side Output loopback after the test -- "
            "the module has been left in a loopback state"
        )
