"""Page 13h (Module Performance Diagnostics Control): loopback
capabilities and current loopback-enable state (Section 8.11).

Deliberately READ-ONLY -- actually enabling loopback is traffic-affecting
(it redirects a live lane's signal path) and this project doesn't drive
it live without explicit opt-in, unlike Page 10h's DPDeinit (where a
same-value no-op write is genuinely harmless) or Page 03h's User EEPROM
(which exists specifically to be written to). Toggling loopback on then
back off still interrupts traffic for that window, so there's no
equivalent safe round trip here.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped for Flat Memory modules and modules that don't
advertise Pages 13h/14h (Page 01h byte 142 bit 5).
"""

import pytest

import cmis
import cmis_helpers


def _require_diag_pages(bridge, module_info):
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 13h isn't supported (Table 8-4)")

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
