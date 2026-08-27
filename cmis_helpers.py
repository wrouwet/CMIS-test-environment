"""Shared plumbing for CMIS register-level reads/writes and page
selection.

CMIS modules are plain I2C targets with a conventional "write register
offset, then read N bytes" access pattern -- unlike the sibling IPMB/
MCTP projects, there's no bus-mastership swap, no PEC, no fragmentation
at this layer. bridge.write_read() (the "X" bridge command: write bytes,
repeated-start, then read) maps directly onto this.
"""

import time

import cmis


def read_lower_memory(bridge):
    """Read the full 128-byte Lower Memory (addresses 0x00-0x7F) and
    return it as raw bytes, ready for cmis.parse_lower_memory()."""
    return bridge.write_read(cmis.CMIS_I2C_ADDR, [0x00], cmis.LOWER_MEMORY_SIZE)


def read_upper_memory(bridge):
    """Read the full 128 bytes of whichever page is currently selected
    (addresses 0x80-0xFF) and return it as raw bytes."""
    return bridge.write_read(cmis.CMIS_I2C_ADDR, [cmis.UPPER_MEMORY_BASE], cmis.UPPER_MEMORY_SIZE)


def select_page(bridge, bank, page, settle=True):
    """Select a bank/page by writing both PageMapping bytes together
    (Section 8.2.13), then wait out the documented tBPC hold-off before
    Upper Memory reads are guaranteed valid (a plain sleep for now --
    the spec's own recommendation is ACK-polling via its TEST primitive,
    a possible future improvement, not implemented here).

    Confirmed gotcha from the spec: writing an unsupported page number
    silently resets PageSelect back to 0x00 rather than erroring -- read
    back Lower Memory's page_select field after calling this if you need
    to confirm the selection actually took (see
    test_page00_vendor_info.py for exactly this check).
    """
    payload = [cmis.BANK_SELECT_BYTE] + list(cmis.build_page_select(bank, page))
    bridge.write(cmis.CMIS_I2C_ADDR, payload)
    if settle:
        time.sleep(cmis.T_BPC_MS / 1000.0)
