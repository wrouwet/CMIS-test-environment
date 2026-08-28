"""Lower Memory (addresses 0x00-0x7F): identification, module state,
environmental monitors.

NOT yet run against real hardware -- see the project README's "Current
status" section. Assertions are deliberately structural (right length,
plausible ranges, defined enum values) rather than asserting specific
vendor-dependent values like an exact Identifier byte, since this
project doesn't know in advance which transceiver it will actually be
run against.

Consumes the session-scoped `module_info` fixture (see conftest.py /
cmis_helpers.discover_module()) rather than re-reading Lower Memory
itself -- discovery already did that read once per session, and the
decoded dict has everything these tests need.
"""

import cmis


def test_read_identifier_and_revision(module_info):
    """Confirm the Identifier and CMIS Revision bytes (Tables 8-3/8-4,
    offsets 0x00/0x01) decoded to something plausible."""
    print(f"CMIS revision: {module_info['cmis_revision_major']}.{module_info['cmis_revision_minor']}")
    assert module_info["identifier"] != 0x00, "Identifier byte is 0x00 -- likely not a real CMIS module"


def test_read_module_state(module_info):
    """Confirm the Module State field (byte 3, bits 3-1) is one of the
    defined states (Table 8-6) -- not one of the reserved encodings,
    which would indicate either a non-CMIS device or a genuine module
    fault worth investigating."""
    state = module_info["module_state"]
    name = cmis.MODULE_STATE_NAMES.get(state)
    print(f"module_state: {state:03b}b ({name})")
    assert name is not None, f"module reported an undefined module_state encoding ({state:03b}b)"
    assert name != "Reserved", "module reported the explicitly-reserved 000b module_state"


def test_read_environmental_monitors(module_info):
    """Confirm the temperature and VCC monitors (bytes 14-15, 16-17) are
    at least in a physically plausible range -- this can't validate
    correctness (that needs a known reference), just catch obviously-wrong
    decoding (e.g. a sign error, or reading the wrong bytes entirely)."""
    temp_c = module_info["temperature_c"]
    vcc_v = module_info["vcc_v"]
    print(f"temperature: {temp_c:.2f} C, VCC: {vcc_v:.3f} V")
    assert -40.0 <= temp_c <= 125.0, (
        f"temperature {temp_c:.2f} C is outside any plausible transceiver "
        f"operating range -- likely a decoding bug, not a real reading"
    )
    assert 0.0 <= vcc_v <= 5.0, (
        f"VCC {vcc_v:.3f} V is outside any plausible supply range -- "
        f"likely a decoding bug, not a real reading"
    )


def test_read_module_flags_and_cdb_status(module_info):
    """Print the remaining Lower Memory flags this project decodes but
    doesn't have a dedicated test for: MciMaxSpeed/SteppedConfigOnly
    (byte 2), InterruptDeasserted (byte 3), and both CDB instances'
    complete-flag + status (bytes 8/37/38, Table 8-13) -- visibility
    only, since none of these have a single "correct" value independent
    of the specific module and what it's currently doing."""
    print(f"stepped_config_only: {module_info['stepped_config_only']}")
    print(f"mci_max_speed: {module_info['mci_max_speed']:02b}b")
    print(f"interrupt_deasserted: {module_info['interrupt_deasserted']}")
    print(f"cdb_cmd_complete_1: {module_info['cdb_cmd_complete_1']}, "
          f"cdb_status_1: {module_info['cdb_status_1']}")
    print(f"cdb_cmd_complete_2: {module_info['cdb_cmd_complete_2']}, "
          f"cdb_status_2: {module_info['cdb_status_2']}")
