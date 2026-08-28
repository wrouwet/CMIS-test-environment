"""Pages 16h/17h (Network Path Functionality + its Flags/Masks,
introduced CMIS 5.1): mirrors Page 10h/11h's Data Path Control/Status
pattern for multiplex-media "Network Path" lanes.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped for Flat Memory modules and modules that don't
advertise Pages 16h/17h (Page 01h byte 142 bit 7) -- also naturally
never present on any module reporting a CMIS revision below 5.1 (see
cmis.VERSION_HISTORY), though the advertisement-bit check alone is
sufficient and this project doesn't hardcode that version gate.
"""

import pytest

import cmis
import cmis_helpers


def _require_network_path(bridge, module_info):
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Pages 16h/17h aren't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["network_path_pages_supported"]:
        pytest.skip("module does not advertise Pages 16h/17h (Page 01h byte 142 bit 7 = 0)")


def test_page16_network_path_status(bridge, module_info):
    """Read Page 16h and confirm every lane's Network Path state decodes
    to one of the 7 defined encodings -- same pattern as
    test_datapath.py's Page 11h DPState check."""
    _require_network_path(bridge, module_info)

    states = cmis_helpers.read_page16_network_path_status(bridge)
    for lane, state in sorted(states.items()):
        name = cmis.NP_STATE_NAMES.get(state, "UNKNOWN/RESERVED")
        print(f"[cmis-discover] lane {lane}: NPState={state:X}h ({name})")
        assert state in cmis.NP_STATE_NAMES, (
            f"lane {lane} reported an undefined NPState encoding (0x{state:X})"
        )


def test_page16_np_control_roundtrip(bridge, module_info):
    """Same non-destructive pattern as test_datapath.py's Page 10h test:
    read the NP Control byte (160) and write the SAME value back,
    confirming the write path works without changing any lane's actual
    init/deinit state."""
    _require_network_path(bridge, module_info)

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_NETWORK_PATH)
    data = cmis_helpers.read_upper_memory(bridge)
    np_control = data[cmis.PAGE16_NP_CONTROL_BYTE - cmis.UPPER_MEMORY_BASE]
    print(f"[cmis-discover] Page 16h NPDeinit bitmap (before): {np_control:08b}b")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_NETWORK_PATH)
    bridge.write(cmis.CMIS_I2C_ADDR, [cmis.PAGE16_NP_CONTROL_BYTE, np_control])
    import time
    time.sleep(cmis.T_WRITE_MS / 1000.0)

    readback = cmis_helpers.read_upper_memory(bridge)
    np_control_after = readback[cmis.PAGE16_NP_CONTROL_BYTE - cmis.UPPER_MEMORY_BASE]
    print(f"[cmis-discover] Page 16h NPDeinit bitmap (after no-op write): {np_control_after:08b}b")
    assert np_control_after == np_control


def test_page17_np_flags(bridge, module_info):
    """Read Page 17h's NPStateChangedFlag bits -- purely informational,
    since a set flag just means some lane's state changed since it was
    last cleared, which may be entirely expected during a fresh session."""
    _require_network_path(bridge, module_info)

    flags = cmis_helpers.read_page17_np_flags(bridge)
    print(f"[cmis-discover] Page 17h NPStateChangedFlag: {flags}")
