"""CMIS (Common Management Interface Specification) register map and
framing, for a transceiver module's management interface over I2C.

Every fact here is sourced directly from the primary specification
document, fetched and verified 2026-08-27:

    "Common Management Interface Specification (CMIS)", Rev 5.0,
    2021-05-08, QSFP-DD MSA (hosted as a third-party spec by OIF)
    https://www.oiforum.com/wp-content/uploads/CMIS5p0_Third_Party_Spec.pdf

Section/table/page numbers are cited per fact below so anything here
can be directly checked against that document. This project has NO
CMIS-compliant hardware to test against yet (see README) -- so unlike
the sibling openbic-test-environment/mctp-test-environment projects,
nothing here has been live-verified. Treat every byte offset and field
meaning as "correctly transcribed from the spec", not "confirmed
against real silicon", until a real module exists to check it against.

SCOPE NOTE: this revision (5.0) defines I2C as the only management
transport -- grepped the full spec text for "I3C", zero hits. Appendix B
(the transport binding) explicitly states only an I2C-based variant is
described in this revision. I3C support may exist in a later CMIS
revision (5.1/5.2/5.3 were not fetched/verified this session) -- if I3C
is actually needed, that's a real gap to research separately, not
something this module attempts.

Wire-level addressing (Appendix B.2.4.1.4, p.270): a CMIS module is a
plain I2C target at a single, fixed 7-bit address, 0x50 -- unlike
SFF-8472's split 0xA0/0xA2 addressing, CMIS multiplexes everything
through page selection at this one address. There is also no
I2C-address-based way to distinguish multiple CMIS modules sharing a
bus (the I2C-MCI transport binding has no endpoint addressing at all,
per Appendix B.2.1) -- every CMIS module answers at 0x50, and
multi-module systems rely on an external, per-module hardware ModSel
signal instead. This project assumes a single module per bus.
"""

CMIS_I2C_ADDR = 0x50

# --- Memory map structure (Section 8.1.1, 8.2, p.105) --------------------
# Lower Memory: byte addresses 0x00-0x7F, statically interpreted -- the
# same physical register always lives at a given address. Upper Memory:
# byte addresses 0x80-0xFF, DYNAMICALLY interpreted -- content depends on
# the currently-selected page (a genuinely paged model, not SFF-8636's
# flat memory map, though CMIS also supports an explicit Flat Memory mode
# for simpler modules -- see MEMORY_MODEL_BYTE below).
LOWER_MEMORY_SIZE = 0x80
UPPER_MEMORY_SIZE = 0x80
UPPER_MEMORY_BASE = 0x80

# --- Lower Memory fields (Tables 8-3 through 8-9, p.105-109) -------------
SFF8024_IDENTIFIER_BYTE = 0x00
CMIS_REVISION_BYTE = 0x01

# Byte 2: MemoryModel (bit7), SteppedConfigOnly (bit6), MciMaxSpeed (bits3-2)
MODULE_FLAGS_BYTE = 0x02
MEMORY_MODEL_PAGED = 0
MEMORY_MODEL_FLAT = 1

# Byte 3: ModuleState (bits3-1), InterruptDeasserted (bit0)
MODULE_STATE_BYTE = 0x03

# Module State encodings (Table 8-6) -- 3-bit field, bits 3-1 of byte 3.
MODULE_STATE_RESERVED_0 = 0b000
MODULE_STATE_LOW_PWR = 0b001
MODULE_STATE_PWR_UP = 0b010
MODULE_STATE_READY = 0b011  # the only state a Flat Memory module ever reports
MODULE_STATE_PWR_DN = 0b100
MODULE_STATE_FAULT = 0b101
MODULE_STATE_NAMES = {
    MODULE_STATE_RESERVED_0: "Reserved",
    MODULE_STATE_LOW_PWR: "ModuleLowPwr",
    MODULE_STATE_PWR_UP: "ModulePwrUp",
    MODULE_STATE_READY: "ModuleReady",
    MODULE_STATE_PWR_DN: "ModulePwrDn",
    MODULE_STATE_FAULT: "ModuleFault",
}

# Bytes 14-15: TempMonValue, signed 16-bit, 1/256 degC increments (Table 8-9, p.109)
TEMP_MON_BYTES = (0x0E, 0x0F)
# Bytes 16-17: VccMonVoltage, unsigned 16-bit, 100uV increments
VCC_MON_BYTES = (0x10, 0x11)

# Bytes 126-127: PageMapping (Table 8-21, p.119). Both must be written
# together for an arbitrary page/bank change; PageSelect alone may be
# written for a same-bank page change. Confirmed gotcha (Section 8.2.13):
# writing an UNSUPPORTED page number causes the module to silently reset
# PageSelect back to 0x00 -- not an error response -- so always read back
# the page-select bytes after selecting a page rather than assuming the
# write "took".
BANK_SELECT_BYTE = 0x7E
PAGE_SELECT_BYTE = 0x7F

# --- Page 00h (Upper Memory) vendor info block (Tables 8-22/8-24, p.119-120) --
# Byte offsets here are absolute (0x80-0xFF), matching the datasheet
# convention -- subtract UPPER_MEMORY_BASE (0x80) to index into a raw
# 128-byte buffer read starting at address 0x80.
PAGE00_SFF8024_IDENTIFIER_COPY_BYTE = 0x80
PAGE00_VENDOR_NAME = (0x81, 16)
PAGE00_VENDOR_OUI = (0x91, 3)
PAGE00_VENDOR_PN = (0x94, 16)
PAGE00_VENDOR_REV = (0xA4, 2)
PAGE00_VENDOR_SN = (0xA6, 16)
PAGE00_DATE_CODE = (0xB6, 8)
PAGE00_CLEI_CODE = (0xBE, 10)
# Checksum over bytes 0x80-0xDD (128-221) inclusive, stored at 0xDE (222).
PAGE00_CHECKSUM_COVERAGE = (0x80, 0xDE)  # [start, end) -- 94 bytes
PAGE00_CHECKSUM_BYTE = 0xDE

