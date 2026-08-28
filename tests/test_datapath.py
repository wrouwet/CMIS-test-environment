"""Pages 10h/11h (Lane/Data Path Control and Status): the per-lane Data
Path state machine (Table 8-74) that governs whether a lane is actually
passing traffic.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules (Table 8-4).
Bank 0 only (lanes 1-8) -- sufficient for any module with up to 8 lanes
(e.g. QSFP-DD); a module with more lanes would need higher banks, not
handled here yet.
"""

import cmis
import cmis_helpers


def _require_paged(module_info):
    cmis_helpers.require_paged(module_info, "Pages 10h/11h")


def test_page11_lane_status(bridge, module_info):
    """Read Page 11h and confirm every lane's Data Path state decodes to
    one of the 7 defined (non-reserved) encodings (Table 8-74) -- an
    undefined encoding would indicate either a real module fault or a
    decoding bug, not a state this suite should silently accept."""
    _require_paged(module_info)

    took = cmis_helpers.try_select_page(bridge, bank=0x00, page=cmis.PAGE_LANE_STATUS)
    assert took, (
        "Page 11h is mandatory for any Paged-memory module (Table 8-4) but did not "
        "read back as selected"
    )
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
    """Read Page 10h's Data Path Control byte (128), then write the SAME
    value back and confirm it reads back unchanged -- this exercises the
    real write command/response path for this register (not just a read)
    while remaining non-destructive: DPDeinitLane<i>=0 means "initialize
    this lane," and writing back exactly what's already there changes no
    lane's actual init/deinit state, only proves the write path works.
    Actually setting a lane's traffic state is left to a future,
    explicitly-opt-in test -- toggling it for real would interrupt live
    traffic, which this suite shouldn't do unprompted.
    """
    _require_paged(module_info)

    took = cmis_helpers.try_select_page(bridge, bank=0x00, page=cmis.PAGE_LANE_CONTROL)
    assert took, (
        "Page 10h is mandatory for any Paged-memory module (Table 8-4) but did not "
        "read back as selected"
    )
    data = cmis_helpers.read_upper_memory(bridge)
    dp_control = data[cmis.PAGE10_DATA_PATH_CONTROL_BYTE - cmis.UPPER_MEMORY_BASE]
    print(f"[cmis-discover] Page 10h DPDeinit bitmap (before): {dp_control:08b}b")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_LANE_CONTROL)
    bridge.write(cmis.CMIS_I2C_ADDR, [cmis.PAGE10_DATA_PATH_CONTROL_BYTE, dp_control])
    import time
    time.sleep(cmis.T_WRITE_MS / 1000.0)

    readback = cmis_helpers.read_upper_memory(bridge)
    dp_control_after = readback[cmis.PAGE10_DATA_PATH_CONTROL_BYTE - cmis.UPPER_MEMORY_BASE]
    print(f"[cmis-discover] Page 10h DPDeinit bitmap (after no-op write): {dp_control_after:08b}b")
    assert dp_control_after == dp_control, (
        f"writing back the same DPDeinit value changed it (0b{dp_control:08b} -> "
        f"0b{dp_control_after:08b}) -- the write path itself may be broken, or "
        f"lane state changed for an unrelated reason between the two reads"
    )
