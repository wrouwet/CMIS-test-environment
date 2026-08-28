"""Page 1Ch (Normalized Application Descriptors, CMIS 5.3+): up to 15
Application descriptors per bank, all RO/static.

NOT yet run against real hardware -- see the project README's "Current
status" section. Present (per the spec's own condition) exactly when
Page 01h's nad_banks_supported > 0 -- naturally never true on any module
older than CMIS 5.3 (see cmis.VERSION_HISTORY), since the page doesn't
exist before that revision.
"""

import cmis
import cmis_helpers


def test_page1c_normalized_application_descriptors(bridge, module_info):
    import pytest
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 1Ch isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    nad_banks = advertising["nad_banks_supported"]
    if nad_banks == 0:
        pytest.skip("module does not advertise Page 1Ch (Page 01h byte 175 bits 3-0 = 0) -- "
                    "expected on any CMIS revision below 5.3")

    for bank in range(nad_banks):
        descriptors = cmis_helpers.read_page1c_nad(bridge, bank_index=bank)
        print(f"[cmis-discover] Page 1Ch bank {bank}: {len(descriptors)} descriptors")
        for d in descriptors:
            print(f"[cmis-discover]   AppSel {d['app_sel']} (AN={d['application_number']}): "
                  f"host_if=0x{d['host_interface_id']:02x}, media_if=0x{d['media_interface_id']:02x}, "
                  f"host_lanes={d['host_lane_count']}, media_lanes={d['media_lane_count']}, "
                  f"network_path={d['is_network_path']}")
