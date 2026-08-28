"""A fully generic, structure-agnostic sweep of the whole CMIS page-number
space (Upper Memory bank 0), using nothing but the confirmed page-select
readback gotcha (Section 8.2.13) to determine which pages a real module
actually implements -- no assumption about a given page's CONTENT, only
whether selecting it "takes." This is deliberately the most black-box
test in this project: it needs no advance knowledge of what a page means
to still produce a useful, real finding (exactly which of the documented
page numbers this specific module supports), and for any page this
project doesn't have a dedicated decoder for yet, it dumps the raw hex so
a future cmis.py addition has real data to be written against.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules, which per
Table 8-4 only ever implement Page 00h (there is nothing left to sweep).
"""

import pytest

import cmis
import cmis_helpers

# Every page number named anywhere in cmis.py's citations, across the
# whole researched 4.0-5.3 lineage -- deliberately includes pages this
# project can't decode yet (05h, 12h-14h, 16h-19h, 1Ch) precisely so this
# sweep is useful for finding out whether they even exist on a given
# module before investing in decoding them.
KNOWN_OPTIONAL_PAGES = {
    0x01: "Advertising",
    0x02: "Thresholds",
    0x03: "User EEPROM",
    0x04: "unconfirmed -- not found as a distinct page in Rev 5.0 research",
    0x05: "form-factor-specific (5.2+)",
    0x10: "Lane Control",
    0x11: "Lane Status",
    0x12: "Tunable Laser Control/Status",
    0x13: "Module Performance Diagnostics Control",
    0x14: "Module Performance Diagnostics Results",
    0x15: "Timing Characteristics",
    0x16: "Network Path (5.1+)",
    0x17: "Flags/Masks (5.1+)",
    0x18: "lane-specific controls (5.2+)",
    0x19: "lane-specific status (5.2+)",
    0x1C: "240-Application expansion (5.3+)",
    0x9F: "CDB Message",
}

# Pages with a dedicated decoder elsewhere in this project -- reported as
# "selectable" here for completeness, but NOT hex-dumped again (their own
# test file already does that meaningfully).
DECODED_ELSEWHERE = {0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x15, 0x9F}


def test_enumerate_known_optional_pages(bridge, module_info):
    """Try selecting every page number this project has ever cited from
    the spec (see KNOWN_OPTIONAL_PAGES) and report which ones actually
    exist on this module. Always leaves the module back on Page 00h."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- only Page 00h exists (Table 8-4)")

    found = {}
    try:
        for page, description in sorted(KNOWN_OPTIONAL_PAGES.items()):
            took = cmis_helpers.try_select_page(bridge, bank=0x00, page=page)
            found[page] = took
            status = "PRESENT" if took else "not present"
            print(f"[cmis-discover] Page {page:02x}h ({description}): {status}")
            if took and page not in DECODED_ELSEWHERE:
                data = cmis_helpers.read_upper_memory(bridge)
                print(f"[cmis-discover]   raw dump: {data.hex()}")
    finally:
        cmis_helpers.select_page(bridge, bank=0x00, page=0x00)

    print(f"[cmis-discover] summary: {sum(found.values())} of {len(found)} known optional "
          f"pages present on this module")
