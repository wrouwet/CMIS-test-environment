"""Page selection (bytes 0x7E/0x7F) is itself a command/response protocol
-- write a page number, read back what the module actually latched -- and
deserves direct black-box testing, not just incidental use as plumbing
for other tests.

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

import cmis
import cmis_helpers


def test_select_page00_is_idempotent(bridge):
    """Selecting Page 00h (the default/reset page) twice in a row should
    read back the same way both times -- a basic sanity check on the
    write-then-readback round trip itself, independent of any particular
    page's content."""
    for attempt in range(2):
        cmis_helpers.select_page(bridge, bank=0x00, page=0x00)
        lower = cmis.parse_lower_memory(cmis_helpers.read_lower_memory(bridge))
        print(f"attempt {attempt}: page_select=0x{lower['page_select']:02x} bank_select=0x{lower['bank_select']:02x}")
        assert lower["page_select"] == 0x00
        assert lower["bank_select"] == 0x00


def test_unsupported_page_falls_back_to_page00(bridge, module_info):
    """Confirmed spec gotcha (Section 8.2.13): writing an unsupported
    page number does NOT error at the I2C level -- the module silently
    resets PageSelect back to 0x00. 0xEF/bank 0xEF is chosen as a page
    number no CMIS revision through 5.3 defines (see cmis.VERSION_HISTORY
    for the researched page list) -- if a future revision ever legitimately
    defines it, this test's premise (not this project's decoding) would
    be what's wrong.

    Skipped for Flat Memory modules -- Table 8-4 says they only ever
    implement Page 00h, so this is exactly the same case as a
    Paged module's "unsupported page" path, not a separate one worth
    double-testing.
    """
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        import pytest
        pytest.skip("Flat Memory module -- every non-zero page is 'unsupported' by definition (Table 8-4)")

    took = cmis_helpers.try_select_page(bridge, bank=0xEF, page=0xEF)
    lower = cmis.parse_lower_memory(cmis_helpers.read_lower_memory(bridge))
    print(f"after selecting bank=0xEF/page=0xEF: page_select=0x{lower['page_select']:02x} "
          f"bank_select=0x{lower['bank_select']:02x}")
    assert not took, "module reported bank=0xEF/page=0xEF as successfully selected -- unexpected, check whether this really is an undefined page for the discovered revision"
    assert lower["page_select"] == 0x00, (
        f"expected PageSelect to fall back to 0x00 per the documented gotcha, "
        f"got 0x{lower['page_select']:02x}"
    )


def test_page_select_survives_a_lower_memory_read(bridge):
    """Reading Lower Memory (which itself includes the PageSelect byte)
    shouldn't perturb the current page selection -- a real risk only if
    the read path and the page-select write path were, incorrectly,
    sharing mutable state somewhere in this project's own bridge
    plumbing, not something the module itself could cause; still worth a
    direct check since every other test's correctness depends on reads
    being side-effect-free."""
    cmis_helpers.select_page(bridge, bank=0x00, page=0x00)
    before = cmis.parse_lower_memory(cmis_helpers.read_lower_memory(bridge))["page_select"]
    cmis_helpers.read_lower_memory(bridge)
    cmis_helpers.read_lower_memory(bridge)
    after = cmis.parse_lower_memory(cmis_helpers.read_lower_memory(bridge))["page_select"]
    print(f"page_select before={before:#04x} after two extra reads={after:#04x}")
    assert before == after
