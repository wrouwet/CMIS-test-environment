"""Page 19h (Data Path Configuration, CMIS 5.2+): per-lane Tx/Rx
AppSel/DataPathID/ExplicitControl, all RO.

NOT yet run against real hardware -- see the project README's "Current
status" section. No single dedicated advertisement bit was found for
this page in the primary spec text (see cmis.py's Page 19h section) --
gated here on Page 01h's unidir_reconfig_supported bit (byte 162 bit 6),
the specific condition documented for the Tx/Rx config fields this
project decodes, using cmis_helpers.try_select_page() as a second,
independent confirmation.
"""

import pytest

import cmis
import cmis_helpers


def test_page19_datapath_config(bridge, module_info):
    cmis_helpers.require_paged(module_info, "Page 19h")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["unidir_reconfig_supported"]:
        pytest.skip("module does not advertise unidir_reconfig_supported (Page 01h byte 162 bit 6 = 0)")

    took = cmis_helpers.try_select_page(bridge, bank=0x00, page=cmis.PAGE_DATAPATH_CONFIG)
    if not took:
        pytest.skip("Page 19h advertised via byte 162 bit 6 but not actually selectable -- "
                     "either a module spec-compliance gap or this project's advertisement-bit "
                     "reading is wrong")

    config = cmis_helpers.read_page19_datapath_config(bridge)
    for lane in range(1, 9):
        tx, rx = config["tx"][lane], config["rx"][lane]
        print(f"[cmis-discover] lane {lane}: tx={tx}, rx={rx}")
