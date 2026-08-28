"""CDB (Command Data Block, Page 9Fh + Lower Memory CdbStatus): the
firmware-update/vendor-command mechanism (Section 8.15/9).

Exercises every CDB command this project can build a well-founded
argument for being SAFE to send unconditionally against a real module
with nothing else going on: Query Status (0000h, pure read), Abort
(0004h, a no-op when nothing is in progress -- the spec itself
recommends sending it to reach a known state), Module/Firmware
Management Features (0040h/0041h, capability queries), and Get Firmware
Info (0100h, a read). Commands with real side effects (password change,
firmware download/write/run/copy) are deliberately NOT sent here -- see
test_password.py for the one password-related command this project does
send live (CDB Enter Password, also just a state query in effect), and
cmis.py's build_cdb_*() functions for the framing a future, explicitly
opt-in destructive-CDB suite would build on.

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

import pytest

import cmis
import cmis_helpers


def _require_cdb(bridge, module_info):
    """Returns the decoded Page 01h advertising dict if the module
    supports paging AND advertises at least one CDB instance; skips
    (with a printed reason) otherwise."""
    cmis_helpers.require_paged(module_info, "CDB (Page 9Fh)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if advertising["cdb_instances_supported"] == 0:
        pytest.skip("module does not advertise CDB support (Page 01h CdbInstancesSupported=0)")
    return advertising


def test_cdb_command_framing_matches_spec_worked_examples():
    """Pure unit check, no hardware needed: cmis.compute_cdb_checksum()'s
    one's-complement formula was verified against FIVE independent
    zero-payload worked examples spanning CMIS 5.0-5.4 (Table 9-6 through
    9-9 area): 0040h=BFh, 0041h=BEh, 0042h=BDh, 0102h=FCh, 0107h=F7h.

    Deliberately does NOT test 0004h Abort here even though it's also a
    zero-payload command with a published CdbChkCode: CMIS 5.0's own
    Table 9-6 lists it as FCh, which is a documented spec erratum
    (corrected to FBh -- the value this formula actually produces -- in
    every subsequent revision, 5.1 through 5.4). Testing against the
    corrected value here to guard against ever regressing back toward
    the erratum by mistake."""
    expected = {
        cmis.CDB_CMD_MODULE_FEATURES: 0xBF,
        cmis.CDB_CMD_FW_MANAGEMENT_FEATURES: 0xBE,
        cmis.CDB_CMD_ABORT_FIRMWARE_DOWNLOAD: 0xFC,
        cmis.CDB_CMD_COMPLETE_FIRMWARE_DOWNLOAD: 0xF7,
        cmis.CDB_CMD_ABORT: 0xFB,  # corrected value, NOT the CMIS 5.0 erratum (0xFC)
    }
    for cmd_id, expected_checksum in expected.items():
        command = cmis.build_cdb_command(cmd_id)
        checksum = command[cmis.CDB_CMD_HEADER_CHECKSUM - cmis.CDB_CMD_HEADER_CMDID[0]]
        print(f"cmd={cmd_id:#06x}: bytes={command.hex()}, checksum=0x{checksum:02x}")
        assert checksum == expected_checksum, (
            f"cmd {cmd_id:#06x}: expected CdbChkCode 0x{expected_checksum:02x}, "
            f"computed 0x{checksum:02x}"
        )


def test_cdb_query_status(bridge, module_info):
    """Send Query Status (0000h), wait for CdbStatus (Lower Memory, NOT
    the Page 9Fh reply header -- see cmis_helpers.poll_cdb_status()'s
    docstring for why) to leave 'in_progress', then decode both the
    command-level outcome and the reply's own unlock-level payload."""
    _require_cdb(bridge, module_info)

    cmis_helpers.send_cdb_full_command(bridge, cmis.build_cdb_query_status())
    status = cmis_helpers.poll_cdb_status(bridge)
    print(f"[cmis-discover] CDB Query Status command outcome: {status}")
    assert status is not None and status["state"] != "in_progress", (
        "CdbStatus never left 'in_progress' within the poll timeout for a plain Query Status"
    )
    assert status["state"] == "success", f"Query Status itself failed: {status}"

    reply = cmis_helpers.read_cdb_reply(bridge)
    decoded = cmis.parse_cdb_query_status_reply(reply["lpl_payload"])
    print(f"[cmis-discover] CDB Query Status reply payload: {decoded}")


def test_cdb_abort_is_a_safe_noop(bridge, module_info):
    """Send Abort (0004h) with nothing in progress -- the spec lists this
    as a normal way to force a known idle state, not something that can
    corrupt module state, so it's safe to send unconditionally."""
    _require_cdb(bridge, module_info)

    cmis_helpers.send_cdb_command(bridge, cmis.CDB_CMD_ABORT)
    status = cmis_helpers.poll_cdb_status(bridge)
    print(f"[cmis-discover] CDB Abort outcome: {status}")
    assert status is not None and status["state"] != "in_progress"


def test_cdb_module_features(bridge, module_info):
    """Send Module Features (0040h, Table 9-8) and decode which CDB
    commands the module claims to support -- capability discovery a real
    host would do before attempting anything CDB-command-specific."""
    _require_cdb(bridge, module_info)

    cmis_helpers.send_cdb_command(bridge, cmis.CDB_CMD_MODULE_FEATURES)
    status = cmis_helpers.poll_cdb_status(bridge)
    assert status is not None and status["state"] != "in_progress"

    reply = cmis_helpers.read_cdb_reply(bridge)
    if status["state"] == "success" and len(reply["lpl_payload"]) >= 36:
        decoded = cmis.parse_cdb_module_features(reply["lpl_payload"])
        supported_hex = sorted(f"0x{c:04x}" for c in decoded["supported_cmds"])
        print(f"[cmis-discover] CDB Module Features: max_completion_time="
              f"{decoded['max_completion_time_ms']}ms, supported_cmds={supported_hex}")
    else:
        print(f"[cmis-discover] CDB Module Features did not return a decodable reply: "
              f"status={status}, raw={reply['lpl_payload'].hex()}")


