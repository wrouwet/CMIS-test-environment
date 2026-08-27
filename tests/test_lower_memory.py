"""Lower Memory (addresses 0x00-0x7F): identification, module state,
environmental monitors.

NOT yet run against real hardware -- see the project README's "Current
status" section. Assertions are deliberately structural (right length,
plausible ranges, defined enum values) rather than asserting specific
vendor-dependent values like an exact Identifier byte, since this
project doesn't know in advance which transceiver it will actually be
run against.
"""

import cmis
import cmis_helpers


def test_read_identifier_and_revision(bridge):
    """Read Lower Memory and decode the Identifier and CMIS Revision
    bytes (Tables 8-3/8-4, offsets 0x00/0x01)."""
    data = cmis_helpers.read_lower_memory(bridge)
    decoded = cmis.parse_lower_memory(data)
    print(f"decoded: {decoded}")
    print(f"CMIS revision: {decoded['cmis_revision_major']}.{decoded['cmis_revision_minor']}")
    assert decoded["identifier"] != 0x00, "Identifier byte is 0x00 -- likely not a real CMIS module"


def test_read_module_state(bridge):
    """Read the Module State field (byte 3, bits 3-1) and confirm it's
    one of the defined states (Table 8-6) -- not one of the reserved
    encodings, which would indicate either a non-CMIS device or a
    genuine module fault worth investigating."""
    data = cmis_helpers.read_lower_memory(bridge)
    decoded = cmis.parse_lower_memory(data)
    state = decoded["module_state"]
    name = cmis.MODULE_STATE_NAMES.get(state)
    print(f"module_state: {state:03b}b ({name})")
    assert name is not None, f"module reported an undefined module_state encoding ({state:03b}b)"
    assert name != "Reserved", "module reported the explicitly-reserved 000b module_state"


def test_read_environmental_monitors(bridge):
    """Read the temperature and VCC monitors (bytes 14-15, 16-17) and
    confirm they're at least in a physically plausible range -- this
    can't validate correctness (that needs a known reference), just
    catch obviously-wrong decoding (e.g. a sign error, or reading the
    wrong bytes entirely)."""
    data = cmis_helpers.read_lower_memory(bridge)
    decoded = cmis.parse_lower_memory(data)
    print(f"temperature: {decoded['temperature_c']:.2f} C, VCC: {decoded['vcc_v']:.3f} V")
    assert -40.0 <= decoded["temperature_c"] <= 125.0, (
        f"temperature {decoded['temperature_c']:.2f} C is outside any plausible "
        f"transceiver operating range -- likely a decoding bug, not a real reading"
    )
    assert 0.0 <= decoded["vcc_v"] <= 5.0, (
        f"VCC {decoded['vcc_v']:.3f} V is outside any plausible supply range -- "
        f"likely a decoding bug, not a real reading"
    )
