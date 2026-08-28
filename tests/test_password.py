"""Password mechanism (Section 8.2.12, Lower Memory bytes 118-125):
gates a small number of protected features (mainly password-change
itself, and some vendor-defined protected areas). Two independent
mechanisms exist for the same underlying password state: the direct
register-write mechanism, and CDB_CMD_ENTER_PASSWORD (Section 9.3.2) --
this project exercises both, since a given module may implement only
one, and the CDB path is the only one of the two that gives direct
success/failure feedback (via Query Status's Table 9-3 unlock_level
field, see cmis.parse_cdb_query_status_reply()).

Deliberately does NOT attempt to CHANGE the password (that's a real,
persistent, hard-to-reverse write to a live module) -- only unlocks with
the well-known factory-default Host Password, which is a normal,
reversible test action (a wrong password or module reinit re-locks it).

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

import pytest

import cmis
import cmis_helpers


def test_password_write_encoding():
    """Pure unit check, no hardware needed: confirm the 32-bit password
    is encoded as 4 big-endian bytes, matching the spec's documented
    factory-default Host Password value (0x00001011, Section 8.2.12)."""
    encoded = cmis.build_password_write(cmis.DEFAULT_HOST_PASSWORD)
    print(f"default host password encoded: {encoded.hex()}")
    assert encoded == bytes([0x00, 0x00, 0x10, 0x11])
    assert cmis.DEFAULT_HOST_PASSWORD <= cmis.HOST_PASSWORD_MAX
    assert cmis.MODULE_PASSWORD_MIN > cmis.HOST_PASSWORD_MAX


def test_unlock_with_default_host_password(bridge):
    """Write the factory-default Host Password to PasswordEntryArea
    (bytes 122-125) and confirm the write itself completes cleanly. This
    mechanism gives no direct success/failure feedback at the I2C level
    (unlike the CDB equivalent) -- whether it actually unlocked anything
    can only be inferred by a subsequent protected-feature test, which
    this project doesn't have yet (no protected feature has been
    identified to probe), so this test is deliberately limited to
    confirming the write path itself works.
    """
    cmis_helpers.unlock_password(bridge, cmis.DEFAULT_HOST_PASSWORD)
    print("[cmis-discover] wrote factory-default Host Password to PasswordEntryArea (0x7A-0x7D)")


def test_enter_password_via_cdb(bridge, module_info):
    """The CDB equivalent of the above -- CDB_CMD_ENTER_PASSWORD (0001h)
    with the factory-default Host Password -- but unlike the register
    mechanism, this one gives direct feedback: follow it with Query
    Status (0000h) and check the reply's unlock_level field (Table 9-3)
    actually reports 'host_password_accepted'. Skipped if the module
    doesn't advertise CDB support at all."""
    cmis_helpers.require_paged(module_info, "CDB (Page 9Fh)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if advertising["cdb_instances_supported"] == 0:
        pytest.skip("module does not advertise CDB support (Page 01h CdbInstancesSupported=0)")

    password_bytes = cmis.build_password_write(cmis.DEFAULT_HOST_PASSWORD)
    cmis_helpers.send_cdb_command(bridge, cmis.CDB_CMD_ENTER_PASSWORD, lpl_payload=password_bytes)
    status = cmis_helpers.poll_cdb_status(bridge)
    print(f"[cmis-discover] CDB Enter Password outcome: {status}")

    if status["state"] != "success":
        print(f"[cmis-discover] Enter Password did not succeed ({status['meaning']}) -- "
              f"module may not implement this mechanism, or rejected the default password")
        return

    cmis_helpers.send_cdb_full_command(bridge, cmis.build_cdb_query_status())
    cmis_helpers.poll_cdb_status(bridge)
    reply = cmis_helpers.read_cdb_reply(bridge)
    decoded = cmis.parse_cdb_query_status_reply(reply["lpl_payload"])
    print(f"[cmis-discover] post-unlock Query Status reply: {decoded}")
    assert decoded["unlock_level"] == "host_password_accepted", (
        f"sent Enter Password successfully but Query Status still reports "
        f"'{decoded['unlock_level']}' -- unexpected"
    )
