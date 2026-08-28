"""Cross-checks Page 01h's advertisement bits against what's actually
selectable (via the page-select readback gotcha, same mechanism as
test_page_enumeration.py) -- two independently-decoded facts about the
same module that should agree. A mismatch means either a real
spec-compliance gap in the module, or a wrong bit position in this
project's Page 01h decoding (see cmis.py's Page 01h section for which
bits are marked as independently confirmed vs. inferred) -- either way,
worth failing loudly rather than silently trusting one source over the
other.

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

import cmis
import cmis_helpers


def test_advertised_pages_match_actual_selectability(bridge, module_info):
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        import pytest
        pytest.skip("module reports Flat Memory model -- Page 01h isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))

    checks = [
        ("page03_user_eeprom_supported", cmis.PAGE_USER_EEPROM),
        ("diagnostic_pages_supported", cmis.PAGE_DIAG_CONTROL),
        ("vdm_pages_supported", cmis.PAGE_VDM_DESCRIPTORS_BASE),
    ]

    mismatches = []
    try:
        for advertised_field, page in checks:
            advertised = advertising[advertised_field]
            actual = cmis_helpers.try_select_page(bridge, bank=0x00, page=page)
            print(f"[cmis-discover] {advertised_field}: advertised={advertised}, "
                  f"page {page:02x}h actually selectable={actual}")
            if advertised != actual:
                mismatches.append((advertised_field, page, advertised, actual))
    finally:
        cmis_helpers.select_page(bridge, bank=0x00, page=0x00)

    assert not mismatches, (
        f"Page 01h advertisement disagreed with actual page selectability for: {mismatches} -- "
        f"either a module spec-compliance gap, or this project's Page 01h bit-position "
        f"decoding (cmis.py's PAGE01_SUPPORTED_PAGES_* constants) is wrong"
    )
