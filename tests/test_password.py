"""Password mechanism (Section 8.2.12, Lower Memory bytes 118-125):
gates a small number of protected features (mainly password-change
itself, and some vendor-defined protected areas). Two independent
mechanisms exist for the same underlying password state -- this project
only exercises the direct register-write mechanism (the simpler of the
two); CDB_CMD_ENTER_PASSWORD/CDB_CMD_CHANGE_PASSWORD (Section 9.3.2/9.3.3)
are the CDB-based equivalent, not exercised here yet.

Deliberately does NOT attempt to CHANGE the password (that's a real,
persistent, hard-to-reverse write to a live module) -- only unlocks with
the well-known factory-default Host Password, which is a normal,
reversible test action (a wrong password or module reinit re-locks it).

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

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
