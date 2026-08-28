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


def test_cdb_command_framing_matches_spec_worked_example():
    """Pure unit check, no hardware needed: the spec gives one concrete
    worked example (Table 9-6/Section 9.3.5) -- the 0004h Abort command,
    sent with no LPL payload, has a FIXED CdbChkCode of FCh. This is the
    only hard data point available to validate build_cdb_command()'s
    checksum convention against (see cmis.build_cdb_command()'s docstring
    for why it uses negation rather than a plain bitwise complement)."""
    abort = cmis.build_cdb_command(cmis.CDB_CMD_ABORT)
    checksum = abort[cmis.CDB_CMD_HEADER_CHECKSUM - cmis.CDB_CMD_HEADER_CMDID[0]]
    print(f"Abort command bytes: {abort.hex()}, checksum byte: 0x{checksum:02x}")
    assert checksum == 0xFC, (
        f"expected the spec's documented fixed CdbChkCode 0xFC for a zero-payload "
        f"Abort command, computed 0x{checksum:02x} -- the checksum algorithm "
        f"assumption in cmis.compute_cdb_checksum() may be wrong"
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


def test_cdb_module_and_firmware_management_features(bridge, module_info):
    """Send Module Features (0040h) and Firmware Management Features
    (0041h) -- capability-discovery commands a real host would call before
    attempting a firmware update. This project doesn't have a confirmed
    byte-level reply layout for these two (unlike Get Firmware Info), so
    it prints the raw reply bytes for visibility rather than decoding
    them -- a real module's response here is exactly the kind of data
    that should feed back into cmis.py once seen."""
    _require_cdb(bridge, module_info)

    for name, cmd_id in (("Module Features", cmis.CDB_CMD_MODULE_FEATURES),
                          ("Firmware Management Features", cmis.CDB_CMD_FW_MANAGEMENT_FEATURES)):
        cmis_helpers.send_cdb_command(bridge, cmd_id)
        status = cmis_helpers.poll_cdb_status(bridge)
        reply = cmis_helpers.read_cdb_reply(bridge)
        print(f"[cmis-discover] CDB {name} ({cmd_id:#06x}): status={status}, "
              f"raw reply LPL={reply['lpl_payload'].hex()}")
        assert status is not None and status["state"] != "in_progress"


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
