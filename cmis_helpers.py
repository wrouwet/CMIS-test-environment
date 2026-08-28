"""Shared plumbing for CMIS register-level reads/writes and page
selection.

CMIS modules are plain I2C targets with a conventional "write register
offset, then read N bytes" access pattern -- unlike the sibling IPMB/
MCTP projects, there's no bus-mastership swap, no PEC, no fragmentation
at this layer. bridge.write_read() (the "X" bridge command: write bytes,
repeated-start, then read) maps directly onto this.
"""

import time

import pytest

import cmis


def require_paged(module_info, what="this page"):
    """Skip the current test (with a printed reason) if the module
    reports the Flat memory model -- shared by every test file gating on
    a page that Table 8-4 says only exists for Paged modules. `what`
    should name the page(s) being gated, e.g. "Page 01h" or
    "Pages 10h/11h", for a clear skip message."""
    if module_info["memory_model"] == cmis.MEMORY_MODEL_FLAT:
        pytest.skip(f"module reports Flat Memory model -- {what} isn't supported (Table 8-4)")


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
    send_cdb_full_command(bridge, cmis.build_cdb_command(cmd_id, lpl_payload))


def send_cdb_full_command(bridge, command_bytes):
    """Write an already-framed CDB command (e.g. from
    cmis.build_cdb_query_status()/build_cdb_start_firmware_download()/etc.)
    to Page 9Fh. Lower-level than send_cdb_command() -- use this when the
    command needs a builder more specific than a bare cmd_id+lpl_payload."""
    select_page(bridge, bank=0x00, page=cmis.PAGE_CDB_MESSAGE)
    bridge.write(cmis.CMIS_I2C_ADDR, [cmis.UPPER_MEMORY_BASE] + list(command_bytes))
    time.sleep(cmis.T_WRITE_MS / 1000.0)


def poll_cdb_status(bridge, instance=1, timeout_s=2.0, interval_s=0.1):
    """Poll Lower Memory's CdbStatus field (Section 8.2.8) until it
    reports something other than 'in_progress', or `timeout_s` elapses.
    Returns the final decoded status dict (see cmis.decode_cdb_status()).
    This is the spec-recommended way to wait for a CDB command to finish
    -- NOT read_cdb_reply()'s Page 9Fh reply header, which only describes
    the LPL/EPL *body* framing, not whether the module is still busy."""
    deadline = time.monotonic() + timeout_s
    status = None
    while time.monotonic() < deadline:
        lower = cmis.parse_lower_memory(read_lower_memory(bridge))
        status = lower["cdb_status_1"] if instance == 1 else lower["cdb_status_2"]
        if status["state"] != "in_progress":
            return status
        time.sleep(interval_s)
    return status


def read_cdb_reply(bridge):
    """Read back Page 9Fh and decode the CDB reply header (Table 8-131)
    plus the reply body -- LPL payload bytes for an LPL-only reply, or
    the concatenated EPL pages (via read_cdb_epl_reply()) for an EPL
    reply. Reading Pages A0h-AFh is safe regardless of the open
    checksum-coverage question noted in cmis.build_cdb_command_with_epl()
    -- it's a read, not a write."""
    data = read_upper_memory(bridge)
    reply = cmis.parse_cdb_reply_header(data)
    if reply["is_epl_reply"]:
        reply["lpl_payload"] = b""
        reply["epl_payload"] = read_cdb_epl_reply(bridge, reply["epl_pages"])
    elif reply["lpl_length"] > 0:
        start = cmis.CDB_LPL_BASE - cmis.UPPER_MEMORY_BASE
        reply["lpl_payload"] = data[start:start + reply["lpl_length"]]
        reply["epl_payload"] = b""
    else:
        reply["lpl_payload"] = b""
        reply["epl_payload"] = b""
    return reply


def read_cdb_epl_reply(bridge, num_pages):
    """Read `num_pages` x 128-byte EPL reply pages (A0h-AFh onward) and
    return them concatenated. Read-only, safe to call regardless of the
    checksum-coverage question in cmis.build_cdb_command_with_epl()."""
    chunks = []
    for i in range(num_pages):
        chunks.append(read_page(bridge, bank=0x00, page=cmis.PAGE_CDB_EPL_BASE + i))
    return b"".join(chunks)


def try_select_page(bridge, bank, page, settle=True):
    """Attempt to select a bank/page and confirm, by reading back Lower
    Memory's PageSelect field, whether it actually took -- the robust way
    to gate a test on "does this optional page even exist" that doesn't
    depend on correctly decoding any particular advertisement bit (some
    of which, e.g. Page 01h's per-page "Supported Pages" bitmap, this
    project hasn't independently confirmed bit-for-bit yet -- see
    cmis.py). Uses the spec's own confirmed gotcha (Section 8.2.13):
    selecting an unsupported page silently resets PageSelect back to
    0x00 rather than erroring.

    Returns True if `page` reads back as selected, False otherwise (in
    which case the module has already fallen back to Page 00h -- no
    cleanup needed by the caller).
    """
    select_page(bridge, bank, page, settle=settle)
    lower = cmis.parse_lower_memory(read_lower_memory(bridge))
    return lower["page_select"] == (page & 0xFF) and lower["bank_select"] == (bank & 0xFF)


def read_vdm_control(bridge):
    """Select Page 2Fh and decode VDM's group-count advertisement and
    freeze/unfreeze handshake status (see cmis.parse_vdm_control())."""
    data = read_page(bridge, bank=0x00, page=cmis.PAGE_VDM_CONTROL)
    return cmis.parse_vdm_control(data)


