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

SCOPE NOTE, now confirmed across the whole 4.0-5.3 lineage (each fetched
and grepped independently): I3C is NEVER adopted as a CMIS management
transport, in any revision through 5.3. I2C ("I2CMCI") is the original
and, through 5.2, only transport. Revision 5.3 (OIF-CMIS-05.3,
2024-09-04) adds a SECOND transport, but it's SPI ("SPIMCI", Appendix
B.3, for co-packaged-optics use cases) -- not I3C. SPIMCI uses a
dedicated per-module chip-select wire rather than bus addressing at all
(the opposite of I3C's dynamic-address model), so nothing about it
changes this project's "single module, fixed address" assumptions for
I2C. This project remains I2C-only.

VERSION LINEAGE (see VERSION_HISTORY below for the per-revision
one-liners this drives cmis_helpers.discover_module()'s printed notes):
CMIS revisions 3.0/4.0/5.0/5.1 were QSFP-DD MSA documents merely hosted
by OIF as a third-party spec; starting at 5.2, OIF itself became the
publisher (formal Implementation Agreement numbering, "OIF-CMIS-05.x").
The spec's own Appendix G compatibility rule (added at 5.0): revisions
sharing a major number are backward-compatible (a host built for 5.0 can
talk to a 5.1/5.2/5.3 module; the reverse -- an older host, newer
mandatory feature -- is the actual risk, not register-map breakage).
The ONE real breaking change in the whole lineage is 4.0->5.0 (different
major numbers) -- the 5.0 spec explicitly warns a 5.0 module "may or may
not interoperate" with a 4.0-built host. Everything this project
currently decodes (Lower Memory layout, Page 00h, and the newly-added
Pages 01h/02h/10h/11h, the password mechanism, and CDB framing) was
independently confirmed byte-identical in both the 4.0 and 5.3 documents,
so none of it is expected to need version-conditional decoding logic --
the discovery architecture's job is mainly to tell a NEWER-major module
apart from what this suite was validated against, and to skip pages a
given revision/model simply doesn't advertise, not to run different math
per version.

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

# --- Version lineage (per-revision one-liners, confirmed 2026-08-27) -----
# Keyed by (major, minor) as decoded from CMIS_REVISION_BYTE. Used only for
# printing a human a bit of context in cmis_helpers.discover_module() --
# not used for any conditional decoding logic (see module docstring: the
# register map covered by this project has been confirmed identical across
# the whole 4.0-5.3 lineage).
VERSION_HISTORY = {
    (4, 0): "QSFP-DD MSA, 2019-05-08 -- adds CDB (pages 9Fh/A0h-AFh); "
            "spec warns 4.0 does NOT interoperate with 3.0.",
    (5, 0): "QSFP-DD MSA (OIF-hosted), 2021-05-08 -- major consolidation; "
            "spec warns a 5.0 module may not interoperate with a 4.0 host "
            "(the one breaking change in the whole 4.0-5.3 lineage).",
    (5, 1): "QSFP-DD MSA (OIF-hosted), 2021-11-02 -- adds Network/Host Path "
            "(page 16h) for multiplex media; 5.0 modules are 5.1-compliant.",
    (5, 2): "OIF-CMIS-05.2, 2022-04 -- first OIF-authored revision; adds "
            "unidirectional Data Path, page 05h, pages 18h/19h; "
            "5.1-compliant implementations are 5.2-compliant.",
    (5, 3): "OIF-CMIS-05.3, 2024-09-04 -- adds SPIMCI (Appendix B.3, NOT "
            "I3C), CPO support, page 1Ch (240-Application expansion); "
            "5.2-compliant implementations are 5.3-compliant.",
}

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

# --- CDB status (Section 8.2.8, Table 8-13, p.113) ------------------------
# CdbCmdCompleteFlag and CdbStatus live in LOWER MEMORY, not Page 9Fh --
# easy to miss since everything else about CDB lives on Page 9Fh/A0h-AFh.
# Two independent CDB "instances" are supported by the spec (Page 01h's
# CdbInstancesSupported can be 1 or 2); this project only ever drives
# instance 1 (cmis_helpers.send_cdb_command()), so only instance-1 fields
# are named here -- instance 2's exist at the same bit/byte pattern one
# position over (bit 7 instead of bit 6 on byte 8; byte 38 instead of 37).
CDB_CMD_COMPLETE_FLAG_BYTE = 0x08   # byte 8: bit 6 = instance 1, bit 7 = instance 2 (RO/COR)
CDB_STATUS_1_BYTE = 0x25            # byte 37 (RO)
CDB_STATUS_2_BYTE = 0x26            # byte 38 (RO)

# CdbStatus byte layout (Table 8-13): bit7=CdbIsBusy, bit6=CdbHasFailed,
# bits5-0=CdbCommandResult (meaning depends on bits 7-6).
CDB_RESULT_IN_PROGRESS_CAPTURED = 0x01
CDB_RESULT_IN_PROGRESS_CHECKING = 0x02
CDB_RESULT_IN_PROGRESS_EXECUTING = 0x03
CDB_RESULT_IN_PROGRESS_NAMES = {
    0x01: "captured, not yet processed",
    0x02: "command checking in progress",
    0x03: "command execution in progress",
}
CDB_RESULT_SUCCESS_COMPLETED = 0x01
CDB_RESULT_SUCCESS_ABORTED = 0x03
CDB_RESULT_SUCCESS_NAMES = {
    0x01: "completed successfully",
    0x03: "previous command was ABORTED by CMD Abort",
}
CDB_RESULT_FAILED_UNKNOWN_CMDID = 0x01
CDB_RESULT_FAILED_PARAMETER_RANGE = 0x02
CDB_RESULT_FAILED_ABORT_INCOMPLETE = 0x03
CDB_RESULT_FAILED_CHECK_TIMEOUT = 0x04
CDB_RESULT_FAILED_CHECKSUM_ERROR = 0x05
CDB_RESULT_FAILED_PASSWORD_ERROR = 0x06
CDB_RESULT_FAILED_INCOMPATIBLE_STATE = 0x07
CDB_RESULT_FAILED_NAMES = {
    0x01: "CMDID unknown",
    0x02: "parameter range error or parameter not supported",
    0x03: "previous command was not properly ABORTED",
    0x04: "command checking time out",
    0x05: "CdbChkCode error",
    0x06: "password-related error",
    0x07: "command not compatible with operating status",
}


def decode_cdb_status(raw_byte):
    """Decode one CdbStatus byte (Lower Memory 0x25/0x26) per Table 8-13.
    Returns a dict with the coarse state (busy/success/failed) and, where
    known, a human-readable meaning for the 6-bit result code -- an
    unrecognized code is reported as such rather than guessed at (the
    spec reserves most of the code space, and 0x30-0x3F is explicitly
    vendor-Custom in every state)."""
    busy = bool((raw_byte >> 7) & 0x1)
    failed = bool((raw_byte >> 6) & 0x1)
    result = raw_byte & 0x3F

    if busy:
        state = "in_progress"
        names = CDB_RESULT_IN_PROGRESS_NAMES
    elif failed:
        state = "failed"
        names = CDB_RESULT_FAILED_NAMES
    else:
        state = "success"
        names = CDB_RESULT_SUCCESS_NAMES

    if 0x30 <= result <= 0x3F:
        meaning = "vendor-custom result code"
    else:
        meaning = names.get(result, "reserved/undefined result code")

    return {"busy": busy, "failed": failed, "result_code": result, "state": state, "meaning": meaning}

# --- Password mechanism (Section 8.2.12, p.117-118) -----------------------
# Two INDEPENDENT ways to unlock/change password-protected features exist:
# this direct register-write mechanism, and a CDB-command mechanism (CDB
# command IDs CDB_CMD_ENTER_PASSWORD/CDB_CMD_CHANGE_PASSWORD below). A given
# module may implement only one -- worth trying both if one doesn't work.
# Both bytes ranges are WO/self-clearing, big-endian 32-bit.
PASSWORD_CHANGE_ENTRY_AREA = (0x76, 4)  # bytes 118-121: write new password here
PASSWORD_ENTRY_AREA = (0x7A, 4)         # bytes 122-125: write current password here to unlock
# Host Password range (host-changeable, factory default per spec is
# 0x00001011) vs. Module Password range (vendor-defined default, NOT
# host-changeable -- writing here via PASSWORD_CHANGE_ENTRY_AREA fails).
HOST_PASSWORD_MAX = 0x7FFFFFFF
MODULE_PASSWORD_MIN = 0x80000000
DEFAULT_HOST_PASSWORD = 0x00001011

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
    cdb_complete_byte = data[CDB_CMD_COMPLETE_FLAG_BYTE]

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
        "cdb_cmd_complete_1": bool((cdb_complete_byte >> 6) & 0x1),
        "cdb_cmd_complete_2": bool((cdb_complete_byte >> 7) & 0x1),
        "cdb_status_1": decode_cdb_status(data[CDB_STATUS_1_BYTE]),
        "cdb_status_2": decode_cdb_status(data[CDB_STATUS_2_BYTE]),
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


def build_password_write(password):
    """Encode a 32-bit password as the 4 big-endian bytes the spec's
    PasswordEntryArea/PasswordChangeEntryArea fields expect."""
    return bytes([(password >> 24) & 0xFF, (password >> 16) & 0xFF,
                  (password >> 8) & 0xFF, password & 0xFF])


# --- Page numbers (named, so callers/tests read as intent, not hex) ------
# Advertised-optional pages (see PAGE01_SUPPORTED_PAGES_BYTE below) --
# whether a given page actually exists on a module should be confirmed via
# that advertisement, not assumed from this list alone.
PAGE_ADVERTISING = 0x01
PAGE_THRESHOLDS = 0x02
PAGE_USER_EEPROM = 0x03
PAGE_LANE_CONTROL = 0x10       # banked; "Data Path Control" in some doc revisions
PAGE_LANE_STATUS = 0x11        # banked; "Data Path Status"
PAGE_TUNABLE_LASER = 0x12      # banked
PAGE_DIAG_CONTROL = 0x13       # banked
PAGE_DIAG_RESULTS = 0x14       # banked
PAGE_TIMING_CHARACTERISTICS = 0x15  # banked
PAGE_USER_EEPROM_MAX_WRITE_BYTES = 8  # Section 8.6: max bytes per write to Page 03h
PAGE_VDM_DESCRIPTORS_BASE = 0x20    # 0x20-0x23, one per VDM group (1-4)
PAGE_VDM_SAMPLES_BASE = 0x24        # 0x24-0x27
PAGE_VDM_THRESHOLDS_BASE = 0x28     # 0x28-0x2B
PAGE_VDM_FLAGS = 0x2C
PAGE_VDM_MASKS = 0x2D
PAGE_VDM_CONTROL = 0x2F
PAGE_CDB_MESSAGE = 0x9F
PAGE_CDB_EPL_BASE = 0xA0             # 0xA0-0xAF, 16 x 128-byte EPL segments


# --- Page 01h: Advertising (Section 8.4, Tables 8-36/8-37/8-48, p.126) ---
# All fields here are RO/static. Mandatory for any paged (non-Flat-Memory)
# module, per Table 8-4.
PAGE01_INACTIVE_FW_REV = (0x80, 2)   # bytes 128-129: major, minor
PAGE01_INACTIVE_HW_REV = (0x82, 2)   # bytes 130-131: major, minor

# Byte 142 (Table 8-40 "Supported Pages Advertising") -- confirmed bit-by-bit:
PAGE01_SUPPORTED_PAGES_BYTE = 0x8E
PAGE01_SUPPORTED_PAGES_VDM_BIT = 6        # Pages 20h-2Fh (partially) supported
PAGE01_SUPPORTED_PAGES_DIAG_BIT = 5       # banked Pages 13h/14h supported
PAGE01_SUPPORTED_PAGES_PAGE03_BIT = 2     # Page 03h (User EEPROM) supported
PAGE01_SUPPORTED_PAGES_BANKS_MASK = 0x3   # bits 1-0: BanksSupported
BANKS_SUPPORTED_NAMES = {
    0b00: "Bank 0 only (8 lanes)",
    0b01: "Banks 0-1 (16 lanes)",
    0b10: "Banks 0-3 (32 lanes)",
    0b11: "Reserved",
}

# Byte 145 (Table 8-43 "Module Characteristics Advertising") -- confirmed
# bit-by-bit (only the bits this project currently surfaces are named):
PAGE01_MODULE_CHARACTERISTICS_BYTE = 0x91
PAGE01_MODCHAR_COOLING_IMPLEMENTED_BIT = 7
PAGE01_MODCHAR_EPPS_SUPPORTED_BIT = 4
PAGE01_MODCHAR_TIMING_PAGE15H_SUPPORTED_BIT = 3

# Byte 155 (Table 8-44 "Supported Controls Advertisement") -- confirmed
# bit-by-bit (only the bits this project currently surfaces are named):
PAGE01_SUPPORTED_CONTROLS_BYTE = 0x9B
PAGE01_SUPCTL_WAVELENGTH_CONTROLLABLE_BIT = 7
PAGE01_SUPCTL_TRANSMITTER_TUNABLE_BIT = 6  # 1 => Pages 04h and 12h supported

PAGE01_CDB_FUNCTIONALITY = (0xA3, 4)  # bytes 163-166 (Table 8-48)
# Checksum coverage is DELIBERATELY DIFFERENT from Page 00h's: it excludes
# bytes 128-129 (InactiveFirmwareRevision), "to avoid requiring a Memory
# Map update when firmware is updated" (Table 8-36 note). Do not reuse
# PAGE00_CHECKSUM_COVERAGE's math here -- the start offset differs.
PAGE01_CHECKSUM_COVERAGE = (0x82, 0xFF)  # [start, end) -- bytes 130-254
PAGE01_CHECKSUM_BYTE = 0xFF


def parse_page01_advertising(data):
    """Decode a 128-byte Page 01h read (addresses 0x80-0xFF). `data` must
    be exactly 128 bytes starting at address 0x80.

    Only decodes the fields this project currently has a use for (CDB
    capability advertisement, which pages exist, inactive-image versions)
    -- Page 01h also carries fiber-length/wavelength/module-characteristic
    advertising (bytes 132-190+) not yet decoded here; add fields as tests
    need them rather than decoding the whole page speculatively.
    """
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 01h, got {len(data)}")

    def _u8(offset):
        return data[offset - UPPER_MEMORY_BASE]

    cdb_off, _ = PAGE01_CDB_FUNCTIONALITY
    cdb0 = _u8(cdb_off)
    supported_pages = _u8(PAGE01_SUPPORTED_PAGES_BYTE)
    modchar = _u8(PAGE01_MODULE_CHARACTERISTICS_BYTE)
    supctl = _u8(PAGE01_SUPPORTED_CONTROLS_BYTE)

    return {
        "inactive_fw_rev": (_u8(PAGE01_INACTIVE_FW_REV[0]), _u8(PAGE01_INACTIVE_FW_REV[0] + 1)),
        "inactive_hw_rev": (_u8(PAGE01_INACTIVE_HW_REV[0]), _u8(PAGE01_INACTIVE_HW_REV[0] + 1)),
        "supported_pages_byte": supported_pages,
        "vdm_pages_supported": bool((supported_pages >> PAGE01_SUPPORTED_PAGES_VDM_BIT) & 0x1),
        "diagnostic_pages_supported": bool((supported_pages >> PAGE01_SUPPORTED_PAGES_DIAG_BIT) & 0x1),
        "page03_user_eeprom_supported": bool((supported_pages >> PAGE01_SUPPORTED_PAGES_PAGE03_BIT) & 0x1),
        "banks_supported": supported_pages & PAGE01_SUPPORTED_PAGES_BANKS_MASK,
        "cooling_implemented": bool((modchar >> PAGE01_MODCHAR_COOLING_IMPLEMENTED_BIT) & 0x1),
        "epps_supported": bool((modchar >> PAGE01_MODCHAR_EPPS_SUPPORTED_BIT) & 0x1),
        "timing_page15h_supported": bool((modchar >> PAGE01_MODCHAR_TIMING_PAGE15H_SUPPORTED_BIT) & 0x1),
        "wavelength_controllable": bool((supctl >> PAGE01_SUPCTL_WAVELENGTH_CONTROLLABLE_BIT) & 0x1),
        "transmitter_tunable": bool((supctl >> PAGE01_SUPCTL_TRANSMITTER_TUNABLE_BIT) & 0x1),
        "cdb_instances_supported": (cdb0 >> 6) & 0x3,
        "cdb_background_mode_supported": bool((cdb0 >> 5) & 0x1),
        "cdb_auto_paging_supported": bool((cdb0 >> 4) & 0x1),
        "cdb_max_pages_epl": cdb0 & 0xF,
    }


def verify_page01_checksum(data):
    """Verify Page 01h's checksum (offset 0xFF) against a sum of bytes
    0x82-0xFE -- NOTE the different coverage vs. Page 00h (see
    PAGE01_CHECKSUM_COVERAGE's comment). Returns (matches, computed, stored)."""
    start, end = PAGE01_CHECKSUM_COVERAGE
    start_index = start - UPPER_MEMORY_BASE
    end_index = end - UPPER_MEMORY_BASE
    computed = sum(data[start_index:end_index]) & 0xFF
    stored = data[PAGE01_CHECKSUM_BYTE - UPPER_MEMORY_BASE]
    return computed == stored, computed, stored


# --- Page 02h: Module & Lane Thresholds (Section 8.5, Tables 8-53/8-54, p.138) --
# All RO/static. Mandatory for paged modules. Each threshold "quad" is 4
# consecutive big-endian 16-bit values in the fixed order High Alarm, Low
# Alarm, High Warning, Low Warning (8 bytes per monitored quantity).
PAGE02_TEMP_THRESHOLDS = 0x80    # signed, 1/256 degC
PAGE02_VCC_THRESHOLDS = 0x88     # unsigned, 100uV
# Aux1/Aux2/Aux3 (signed -- meaning is TEC current OR laser temperature
# depending on module configuration, per Table 8-54; this project doesn't
# know which for a given module, so these are decoded as raw signed
# values with no fixed physical unit assigned) and Custom (module-vendor-
# defined, decoded as raw signed here too). Offsets are an INFERENCE from
# the sequential 8-bytes-per-quantity stride established by Temp/VCC
# (0x80, 0x88, ...) landing exactly on the lane-specific range's start
# (0xB0/176) after 6 quantities x 8 bytes = 48 bytes (128-175) -- not an
# independently re-confirmed byte-offset table for these specific three.
PAGE02_AUX1_THRESHOLDS = 0x90
PAGE02_AUX2_THRESHOLDS = 0x98
PAGE02_AUX3_THRESHOLDS = 0xA0
PAGE02_CUSTOM_THRESHOLDS = 0xA8
# Lane-specific quads, bytes 176-199 (Table 8-55): three quantities x 8
# bytes = 24 bytes, exactly filling the range. Byte ORDER within the
# range (TxPower, then Bias, then RxPower) is an INFERENCE from the
# conventional SFF/CMIS field-listing order (matches how Table 8-55 lists
# them, and the common SFF-8636 convention) -- not an explicitly-stated
# byte-offset table in the research pass this was transcribed from.
# Confirm against real Table 8-55 byte offsets before trusting this if a
# real module's lane thresholds don't make sense.
PAGE02_TX_POWER_THRESHOLDS = 0xB0   # bytes 176-183, unsigned, 0.1uW
PAGE02_BIAS_THRESHOLDS = 0xB8       # bytes 184-191, unsigned, 2uA x multiplier (multiplier not decoded here)
PAGE02_RX_POWER_THRESHOLDS = 0xC0   # bytes 192-199, unsigned, 0.1uW
PAGE02_CHECKSUM_COVERAGE = (0x80, 0xFF)  # full-range sum, unlike Page 01h
PAGE02_CHECKSUM_BYTE = 0xFF


def _parse_threshold_quad(data, offset, signed):
    index = offset - UPPER_MEMORY_BASE
    values = []
    for i in range(4):
        raw = (data[index + i * 2] << 8) | data[index + i * 2 + 1]
        if signed and raw >= 0x8000:
            raw -= 0x10000
        values.append(raw)
    return dict(zip(("high_alarm", "low_alarm", "high_warning", "low_warning"), values))


def parse_page02_thresholds(data):
    """Decode Page 02h's module-level Temp/VCC and lane-specific
    TxPower/Bias/RxPower threshold quads. `data` must be exactly 128
    bytes starting at address 0x80. The Aux1-3 module-level quads aren't
    decoded here yet -- add as tests need them. See
    PAGE02_TX_POWER_THRESHOLDS's comment re: the lane-quad byte ORDER
    being an inference, not a confirmed table lookup.
    """
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 02h, got {len(data)}")

    temp = _parse_threshold_quad(data, PAGE02_TEMP_THRESHOLDS, signed=True)
    vcc = _parse_threshold_quad(data, PAGE02_VCC_THRESHOLDS, signed=False)
    aux1 = _parse_threshold_quad(data, PAGE02_AUX1_THRESHOLDS, signed=True)
    aux2 = _parse_threshold_quad(data, PAGE02_AUX2_THRESHOLDS, signed=True)
    aux3 = _parse_threshold_quad(data, PAGE02_AUX3_THRESHOLDS, signed=True)
    custom = _parse_threshold_quad(data, PAGE02_CUSTOM_THRESHOLDS, signed=True)
    tx_power = _parse_threshold_quad(data, PAGE02_TX_POWER_THRESHOLDS, signed=False)
    bias = _parse_threshold_quad(data, PAGE02_BIAS_THRESHOLDS, signed=False)
    rx_power = _parse_threshold_quad(data, PAGE02_RX_POWER_THRESHOLDS, signed=False)
    return {
        "temp_c": {k: v / 256.0 for k, v in temp.items()},
        "vcc_v": {k: v * 100e-6 for k, v in vcc.items()},
        "aux1_raw": aux1,  # TEC current or laser temp, module-config-dependent -- unscaled
        "aux2_raw": aux2,
        "aux3_raw": aux3,
        "custom_raw": custom,
        "tx_power_uw": {k: v * 0.1 for k, v in tx_power.items()},
        "bias_ua": {k: v * 2 for k, v in bias.items()},  # assumes multiplier=1, not decoded
        "rx_power_uw": {k: v * 0.1 for k, v in rx_power.items()},
    }


# --- Page 10h: Lane Control (Section 8.8, Table 8-59/8-60, p.144) --------
PAGE10_DATA_PATH_CONTROL_BYTE = 0x80  # DPDeinitLane<i>, one bit per lane (1=deinit)


def build_dp_deinit(lane_bits):
    """Build the Page 10h Data Path Control byte (128) from an 8-bit mask
    (bit i = lane i+1's DPDeinit bit, 1=deinitialize). Evaluated only in
    ModuleReady state (Section 8.8)."""
    return lane_bits & 0xFF


# --- Page 11h: Lane Status (Section 8.9, Tables 8-72/8-73/8-74, p.160) ---
# All RO. DPState is a 4-bit field per lane, 2 lanes packed per byte
# (low nibble = even lane, high nibble = odd lane), across bytes 128-131
# for 8 lanes total.
PAGE11_DP_STATE_BYTES = (0x80, 0x81, 0x82, 0x83)
PAGE11_OUTPUT_STATUS_BYTES = (0x84, 0x85)  # 132: Rx, 133: Tx -- 1 bit/lane

DP_STATE_DEACTIVATED = 0x1
DP_STATE_INIT = 0x2
DP_STATE_DEINIT = 0x3
DP_STATE_ACTIVATED = 0x4
DP_STATE_TX_TURN_ON = 0x5
DP_STATE_TX_TURN_OFF = 0x6
DP_STATE_INITIALIZED = 0x7
DP_STATE_NAMES = {
    DP_STATE_DEACTIVATED: "DPDeactivated",
    DP_STATE_INIT: "DPInit",
    DP_STATE_DEINIT: "DPDeinit",
    DP_STATE_ACTIVATED: "DPActivated",
    DP_STATE_TX_TURN_ON: "DPTxTurnOn",
    DP_STATE_TX_TURN_OFF: "DPTxTurnOff",
    DP_STATE_INITIALIZED: "DPInitialized",
}


def parse_page11_lane_status(data):
    """Decode Page 11h's per-lane Data Path state machine and output
    validity bits for up to 8 lanes. `data` must be exactly 128 bytes
    starting at address 0x80. Returns 1-indexed lane numbers in the
    result dicts, matching the spec's own DPStateHostLane<i> naming."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 11h, got {len(data)}")

    dp_states = {}
    for byte_i, offset in enumerate(PAGE11_DP_STATE_BYTES):
        byte_val = data[offset - UPPER_MEMORY_BASE]
        lane_even = byte_i * 2 + 1
        lane_odd = byte_i * 2 + 2
        dp_states[lane_even] = byte_val & 0xF
        dp_states[lane_odd] = (byte_val >> 4) & 0xF

    rx_byte = data[PAGE11_OUTPUT_STATUS_BYTES[0] - UPPER_MEMORY_BASE]
    tx_byte = data[PAGE11_OUTPUT_STATUS_BYTES[1] - UPPER_MEMORY_BASE]
    output_status = {
        lane: {"rx_valid": bool((rx_byte >> (lane - 1)) & 1),
               "tx_valid": bool((tx_byte >> (lane - 1)) & 1)}
        for lane in range(1, 9)
    }

    return {"dp_state": dp_states, "output_status": output_status}


# --- VDM: Versatile Diagnostic Monitoring (Section 8.14, Tables 8-119 --
# through 8-128, p.201). Optional, advertised by Page 01h's
# vdm_pages_supported bit (byte 142 bit 6). Up to 256 "instances" across 4
# groups of 64, each either unused or bound (via its descriptor) to one
# observable quantity. All VDM multi-byte values are BIG ENDIAN (the spec
# explicitly calls this out as differing from the Page 13h/14h Module
# Diagnostics registers).
PAGE_VDM_DESCRIPTORS = (0x20, 0x21, 0x22, 0x23)  # one page per group (1-4), 64 x 2B descriptors/page
PAGE_VDM_SAMPLES = (0x24, 0x25, 0x26, 0x27)      # 64 x 2B (X16) samples/page
PAGE_VDM_THRESHOLDS = (0x28, 0x29, 0x2A, 0x2B)   # 16 x 8B (4x2B quad) threshold sets/page

# VDM Instance Descriptor (Table 8-121): 2 bytes/instance.
#   even byte: bits 7-4 = LocalThresholdSetID, bits 3-0 = MonitoredResource
#   odd byte:  ObservableType (full byte, indexes VDM_OBSERVABLE_TYPE_NAMES)
VDM_MONITORED_RESOURCE_MODULE_WIDE = 0xF  # 0-7 = Lane/DataPath 1-8; 15 = module-wide

# Global ThresholdSetID = per-group offset + LocalThresholdSetID (Table 8-121's
# own worked mapping) -- lets a threshold set be referenced unambiguously
# across groups, since each group's Page 28h-2Bh only holds 16 local sets.
VDM_THRESHOLD_SET_GROUP_OFFSET = {0x20: 1, 0x21: 17, 0x22: 33, 0x23: 49}

# ObservableType values confirmed by name in the fetched text (Table
# 8-122) -- NOT a complete table (the full ID 3-99 range wasn't extracted).
# Data Type (U16/S16/F16) is a property of the Observable Type itself, per
# the spec -- NOT a separate descriptor field -- so full numeric decoding
# of a sample requires knowing every ID's data type, which this project
# doesn't have yet for most IDs. parse_vdm_sample() below returns the raw
# 16-bit value plus this name (or "unknown (not yet catalogued)") rather
# than guessing a data type for an uncatalogued ID.
VDM_OBSERVABLE_TYPE_NAMES = {
    0x00: "NotUsed (instance is passive/unused)",
    0x01: "LaserAge (Basic, U16)",
    0x02: "TECCurrent (Basic, S16)",
    # IDs 9-24: Pre-FEC BER / FERC (min/max/avg/current), Basic or
    # Statistic, Data Type F16 -- exact per-ID assignment within 9-24 not
    # extracted from the fetched text; reported generically if seen.
}
VDM_OBSERVABLE_TYPE_PRE_FEC_BER_RANGE = range(0x09, 0x19)  # 9-24 inclusive


def parse_vdm_descriptor(even_byte, odd_byte):
    """Decode one 2-byte VDM Instance Descriptor (Table 8-121)."""
    local_threshold_set_id = (even_byte >> 4) & 0xF
    monitored_resource = even_byte & 0xF
    observable_type = odd_byte

    if observable_type in VDM_OBSERVABLE_TYPE_NAMES:
        type_name = VDM_OBSERVABLE_TYPE_NAMES[observable_type]
    elif observable_type in VDM_OBSERVABLE_TYPE_PRE_FEC_BER_RANGE:
        type_name = "Pre-FEC BER/FERC statistic (Basic or Statistic, F16) -- exact ID meaning not catalogued"
    elif 0x64 <= observable_type <= 0x7F:
        type_name = "Custom Observable (100-127)"
    elif 0x80 <= observable_type <= 0xFF:
        type_name = "Restricted (OIF use), 128-255"
    elif observable_type == 0:
        type_name = VDM_OBSERVABLE_TYPE_NAMES[0]
    else:
        type_name = "reserved/unknown"

    return {
        "local_threshold_set_id": local_threshold_set_id,
        "monitored_resource": (
            "module-wide" if monitored_resource == VDM_MONITORED_RESOURCE_MODULE_WIDE
            else f"lane/DataPath {monitored_resource + 1}"
        ),
        "observable_type": observable_type,
        "observable_type_name": type_name,
        "is_used": observable_type != 0x00,
    }


def parse_vdm_descriptor_page(data, page):
    """Decode a full VDM descriptor page (Pages 20h-23h) into a list of up
    to 64 per-instance descriptors (see parse_vdm_descriptor()). `data`
    must be exactly 128 bytes starting at 0x80. `page` (one of
    PAGE_VDM_DESCRIPTORS) determines the Global ThresholdSetID offset
    attached to each entry."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of a VDM descriptor page, got {len(data)}")
    offset = VDM_THRESHOLD_SET_GROUP_OFFSET.get(page)
    descriptors = []
    for i in range(64):
        even, odd = data[i * 2], data[i * 2 + 1]
        d = parse_vdm_descriptor(even, odd)
        if offset is not None:
            d["global_threshold_set_id"] = offset + d["local_threshold_set_id"]
        descriptors.append(d)
    return descriptors


def parse_vdm_sample_page(data):
    """Decode a full VDM sample page (Pages 24h-27h) into a list of 64 raw
    unsigned 16-bit values (X16, big-endian, Table 8-123). Interpreting a
    given slot's sign/scale requires its paired descriptor's
    observable_type -- not done here, since most type IDs aren't
    catalogued yet (see VDM_OBSERVABLE_TYPE_NAMES)."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of a VDM sample page, got {len(data)}")
    return [(data[i * 2] << 8) | data[i * 2 + 1] for i in range(64)]


def parse_vdm_threshold_page(data):
    """Decode a full VDM threshold page (Pages 28h-2Bh) into a list of 16
    raw threshold quads (Table 8-124: HighAlarm/LowAlarm/HighWarning/
    LowWarning, same field order as Page 02h), indexed by LocalThresholdSetID
    0-15. Values are raw U16 -- scaling depends on the referencing
    descriptor's observable_type, same caveat as parse_vdm_sample_page()."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of a VDM threshold page, got {len(data)}")
    return [_parse_threshold_quad(data, UPPER_MEMORY_BASE + i * 8, signed=False) for i in range(16)]


# Page 2Fh: VDM Advertisement + dynamic controls (Table 8-128).
PAGE2F_VDM_SUPPORT_BYTE = 0x80         # bits 1-0: raw value + 1 = number of active groups (1-4)
PAGE2F_FINE_INTERVAL_LENGTH = (0x81, 2)  # bytes 129-130, U16, units of 0.1ms
PAGE2F_FREEZE_REQUEST_BYTE = 0x90      # byte 144, bit 7 (RW)
PAGE2F_FREEZE_DONE_UNFREEZE_DONE_BYTE = 0x91  # byte 145: bit 7 = FreezeDone (RO), bit 6 = UnfreezeDone (RO)


def parse_vdm_control(data):
    """Decode Page 2Fh's VDM group-count advertisement and the
    freeze/unfreeze handshake status. `data` must be exactly 128 bytes
    starting at 0x80."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 2Fh, got {len(data)}")

    support_byte = data[PAGE2F_VDM_SUPPORT_BYTE - UPPER_MEMORY_BASE]
    fine_interval_off, _ = PAGE2F_FINE_INTERVAL_LENGTH
    fine_interval_idx = fine_interval_off - UPPER_MEMORY_BASE
    fine_interval = (data[fine_interval_idx] << 8) | data[fine_interval_idx + 1]
    freeze_request_byte = data[PAGE2F_FREEZE_REQUEST_BYTE - UPPER_MEMORY_BASE]
    freeze_status_byte = data[PAGE2F_FREEZE_DONE_UNFREEZE_DONE_BYTE - UPPER_MEMORY_BASE]

    return {
        "active_vdm_groups": (support_byte & 0x3) + 1,
        "fine_interval_length_ms": fine_interval * 0.1,
        "freeze_request": bool((freeze_request_byte >> 7) & 0x1),
        "freeze_done": bool((freeze_status_byte >> 7) & 0x1),
        "unfreeze_done": bool((freeze_status_byte >> 6) & 0x1),
    }


def build_freeze_request_byte(assert_freeze):
    """Build Page 2Fh byte 144 (FreezeRequest, bit 7) -- write True to
    request the module freeze all VDM statistics registers for a
    consistent multi-instance snapshot, False to release."""
    return 0x80 if assert_freeze else 0x00


# --- Page 15h: Timing Characteristics (Section 8.13, p.201) --------------
# Optional, advertised via Page 01h's timing_page15h_supported bit (byte
# 145 bit 3). All RO. Per-host-lane (8 lanes) module transit latency.
# Spec explicitly notes accuracy/update-timing semantics are UNDEFINED in
# this revision -- treat these as informational, not tight-tolerance
# assertable values.
PAGE15_RX_LATENCY_BASE = 0xE0   # bytes 224-239: 8 x U16 ns, DataPathRxLatencyHostLane<i>
PAGE15_TX_LATENCY_BASE = 0xF0   # bytes 240-255: 8 x U16 ns, DataPathTxLatencyHostLane<i>


def parse_page15_timing(data):
    """Decode Page 15h's per-lane Rx/Tx transit latency (nanoseconds).
    `data` must be exactly 128 bytes starting at address 0x80. Returns
    1-indexed lane numbers, matching the spec's own HostLane<i> naming."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 15h, got {len(data)}")

    def _lane_values(base):
        idx = base - UPPER_MEMORY_BASE
        return {
            lane: (data[idx + (lane - 1) * 2] << 8) | data[idx + (lane - 1) * 2 + 1]
            for lane in range(1, 9)
        }

    return {
        "rx_latency_ns": _lane_values(PAGE15_RX_LATENCY_BASE),
        "tx_latency_ns": _lane_values(PAGE15_TX_LATENCY_BASE),
    }


# --- Page 03h: User EEPROM (Section 8.6, p.140) ---------------------------
# Optional, advertised via Page 01h's page03_user_eeprom_supported bit
# (byte 142 bit 2). The whole page (128-255) is host-writable, vendor-
# unspecified-use non-volatile memory -- no fixed field layout to decode,
# unlike every other page in this file. Max PAGE_USER_EEPROM_MAX_WRITE_BYTES
# (8) bytes per write; tWRITENV (80ms) hold-off applies after writing.
PAGE03_USER_EEPROM_BASE = 0x80
PAGE03_USER_EEPROM_SIZE = 0x80


# --- CDB: Command Data Block framing (Section 8.15, Tables 8-129/8-130/8-131, p.212) --
# CDB is the firmware-update / vendor-extension command mechanism. A host
# writes a command header (+ optional Local/Extended Payload) to Page 9Fh
# (+ A0h-AFh for EPL), then polls CDB_CMD_QUERY_STATUS for completion.
CDB_CMD_HEADER_CMDID = (0x80, 2)      # bytes 128-129, BE, WRITING this "sends" the command
CDB_CMD_HEADER_EPL_LENGTH = (0x82, 2)  # bytes 130-131, BE, 0-2048
CDB_CMD_HEADER_LPL_LENGTH = 0x84       # byte 132
CDB_CMD_HEADER_CHECKSUM = 0x85         # byte 133
CDB_REPLY_HEADER_RPL_LENGTH = 0x86     # byte 134
CDB_REPLY_HEADER_CHECKSUM = 0x87       # byte 135
CDB_LPL_BASE = 0x88                    # byte 136 onward, up to 120 bytes

CDB_CMD_QUERY_STATUS = 0x0000
CDB_CMD_ENTER_PASSWORD = 0x0001
CDB_CMD_CHANGE_PASSWORD = 0x0002
CDB_CMD_ABORT = 0x0004
CDB_CMD_MODULE_FEATURES = 0x0040
CDB_CMD_FW_MANAGEMENT_FEATURES = 0x0041
CDB_CMD_GET_FIRMWARE_INFO = 0x0100
CDB_CMD_START_FIRMWARE_DOWNLOAD = 0x0101
CDB_CMD_ABORT_FIRMWARE_DOWNLOAD = 0x0102
CDB_CMD_WRITE_FIRMWARE_BLOCK_LPL = 0x0103
CDB_CMD_WRITE_FIRMWARE_BLOCK_EPL = 0x0104
CDB_CMD_COMPLETE_FIRMWARE_DOWNLOAD = 0x0107
CDB_CMD_COPY_FIRMWARE_IMAGE = 0x0108
CDB_CMD_RUN_FIRMWARE_IMAGE = 0x0109

CDB_COPY_DIRECTION_A_TO_B = 0xAB
CDB_COPY_DIRECTION_B_TO_A = 0xBA

CDB_RUN_IMAGE_TRAFFIC_AFFECTING_TO_INACTIVE = 0x00
CDB_RUN_IMAGE_HITLESS_TO_INACTIVE = 0x01
CDB_RUN_IMAGE_TRAFFIC_AFFECTING_TO_RUNNING = 0x02
CDB_RUN_IMAGE_HITLESS_TO_RUNNING = 0x03


def build_cdb_command(cmd_id, lpl_payload=b""):
    """Build a full CDB command: the 6-byte header (Table 8-130) followed
    by the LPL payload, ready to write starting at Page 9Fh offset 0x80
    (byte 128). EPL-carried commands (payload > 120 bytes) aren't built by
    this helper -- those also need writes to Pages A0h-AFh, not attempted
    here yet.

    Checksum (byte 133, CdbChkCode): the spec's prose calls this a "one's
    complement of the sum" of bytes 128-132 plus the LPL payload, but the
    0004h Abort command's own worked example (fixed CdbChkCode=FCh for a
    zero-payload Abort, sum=0x04) only checks out as a NEGATION
    (two's-complement, `(0x100 - sum) & 0xFF` = 0xFC) -- plain bitwise
    complement (`~sum & 0xFF`) gives 0xFB instead. Implemented to match
    the worked example (negation), not the prose, since that's the
    stronger evidence -- flagged here in case a real module disagrees.
    """
    if len(lpl_payload) > 120:
        raise ValueError(
            f"LPL payload is {len(lpl_payload)} bytes, max 120 -- longer "
            f"commands need EPL (pages A0h-AFh), not implemented by this helper"
        )

    header_prefix = bytes([
        (cmd_id >> 8) & 0xFF, cmd_id & 0xFF,   # 128-129: CMDID
        0x00, 0x00,                             # 130-131: EPLLength (none, via this helper)
        len(lpl_payload) & 0xFF,                 # 132: LPLLength
    ])
    checksum = compute_cdb_checksum(header_prefix + lpl_payload)
    return header_prefix + bytes([checksum]) + lpl_payload


def build_cdb_query_status(response_delay_ms=0):
    """Build the 0000h Query Status command (Table 9-3): LPL = 2-byte
    ResponseDelay (module should respond ASAP if 0)."""
    lpl = bytes([(response_delay_ms >> 8) & 0xFF, response_delay_ms & 0xFF])
    return build_cdb_command(CDB_CMD_QUERY_STATUS, lpl)


def build_cdb_start_firmware_download(image_size, vendor_data=b""):
    """Build the 0101h Start Firmware Download command (Table 9-16). LPL =
    ImageSize (U32, bytes 136-139) + 4 reserved bytes (140-143) + up to
    112 bytes of vendor header data (144-255)."""
    if len(vendor_data) > 112:
        raise ValueError(f"vendor_data is {len(vendor_data)} bytes, max 112")
    lpl = bytes([
        (image_size >> 24) & 0xFF, (image_size >> 16) & 0xFF,
        (image_size >> 8) & 0xFF, image_size & 0xFF,
        0x00, 0x00, 0x00, 0x00,
    ]) + vendor_data
    return build_cdb_command(CDB_CMD_START_FIRMWARE_DOWNLOAD, lpl)


def build_cdb_write_firmware_block_lpl(block_address, firmware_block):
    """Build the 0103h Write Firmware Block LPL command (Table 9-18). LPL
    = BlockAddress (U32, bytes 136-139) + up to 116 bytes of firmware
    image data (140-255)."""
    if len(firmware_block) > 116:
        raise ValueError(
            f"firmware_block is {len(firmware_block)} bytes, max 116 for LPL -- "
            f"use Write Firmware Block EPL (0104h, not implemented here) for larger blocks"
        )
    lpl = bytes([
        (block_address >> 24) & 0xFF, (block_address >> 16) & 0xFF,
        (block_address >> 8) & 0xFF, block_address & 0xFF,
    ]) + firmware_block
    return build_cdb_command(CDB_CMD_WRITE_FIRMWARE_BLOCK_LPL, lpl)


def build_cdb_copy_firmware_image(direction):
    """Build the 0108h Copy Firmware Image command (Table 9-23). LPL =
    1 byte CopyDirection (CDB_COPY_DIRECTION_A_TO_B/B_TO_A)."""
    return build_cdb_command(CDB_CMD_COPY_FIRMWARE_IMAGE, bytes([direction]))


def build_cdb_run_firmware_image(image_to_run, delay_to_reset_ms=0):
    """Build the 0109h Run Firmware Image command (Table 9-24). LPL = 1
    reserved byte + ImageToRun (byte 137) + DelayToReset (U16, bytes
    138-139). Note: if delay_to_reset_ms is 0, the spec warns the module
    may reset before the host even reads back CdbStatus for this command."""
    lpl = bytes([
        0x00, image_to_run & 0xFF,
        (delay_to_reset_ms >> 8) & 0xFF, delay_to_reset_ms & 0xFF,
    ])
    return build_cdb_command(CDB_CMD_RUN_FIRMWARE_IMAGE, lpl)


def compute_cdb_checksum(header_prefix_and_lpl):
    """Negation (two's complement) of the sum of the given bytes, mod 256
    -- see build_cdb_command()'s docstring for why this, not a plain
    bitwise complement, matches the spec's own Abort worked example.
    `header_prefix_and_lpl` should be bytes 128-132 concatenated with the
    LPL payload (everything build_cdb_command() writes except the
    checksum byte itself)."""
    return (0x100 - (sum(header_prefix_and_lpl) & 0xFF)) & 0xFF


def parse_cdb_query_status_reply(lpl_payload):
    """Decode the 0000h Query Status reply LPL body (Table 9-3): byte 0
    (absolute offset 136) = Length (should be 2), byte 1 (137) = Status,
    reporting the module's current unlock level -- NOT the same thing as
    CdbStatus (Lower Memory 0x25/0x26, which reports whether the QUERY
    STATUS *command itself* succeeded/is still running; this is the
    payload it returns once it has).
    """
    if len(lpl_payload) < 2:
        raise ValueError(f"expected at least 2 bytes of Query Status reply LPL, got {len(lpl_payload)}")
    length, status = lpl_payload[0], lpl_payload[1]
    if status == 0x00:
        unlock_level = "module_boot_up"
    elif status == 0x01:
        unlock_level = "host_password_accepted"
    elif status & 0x80:
        unlock_level = "module_password_accepted"
    else:
        unlock_level = "reserved/undefined"
    return {"length": length, "status_byte": status, "unlock_level": unlock_level}


# --- CDB 0100h Get Firmware Info reply (Table 9-15) -----------------------
def parse_cdb_get_firmware_info(lpl_payload):
    """Decode the 0100h Get Firmware Info reply LPL body. `lpl_payload`
    should start at absolute byte 136 (i.e. index 0 == byte 136).
    ImageInformation's bit-to-offset mapping has one unresolved wrinkle:
    the spec's prose says Factory/Boot info starts at byte 201, but its
    own field table lists FactoryBootMajor starting at byte 210 --
    implemented using the field-table offset (210), flagged here in case
    a real module's reply disagrees.
    """
    if len(lpl_payload) < 2:
        raise ValueError(f"expected at least 2 bytes of Get Firmware Info reply LPL, got {len(lpl_payload)}")

    def _u8(byte_offset):
        idx = byte_offset - 136
        return lpl_payload[idx] if idx < len(lpl_payload) else None

    firmware_status = lpl_payload[0]
    image_information = lpl_payload[1]
    result = {
        "bank_a_operational": bool(firmware_status & 0x1),
        "bank_a_administrative": bool((firmware_status >> 1) & 0x1),
        "bank_a_invalid": bool((firmware_status >> 2) & 0x1),
        "bank_b_operational": bool((firmware_status >> 4) & 0x1),
        "bank_b_administrative": bool((firmware_status >> 5) & 0x1),
        "bank_b_invalid": bool((firmware_status >> 6) & 0x1),
    }

    if image_information & 0x1:
        result["image_a"] = (_u8(138), _u8(139))  # (major, minor); build/extra-string not decoded
    if image_information & 0x2:
        result["image_b"] = (_u8(174), _u8(175))
    if image_information & 0x4:
        result["factory_boot"] = (_u8(210), _u8(211))

    return result


def parse_cdb_reply_header(data):
    """Decode the 2-byte CDB reply header (Table 8-131) from a Page 9Fh
    read. `data` must be exactly 128 bytes starting at address 0x80.
    RPLLength 0-120 means an LPL-only reply of that many bytes; 240-255
    means an EPL reply of (value-239) 128-byte pages starting at A0h."""
    if len(data) < 128:
        raise ValueError(f"expected 128 bytes of Page 9Fh, got {len(data)}")

    rpl_length = data[CDB_REPLY_HEADER_RPL_LENGTH - UPPER_MEMORY_BASE]
    rpl_checksum = data[CDB_REPLY_HEADER_CHECKSUM - UPPER_MEMORY_BASE]
    is_epl = rpl_length >= 240
    return {
        "rpl_length": rpl_length,
        "rpl_checksum": rpl_checksum,
        "is_epl_reply": is_epl,
        "epl_pages": (rpl_length - 239) if is_epl else 0,
        "lpl_length": 0 if is_epl else rpl_length,
    }
