"""Page 03h (User EEPROM): host-writable, vendor-unspecified-use
non-volatile memory (Section 8.6) -- the one page in this project's
scope where writing arbitrary test data is actually within spec, since
the whole page exists for exactly that purpose.

NOT yet run against real hardware -- see the project README's "Current
status" section. Uses cmis_helpers.try_select_page() rather than the
Page 01h advertisement bit to gate this test -- more robust, since it
doesn't depend on this project's not-yet-independently-reread bit
position for page03_user_eeprom_supported (see cmis.py's Page 01h
section) actually being right.
"""

import cmis
import cmis_helpers


def test_page03_user_eeprom_roundtrip(bridge):
    """Write a small known pattern to the start of Page 03h, read it
    back, then restore whatever was there before -- a real write/read
    round trip, kept non-destructive by saving and restoring the
    original bytes. Skipped (via try_select_page) if the module doesn't
    actually support this optional page."""
    took = cmis_helpers.try_select_page(bridge, bank=0x00, page=cmis.PAGE_USER_EEPROM)
    if not took:
        import pytest
        pytest.skip("Page 03h (User EEPROM) is not selectable on this module -- likely not supported")

    original = cmis_helpers.read_upper_memory(bridge)
    original_prefix = original[:4]
    print(f"[cmis-discover] Page 03h original first 4 bytes: {original_prefix.hex()}")

    test_pattern = bytes([0xDE, 0xAD, 0xBE, 0xEF])
    try:
        cmis_helpers.write_user_eeprom(bridge, cmis.PAGE03_USER_EEPROM_BASE, test_pattern)
        readback = cmis_helpers.read_upper_memory(bridge)[:4]
        print(f"[cmis-discover] Page 03h readback after write: {readback.hex()}")
        assert readback == test_pattern, (
            f"wrote {test_pattern.hex()} to Page 03h, read back {readback.hex()} -- "
            f"write path may not be working, or this page isn't truly writable "
            f"despite selecting successfully"
        )
    finally:
        cmis_helpers.write_user_eeprom(bridge, cmis.PAGE03_USER_EEPROM_BASE, original_prefix)
        restored = cmis_helpers.read_upper_memory(bridge)[:4]
        print(f"[cmis-discover] Page 03h restored to: {restored.hex()}")
        assert restored == original_prefix, (
            "failed to restore Page 03h's original contents after the test write -- "
            "the module's user EEPROM has been left modified"
        )
