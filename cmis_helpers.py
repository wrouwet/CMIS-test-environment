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


def discover_module(bridge):
    """Read Lower Memory and decode + PRINT the module's self-reported
    identity/capability facts -- CMIS's own built-in, on-the-wire
    discovery mechanism (the CmisRevision byte, and the MemoryModel bit
    that determines which pages are even supported at all).

    Per explicit user direction (2026-08-27): since CMIS provides a real
    discovery protocol, this project does NOT maintain separate
    hardcoded test suites per CMIS version. Instead, every test session
    discovers the actual module's revision/memory model up front (this
    function, via the session-scoped `module_info` fixture in
    conftest.py), prints exactly what it found, and the rest of the
    suite is expected to branch/skip on that discovered data rather
    than assume a specific version's behavior.

    Returns the decoded Lower Memory dict (see cmis.parse_lower_memory())
    so callers needing to gate behavior on the discovered version or
    memory model have the raw fields available, not just the printed
    summary.
    """
    data = read_lower_memory(bridge)
    info = cmis.parse_lower_memory(data)
    revision = f"{info['cmis_revision_major']}.{info['cmis_revision_minor']}"
    is_flat = info["memory_model"] == cmis.MEMORY_MODEL_FLAT
    model_name = "Flat" if is_flat else "Paged"
    model_note = (
        "only Page 00h is supported (Table 8-4)" if is_flat
        else "Pages 00h-02h, 10h-11h supported per Table 8-4 -- exact page "
             "support beyond that should still be confirmed per-page, not assumed"
    )
    state_name = cmis.MODULE_STATE_NAMES.get(info["module_state"], "UNKNOWN/RESERVED")
    version_note = cmis.VERSION_HISTORY.get(
        (info["cmis_revision_major"], info["cmis_revision_minor"]),
        "not in this project's known revision list (4.0/5.0/5.1/5.2/5.3) -- "
        "either older/newer than researched, or a decoding issue; proceed "
        "cautiously and don't assume this project's page/field assumptions hold",
    )

    print(f"[cmis-discover] CMIS revision: {revision} -- {version_note}")
    print(f"[cmis-discover] Memory model: {model_name} ({model_note})")
    print(f"[cmis-discover] Identifier (SFF-8024) byte: 0x{info['identifier']:02x}")
    print(f"[cmis-discover] Module state: {info['module_state']:03b}b ({state_name})")
    return info


def read_page(bridge, bank, page, settle=True):
    """Select a bank/page and read its 128-byte Upper Memory contents in
    one call -- the common pattern every per-page test needs. Equivalent
    to select_page() followed by read_upper_memory()."""
    select_page(bridge, bank, page, settle=settle)
    return read_upper_memory(bridge)


def unlock_password(bridge, password):
    """Write a password to Lower Memory's PasswordEntryArea (bytes
    122-125, Section 8.2.12) to unlock password-protected features. This
    is the direct register-based mechanism; CDB_CMD_ENTER_PASSWORD is the
    other, independent way to do the same thing -- a given module may
    implement only one. This mechanism gives no direct success/failure
    feedback (unlike the CDB command) -- the caller has to try a
    subsequent protected access and see if it's still locked."""
    offset, _ = cmis.PASSWORD_ENTRY_AREA
    payload = [offset] + list(cmis.build_password_write(password))
    bridge.write(cmis.CMIS_I2C_ADDR, payload)
    time.sleep(cmis.T_WRITE_MS / 1000.0)


def send_cdb_command(bridge, cmd_id, lpl_payload=b""):
    """Write a CDB command (Section 8.15) to Page 9Fh and return once the
    write completes -- does NOT wait for or read the reply; the module
    processes CDB commands asynchronously (see CDB_CMD_QUERY_STATUS) and
    ResponseDelay (returned by that query) tells you how long to wait
    before polling. LPL-only (<=120 byte payload) commands only -- EPL
    (pages A0h-AFh) isn't wired up here yet."""
    select_page(bridge, bank=0x00, page=cmis.PAGE_CDB_MESSAGE)
    command = cmis.build_cdb_command(cmd_id, lpl_payload)
    bridge.write(cmis.CMIS_I2C_ADDR, [cmis.UPPER_MEMORY_BASE] + list(command))
    time.sleep(cmis.T_WRITE_MS / 1000.0)


def read_cdb_reply(bridge):
    """Read back Page 9Fh and decode the CDB reply header (Table 8-131)
    plus, for an LPL-only reply, the LPL payload bytes themselves."""
    data = read_upper_memory(bridge)
    reply = cmis.parse_cdb_reply_header(data)
    if not reply["is_epl_reply"] and reply["lpl_length"] > 0:
        start = cmis.CDB_LPL_BASE - cmis.UPPER_MEMORY_BASE
        reply["lpl_payload"] = data[start:start + reply["lpl_length"]]
    else:
        reply["lpl_payload"] = b""
    return reply


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
