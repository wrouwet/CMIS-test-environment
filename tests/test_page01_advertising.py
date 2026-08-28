"""Page 01h (Advertising): capability advertisement, including whether
CDB (firmware update) is supported at all.

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules, which per
Table 8-4 only ever support Page 00h.
"""

import cmis
import cmis_helpers


def _require_paged(module_info):
    cmis_helpers.require_paged(module_info, "Page 01h")


def test_page01_advertising_and_checksum(bridge, module_info):
    """Select Page 01h, read it, and verify it against its own checksum
    (byte 0xFF, covering 0x82-0xFE -- deliberately NOT the same coverage
    as Page 00h's checksum, see cmis.PAGE01_CHECKSUM_COVERAGE)."""
    _require_paged(module_info)

    took = cmis_helpers.try_select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    assert took, (
        "Page 01h is mandatory for any Paged-memory module (Table 8-4) but did not "
        "read back as selected -- either a spec-compliance gap in this module, or a "
        "problem with this project's page-select plumbing"
    )
    data = cmis_helpers.read_upper_memory(bridge)

    decoded = cmis.parse_page01_advertising(data)
    print(f"decoded Page 01h: {decoded}")

    matches, computed, stored = cmis.verify_page01_checksum(data)
    print(f"page01 checksum: computed=0x{computed:02x} stored=0x{stored:02x} match={matches}")
    assert matches, (
        f"Page 01h checksum mismatch (computed 0x{computed:02x}, stored 0x{stored:02x})"
    )


def test_cdb_capability_advertisement(bridge, module_info):
    """Print (don't assert on) whether the module advertises CDB support
    at all -- CdbInstancesSupported=0 is a perfectly valid, common answer
    (CDB/firmware-update is optional), so this is discovery, not a
    pass/fail check. Tests that actually exercise CDB commands should
    gate on this rather than assuming CDB exists."""
    _require_paged(module_info)

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    data = cmis_helpers.read_upper_memory(bridge)
    decoded = cmis.parse_page01_advertising(data)

    if decoded["cdb_instances_supported"] == 0:
        print("[cmis-discover] CDB: not supported by this module (CdbInstancesSupported=0)")
    else:
        print(
            f"[cmis-discover] CDB: {decoded['cdb_instances_supported']} instance(s), "
            f"background_mode={decoded['cdb_background_mode_supported']}, "
            f"auto_paging={decoded['cdb_auto_paging_supported']}, "
            f"max_epl_pages_field={decoded['cdb_max_pages_epl']}"
        )
