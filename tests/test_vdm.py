"""VDM (Versatile Diagnostic Monitoring, Pages 20h-2Fh): up to 256
monitored "instances" across 4 groups of 64, each optionally bound to an
observable quantity via its descriptor, plus a freeze/unfreeze handshake
for taking a gap-free multi-instance snapshot (Section 8.14).

NOT yet run against real hardware -- see the project README's "Current
status" section. Skipped entirely for Flat Memory modules, and further
skipped if the module doesn't advertise VDM support at all (Page 01h
byte 142 bit 6).
"""

import pytest

import cmis
import cmis_helpers


def _require_vdm(bridge, module_info):
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip("module reports Flat Memory model -- VDM isn't supported (Table 8-4)")

    cmis_helpers.select_page(bridge, bank=0x00, page=cmis.PAGE_ADVERTISING)
    advertising = cmis.parse_page01_advertising(cmis_helpers.read_upper_memory(bridge))
    if not advertising["vdm_pages_supported"]:
        pytest.skip("module does not advertise VDM support (Page 01h byte 142 bit 6 = 0)")


def test_vdm_control_and_active_groups(bridge, module_info):
    """Read Page 2Fh and print how many of the 4 possible VDM groups are
    actually active -- every other VDM test depends on this to know which
    of the 4 descriptor/sample/threshold pages are even meaningful to read."""
    _require_vdm(bridge, module_info)

    control = cmis_helpers.read_vdm_control(bridge)
    print(f"[cmis-discover] VDM control: {control}")
    assert 1 <= control["active_vdm_groups"] <= 4


def test_vdm_descriptors_and_samples(bridge, module_info):
    """For each active VDM group, read its descriptor and sample pages
    and print every USED instance (observable_type != 0) alongside its
    current raw sample value -- the closest thing to a general-purpose
    VDM dump this project can do without a complete Observable Type ->
    Data Type table (see cmis.VDM_OBSERVABLE_TYPE_NAMES's docstring)."""
    _require_vdm(bridge, module_info)

    control = cmis_helpers.read_vdm_control(bridge)
    for group_index in range(control["active_vdm_groups"]):
        group = cmis_helpers.read_vdm_group(bridge, group_index)
        used = [(i, d) for i, d in enumerate(group["descriptors"]) if d["is_used"]]
        print(f"[cmis-discover] VDM group {group_index + 1}: {len(used)} of 64 instances in use")
        for instance_index, descriptor in used:
            sample = group["samples"][instance_index]
            value, unit = cmis.interpret_vdm_sample(sample, descriptor["observable_type"])
            if value is not None:
                print(
                    f"[cmis-discover]   instance {instance_index + 1}: "
                    f"{descriptor['observable_type_name']} = {value:g} {unit or ''} "
                    f"(resource={descriptor['monitored_resource']})"
                )
            else:
                print(
                    f"[cmis-discover]   instance {instance_index + 1}: "
                    f"{descriptor['observable_type_name']}, resource={descriptor['monitored_resource']}, "
                    f"raw_sample=0x{sample:04x} ({sample}) -- not decodable (uncatalogued observable type)"
                )


def test_vdm_freeze_unfreeze_handshake(bridge, module_info):
    """Exercise the freeze/unfreeze handshake itself (Page 2Fh byte 144
    FreezeRequest, byte 145 FreezeDone/UnfreezeDone) -- this is a
    real command/response round trip worth testing on its own, separate
    from whether any particular observable is populated. Always cleans
    up by unfreezing even if an assertion fails partway through."""
    _require_vdm(bridge, module_info)

    try:
        froze = cmis_helpers.vdm_freeze(bridge)
        print(f"[cmis-discover] VDM freeze handshake: FreezeDone observed={froze}")
        assert froze, "module never asserted FreezeDone after FreezeRequest"
    finally:
        unfroze = cmis_helpers.vdm_unfreeze(bridge)
        print(f"[cmis-discover] VDM unfreeze handshake: UnfreezeDone observed={unfroze}")
        assert unfroze, "module never asserted UnfreezeDone after clearing FreezeRequest"