def read_vdm_group(bridge, group_index):
    """Read one VDM group's (0-3, i.e. groups 1-4) descriptor + sample +
    threshold pages and return them decoded together, since a
    descriptor's fields are what make its paired sample/threshold data
    meaningful. Does not itself check active_vdm_groups (see
    read_vdm_control()) -- callers should skip groups beyond what's
    advertised rather than assume all 4 pages exist."""
    descriptor_page = cmis.PAGE_VDM_DESCRIPTORS[group_index]
    sample_page = cmis.PAGE_VDM_SAMPLES[group_index]
    threshold_page = cmis.PAGE_VDM_THRESHOLDS[group_index]

    descriptors = cmis.parse_vdm_descriptor_page(
        read_page(bridge, bank=0x00, page=descriptor_page), descriptor_page)
    samples = cmis.parse_vdm_sample_page(read_page(bridge, bank=0x00, page=sample_page))
    thresholds = cmis.parse_vdm_threshold_page(read_page(bridge, bank=0x00, page=threshold_page))

    return {"descriptors": descriptors, "samples": samples, "thresholds": thresholds}


def vdm_freeze(bridge, timeout_s=2.0, interval_s=0.05):
    """Assert Page 2Fh's FreezeRequest bit and poll FreezeDone until the
    module confirms (or `timeout_s` elapses) -- the handshake needed to
    read multiple VDM statistics instances as a gap-free, consistent
    snapshot (Section 8.14). Returns True if FreezeDone was observed."""
    select_page(bridge, bank=0x00, page=cmis.PAGE_VDM_CONTROL)
    bridge.write(cmis.CMIS_I2C_ADDR,
                 [cmis.PAGE2F_FREEZE_REQUEST_BYTE, cmis.build_freeze_request_byte(True)])
    time.sleep(cmis.T_WRITE_MS / 1000.0)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if read_vdm_control(bridge)["freeze_done"]:
            return True
        time.sleep(interval_s)
    return False


def vdm_unfreeze(bridge, timeout_s=2.0, interval_s=0.05):
    """Clear Page 2Fh's FreezeRequest bit and poll UnfreezeDone until the
    module confirms (or `timeout_s` elapses). Returns True if
    UnfreezeDone was observed."""
    select_page(bridge, bank=0x00, page=cmis.PAGE_VDM_CONTROL)
    bridge.write(cmis.CMIS_I2C_ADDR,
                 [cmis.PAGE2F_FREEZE_REQUEST_BYTE, cmis.build_freeze_request_byte(False)])
    time.sleep(cmis.T_WRITE_MS / 1000.0)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if read_vdm_control(bridge)["unfreeze_done"]:
            return True
        time.sleep(interval_s)
    return False


def read_page15_timing(bridge):
    """Select Page 15h and decode per-lane Rx/Tx transit latency."""
    return cmis.parse_page15_timing(read_page(bridge, bank=0x00, page=cmis.PAGE_TIMING_CHARACTERISTICS))


def write_user_eeprom(bridge, offset, data):
    """Write `data` to Page 03h (User EEPROM) starting at absolute address
    `offset` (0x80-0xFF), chunked to the spec's max 8 bytes/write
    (Section 8.6), waiting out tWRITENV after each chunk since this is
    non-volatile memory. Caller must already have selected Page 03h."""
    for chunk_start in range(0, len(data), cmis.PAGE_USER_EEPROM_MAX_WRITE_BYTES):
        chunk = data[chunk_start:chunk_start + cmis.PAGE_USER_EEPROM_MAX_WRITE_BYTES]
        bridge.write(cmis.CMIS_I2C_ADDR, [offset + chunk_start] + list(chunk))
        time.sleep(cmis.T_WRITE_NV_MS / 1000.0)


def read_page12_tunable_laser(bridge):
    return cmis.parse_page12_tunable_laser(read_page(bridge, bank=0x00, page=cmis.PAGE_TUNABLE_LASER))


def read_page13_loopback_capabilities(bridge):
    data = read_page(bridge, bank=0x00, page=cmis.PAGE_DIAG_CONTROL)
    return cmis.parse_page13_loopback_capabilities(data[cmis.PAGE13_LOOPBACK_CAPABILITIES_BYTE - cmis.UPPER_MEMORY_BASE])


def read_page13_loopback_controls(bridge):
    return cmis.parse_page13_loopback_controls(read_page(bridge, bank=0x00, page=cmis.PAGE_DIAG_CONTROL))


def read_page14_status(bridge, selector=None):
    """Select Page 14h; if `selector` is given, write it to
    DiagnosticsSelector first (a safe, non-traffic-affecting mux change,
    unlike Page 13h's loopback controls) and wait tWRITE before reading."""
    select_page(bridge, bank=0x00, page=cmis.PAGE_DIAG_RESULTS)
    if selector is not None:
        bridge.write(cmis.CMIS_I2C_ADDR, [cmis.PAGE14_DIAGNOSTICS_SELECTOR_BYTE, selector])
        time.sleep(cmis.T_WRITE_MS / 1000.0)
    return cmis.parse_page14_status(read_upper_memory(bridge))


def read_page16_network_path_status(bridge):
    return cmis.parse_page16_network_path_status(read_page(bridge, bank=0x00, page=cmis.PAGE_NETWORK_PATH))


def read_page17_np_flags(bridge):
    return cmis.parse_page17_np_flags(read_page(bridge, bank=0x00, page=cmis.PAGE_NETWORK_PATH_FLAGS))


def read_page19_datapath_config(bridge):
    return cmis.parse_page19_datapath_config(read_page(bridge, bank=0x00, page=cmis.PAGE_DATAPATH_CONFIG))


def read_page1c_nad(bridge, bank_index=0):
    data = read_page(bridge, bank=bank_index, page=cmis.PAGE_NORMALIZED_APP_DESCRIPTORS)
    return cmis.parse_page1c_nad(data, bank_index=bank_index)


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
