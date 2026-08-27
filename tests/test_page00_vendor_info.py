"""Page 00h (Upper Memory): vendor identification block.

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

import cmis
import cmis_helpers


def test_page00_vendor_info_and_checksum(bridge):
    """Select page 00h, read the vendor identification block, and
    verify it against the page's own checksum byte -- printing the
    decoded fields for visibility rather than asserting specific vendor
    strings, since this project doesn't know in advance which
    transceiver it will be run against.
    """
    cmis_helpers.select_page(bridge, bank=0x00, page=0x00)

    # Confirmed gotcha (Section 8.2.13): an unsupported page write
    # silently resets PageSelect back to 0x00 instead of erroring -- read
    # Lower Memory back to confirm the selection actually took, rather
    # than assuming the write succeeded just because it didn't NAK.
    lower = cmis_helpers.read_lower_memory(bridge)
    decoded_lower = cmis.parse_lower_memory(lower)
    assert decoded_lower["page_select"] == 0x00, (
        f"expected page_select to read back as 0x00 after selecting it, got "
        f"0x{decoded_lower['page_select']:02x} -- page selection may not be working "
        f"as documented"
    )

    upper = cmis_helpers.read_upper_memory(bridge)
    decoded = cmis.parse_page00_vendor_info(upper)
    print(f"decoded vendor info: {decoded}")

    matches, computed, stored = cmis.verify_page00_checksum(upper)
    print(f"page checksum: computed=0x{computed:02x} stored=0x{stored:02x} match={matches}")
    assert matches, (
        f"Page 00h checksum mismatch (computed 0x{computed:02x}, stored 0x{stored:02x}) -- "
        f"either a real data-integrity problem, or this project's checksum ALGORITHM "
        f"assumption (plain 8-bit sum, not independently confirmed against the spec "
        f"text -- see cmis.verify_page00_checksum()'s docstring) is wrong"
    )