def test_cdb_firmware_management_features(bridge, module_info):
    """Send Firmware Management Features (0041h, Table 9-9) and decode
    the module's firmware-update capabilities/limits (EPL/LPL size
    limits, supported mechanisms, max command durations) -- exactly the
    data a real firmware-update client needs before starting."""
    _require_cdb(bridge, module_info)

    cmis_helpers.send_cdb_command(bridge, cmis.CDB_CMD_FW_MANAGEMENT_FEATURES)
    status = cmis_helpers.poll_cdb_status(bridge)
    assert status is not None and status["state"] != "in_progress"

    reply = cmis_helpers.read_cdb_reply(bridge)
    if status["state"] == "success" and len(reply["lpl_payload"]) >= 18:
        decoded = cmis.parse_cdb_fw_management_features(reply["lpl_payload"])
        print(f"[cmis-discover] CDB Firmware Management Features: {decoded}")
    else:
        print(f"[cmis-discover] CDB Firmware Management Features did not return a decodable "
              f"reply: status={status}, raw={reply['lpl_payload'].hex()}")


def test_cdb_rejects_bad_checksum(bridge, module_info):
    """Negative-path test: send a syntactically well-formed Query Status
    command with a deliberately corrupted CdbChkCode byte, and confirm
    the module reports CdbStatus failure with result code 0x05
    ('CdbChkCode error', Table 8-13) -- not silently accepting it, and
    not crashing/hanging. This is the only negative-path CDB test this
    project sends live, since corrupting a command that would otherwise
    have a real side effect risks the module executing something
    unintended if it turns out to (incorrectly) ignore the bad checksum;
    Query Status has no side effect either way, making it safe to use
    for this specific check.
    """
    _require_cdb(bridge, module_info)

    good_command = bytearray(cmis.build_cdb_query_status())
    checksum_index = cmis.CDB_CMD_HEADER_CHECKSUM - cmis.CDB_CMD_HEADER_CMDID[0]
    good_command[checksum_index] ^= 0xFF  # guaranteed different from the correct value
    cmis_helpers.send_cdb_full_command(bridge, bytes(good_command))

    status = cmis_helpers.poll_cdb_status(bridge)
    print(f"[cmis-discover] CDB bad-checksum outcome: {status}")
    assert status is not None and status["state"] != "in_progress"
    assert status["state"] == "failed", (
        f"sent Query Status with a deliberately corrupted checksum, but the module "
        f"reported '{status['state']}' instead of 'failed' -- it may not be validating "
        f"CdbChkCode at all"
    )
    if status["result_code"] != cmis.CDB_RESULT_FAILED_CHECKSUM_ERROR:
        print(f"[cmis-discover] module failed the bad-checksum command but with result "
              f"code 0x{status['result_code']:02x} ({status['meaning']}), not the expected "
              f"0x05 CdbChkCode error -- still a failure, just not the exact reason expected")


def test_cdb_rejects_unknown_cmdid(bridge, module_info):
    """Negative-path test: send a CMDID from a range no CDB command in
    this project's researched spec text (4.0-5.3) defines, and confirm
    the module reports failure -- ideally result code 0x01 ('CMDID
    unknown', Table 8-13), though this is soft-checked since a vendor
    could legitimately implement a custom command in this space."""
    _require_cdb(bridge, module_info)

    UNASSIGNED_CMDID = 0xFFFE  # not defined by any researched CDB command table
    cmis_helpers.send_cdb_command(bridge, UNASSIGNED_CMDID)
    status = cmis_helpers.poll_cdb_status(bridge)
    print(f"[cmis-discover] CDB unknown-CMDID (0x{UNASSIGNED_CMDID:04x}) outcome: {status}")
    assert status is not None and status["state"] != "in_progress"
    if status["state"] != "failed":
        print(f"[cmis-discover] module reported '{status['state']}' for an unassigned CMDID "
              f"-- either it implements a vendor-custom command here, or doesn't validate CMDID")


def test_cdb_get_firmware_info(bridge, module_info):
    """Send Get Firmware Info (0100h) and decode the reply (Table 9-15) --
    this is a read, safe to send unconditionally. Only prints/soft-checks
    since a real module's exact FirmwareStatus/ImageInformation bits
    aren't something this project can predict in advance."""
    _require_cdb(bridge, module_info)

    cmis_helpers.send_cdb_command(bridge, cmis.CDB_CMD_GET_FIRMWARE_INFO)
    status = cmis_helpers.poll_cdb_status(bridge)
    assert status is not None and status["state"] != "in_progress"

    reply = cmis_helpers.read_cdb_reply(bridge)
    if status["state"] == "success" and len(reply["lpl_payload"]) >= 2:
        decoded = cmis.parse_cdb_get_firmware_info(reply["lpl_payload"])
        print(f"[cmis-discover] CDB Get Firmware Info: {decoded}")
    else:
        print(f"[cmis-discover] CDB Get Firmware Info did not return a decodable reply: "
              f"status={status}, raw={reply['lpl_payload'].hex()}")
