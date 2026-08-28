"""Page 12h (Tunable Laser Control/Status): per-lane grid spacing,
channel, frequency, and tuning status (Section 8.10/8.11 depending on
revision -- confirmed byte-identical across CMIS 5.0-5.3).

NOT yet run against real hardware -- see the project README's "Current
status" section. Read-only: this project doesn't attempt to actually
retune a live laser (a real, traffic-affecting action) without explicit
opt-in. Skipped for Flat Memory modules and modules that don't advertise
a tunable transmitter (Page 01h byte 155 bit 6).
"""

import pytest

import cmis
import cmis_helpers


def test_page12_tunable_laser_status(bridge, module_info):
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- Page 12h isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["transmitter_tunable"]:
        pytest.skip("module does not advertise a tunable transmitter (Page 01h byte 155 bit 6 = 0)")

    lanes = cmis_helpers.read_page12_tunable_laser(bridge)
    for lane, info in lanes.items():
        print(f"[cmis-discover] lane {lane}: grid={info['grid_spacing']}, "
              f"channel={info['channel_number']}, "
              f"freq={info['current_laser_frequency_ghz']:.3f}GHz, "
              f"target_power={info['target_output_power_dbm']:.2f}dBm, "
              f"tuning_in_progress={info['tuning_in_progress']}, "
              f"wavelength_unlock_status={info['wavelength_unlock_status']}")
        active_flags = [name for name, val in info["flags"].items() if val]
        if active_flags:
            print(f"[cmis-discover]   active flags: {active_flags}")
        assert info["grid_spacing"] != "reserved", (
            f"lane {lane} reported a reserved/undefined GridSpacing encoding -- "
            f"possibly a CMIS revision newer than this project's researched set (5.3)"
        )
