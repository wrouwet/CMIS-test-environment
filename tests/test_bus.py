"""Foundational test: is the CMIS module present on the bus at all.

NOT yet run against real hardware -- see the project README's "Current
status" section.
"""

from config import MODULE_ADDR


def test_detect_cmis_module(bridge):
    """The CMIS module should respond on the I2C bus at its fixed
    address (0x50, confirmed against the spec -- see cmis.py). Note:
    per cmis.py's module docstring, CMIS has no I2C-address-based way to
    distinguish multiple modules on a shared bus -- this test (and this
    whole project) assumes a single module per bus.
    """
    addrs = bridge.scan()
    print(f"bus scan found: {[hex(a) for a in addrs]}")
    assert MODULE_ADDR in addrs, (
        f"CMIS module not found at 0x{MODULE_ADDR:02x}; devices found: {[hex(a) for a in addrs]}"
    )
