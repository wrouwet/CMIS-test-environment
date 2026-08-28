"""Pages 10h/11h (Lane/Data Path Control and Status): the per-lane Data
Path state machine (Table 8-74) that governs whether a lane is actually
passing traffic.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules (Table 8-4).
Bank 0 only (lanes 1-8) -- sufficient for any module with up to 8 lanes
(e.g. QSFP-DD); a module with more lanes would need higher banks, not
handled here yet.
"""

import pytest

import cmis
import cmis_helpers


def _require_paged(module_info):
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Pages 10h/11h aren't supported (Table 8-4)")


def test_page11_lane_status(bridge, module_info):
    """Read Page 11h and confirm every lane's Data Path state decodes to
    one of the 7 defined (non-reserved) encodings (Table 8-74) -- an
    undefined encoding would indicate either a real module fault or a
    decoding bug, not a state this suite should silently accept."""
    _require_paged(module_info)

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_LANE_STATUS)
    data = cmis_helpers.read_upper_memory(bridge)
    decoded = cmis.parse_page11_lane_status(data)

    for lane, state in sorted(decoded["dp_state"].items()):
        name = cmis.DP_STATE_NAMES.get(state, "UNKNOWN/RESERVED")
        status = decoded["output_status"][lane]
        print(
            f"[cmis-discover] lane {lane}: DPState={state:X}h ({name}), "
            f"rx_valid={status['rx_valid']}, tx_valid={status['tx_valid']}"
        )
        assert state in cmis.DP_STATE_NAMES, (
            f"lane {lane} reported an undefined DPState encoding (0x{state:X}) -- "
            f"see Table 8-74 for the 7 valid encodings (1h-7h)"
        )


def test_page10_data_path_control_roundtrip(bridge, module_info):
    """Read back Page 10h's Data Path Control byte (128) without writing
    anything -- this project doesn't drive DPDeinit against a real module
    yet (that changes live traffic state), just confirms the byte is
    readable and reports its current per-lane deinit bitmap for
    visibility."""
    _require_paged(module_info)

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_LANE_CONTROL)
    data = cmis_helpers.read_upper_memory(bridge)
    dp_control = data[cmis.PAGE10_DATA_PATH_CONTROL_BYTE - cmis.UPPER_MEMORY_BASE]
    print(f"[cmis-discover] Page 10h DPDeinit bitmap: {dp_control:08b}b")
