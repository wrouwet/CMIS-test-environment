"""CDB (Command Data Block, Page 9Fh): the firmware-update/vendor-command
mechanism (Section 8.15/9). Deliberately conservative -- the only command
exercised against real hardware here is Query Status (0000h), which is
read-only in effect (it just reports on the last command, or on nothing
if none was ever sent) and safe to send unconditionally. Commands with
real side effects (password change, firmware download/abort) are NOT
sent here -- see test_password.py for the one password test this project
does run live, and cmis_helpers.send_cdb_command()/read_cdb_reply() for
the plumbing a future, more thorough CDB suite would build on.

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

import pytest

import cmis
import cmis_helpers


def test_cdb_command_framing_matches_spec_worked_example():
    """Pure unit check, no hardware needed: the spec gives one concrete
    worked example (Table 9-6/§9.3.5) -- the 0004h Abort command, sent
    with no LPL payload, has a FIXED CdbChkCode of FCh. This is the only
    hard data point available to validate build_cdb_command()'s checksum
    convention against (see cmis.build_cdb_command()'s docstring for why
    it uses negation rather than a plain bitwise complement)."""
    abort = cmis.build_cdb_command(cmis.CDB_CMD_ABORT)
    checksum = abort[cmis.CDB_CMD_HEADER_CHECKSUM - cmis.CDB_CMD_HEADER_CMDID[0]]
    print(f"Abort command bytes: {abort.hex()}, checksum byte: 0x{checksum:02x}")
    assert checksum == 0xFC, (
        f"expected the spec's documented fixed CdbChkCode 0xFC for a zero-payload "
        f"Abort command, computed 0x{checksum:02x} -- the checksum algorithm "
        f"assumption in cmis.compute_cdb_checksum() may be wrong"
    )


def test_cdb_query_status(bridge, module_info):
    """If the module advertises any CDB support (Page 01h), send Query
    Status (0000h) and print the decoded reply. Query Status is the
    generic "is my last command done" poll -- sent here with nothing
    outstanding, so a real module is expected to report success/idle,
    but this test only prints the result rather than asserting a specific
    status code, since the exact idle-state encoding isn't confirmed."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- CDB (Page 9Fh) isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if advertising["cdb_instances_supported"] == 0:
        pytest.skip("module does not advertise CDB support (Page 01h CdbInstancesSupported=0)")

    cmis_helpers.send_cdb_command(bridge, cmis.CDB_CMD_QUERY_STATUS)
    reply = cmis_helpers.read_cdb_reply(bridge)
    print(f"[cmis-discover] CDB Query Status reply: {reply}")