# --- Documented I2C timing gotchas (Section 10.2.2, Table 10-4, p.262) --
# Hold-off periods after specific writes before a read is guaranteed to
# reflect them -- the spec's own recommendation is ACK-polling (its TEST
# primitive) rather than blindly sleeping the max duration, but a simple
# sleep is a reasonable, much simpler starting point for a test harness
# and is what this project's helpers use for now.
T_BPC_MS = 10       # after a PageMapping (page-select) write, before Upper Memory reads are valid
T_WRITE_MS = 10     # after a write to a volatile register, before readback reflects it
T_WRITE_NV_MS = 80  # same, but for non-volatile (persistent) memory writes


def parse_lower_memory(data):
    """Decode a 128-byte Lower Memory read (addresses 0x00-0x7F) into its
    key fields. `data` must be exactly 128 bytes starting at address 0.
    """
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Lower Memory, got {len(data)}")

    byte2 = data[MODULE_FLAGS_BYTE]
    byte3 = data[MODULE_STATE_BYTE]
    temp_raw = (data[TEMP_MON_BYTES[0]] << 8) | data[TEMP_MON_BYTES[1]]
    if temp_raw >= 0x8000:
        temp_raw -= 0x10000  # signed 16-bit
    vcc_raw = (data[VCC_MON_BYTES[0]] << 8) | data[VCC_MON_BYTES[1]]

    return {
        "identifier": data[SFF8024_IDENTIFIER_BYTE],
        "cmis_revision_major": (data[CMIS_REVISION_BYTE] >> 4) & 0xF,
        "cmis_revision_minor": data[CMIS_REVISION_BYTE] & 0xF,
        "memory_model": (byte2 >> 7) & 0x1,
        "stepped_config_only": (byte2 >> 6) & 0x1,
        "mci_max_speed": (byte2 >> 2) & 0x3,
        "module_state": (byte3 >> 1) & 0x7,
        "interrupt_deasserted": byte3 & 0x1,
        "temperature_c": temp_raw / 256.0,
        "vcc_v": vcc_raw * 100e-6,
        "bank_select": data[BANK_SELECT_BYTE],
        "page_select": data[PAGE_SELECT_BYTE],
    }


def _decode_ascii_field(data, offset_length):
    """Extract a right-space-padded ASCII field (the universal SFF/CMIS
    string convention) from a page buffer, stripping trailing padding."""
    offset, length = offset_length
    index = offset - UPPER_MEMORY_BASE
    raw = data[index:index + length]
    return raw.decode("ascii", errors="replace").rstrip(" ")


def parse_page00_vendor_info(data):
    """Decode a 128-byte Page 00h (Upper Memory) read (addresses
    0x80-0xFF) into its vendor identification fields. `data` must be
    exactly 128 bytes starting at address 0x80.
    """
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 00h, got {len(data)}")

    oui_off, oui_len = PAGE00_VENDOR_OUI
    oui_index = oui_off - UPPER_MEMORY_BASE
    vendor_oui = data[oui_index:oui_index + oui_len]

    return {
        "identifier_copy": data[PAGE00_SFF8024_IDENTIFIER_COPY_BYTE - UPPER_MEMORY_BASE],
        "vendor_name": _decode_ascii_field(data, PAGE00_VENDOR_NAME),
        "vendor_oui": vendor_oui,
        "vendor_pn": _decode_ascii_field(data, PAGE00_VENDOR_PN),
        "vendor_rev": _decode_ascii_field(data, PAGE00_VENDOR_REV),
        "vendor_sn": _decode_ascii_field(data, PAGE00_VENDOR_SN),
        "date_code": _decode_ascii_field(data, PAGE00_DATE_CODE),
    }


def verify_page00_checksum(data):
    """Verify Page 00h's checksum byte (offset 0xDE) against a plain
    8-bit sum of bytes 0x80-0xDD.

    NOT independently confirmed against the spec text for the exact
    checksum algorithm (sum vs. sum-then-complement) -- implemented as a
    straightforward 8-bit sum, the conventional algorithm used by
    SFF-8636/SFF-8472's equivalent checksum fields, but this specific
    detail should be treated as a reasonable inference, not a verified
    fact, until checked against real hardware (or the spec's own worked
    example, if one is found). Returns (matches: bool, computed: int,
    stored: int).
    """
    start, end = PAGE00_CHECKSUM_COVERAGE
    start_index = start - UPPER_MEMORY_BASE
    end_index = end - UPPER_MEMORY_BASE
    computed = sum(data[start_index:end_index]) & 0xFF
    stored = data[PAGE00_CHECKSUM_BYTE - UPPER_MEMORY_BASE]
    return computed == stored, computed, stored


def build_page_select(bank, page):
    """Build the 2-byte [bank, page] value to write to BANK_SELECT_BYTE/
    PAGE_SELECT_BYTE (0x7E/0x7F) to select a given bank/page. Both bytes
    should be written together in one transaction for an arbitrary
    page/bank change (Section 8.2.13)."""
    return bytes([bank & 0xFF, page & 0xFF])
