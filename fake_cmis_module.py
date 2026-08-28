"""An in-memory CMIS module simulator, implementing the same interface as
bridge.I2CBridge (scan/write/read/write_read/close). This is NOT a
substitute for real hardware verification (see README's "Current status"
section) -- it's a way to actually EXECUTE this project's test
bodies end-to-end and catch real Python bugs (wrong index math, wrong
attribute names, off-by-one slicing) that `pytest --collect-only` and
cmis.py's own synthetic-buffer unit checks can't, since those never run
a full page-select -> read -> decode -> assert round trip the way a real
test session does.

Enabled via CMIS_USE_FAKE_BRIDGE=1 (see conftest.py's `bridge` fixture) --
`CMIS_USE_FAKE_BRIDGE=1 .venv/bin/pytest tests/` runs the whole suite
against this simulator. A pass here means "the test code runs and its
logic is internally consistent against a module that behaves exactly
like this project assumes CMIS modules behave" -- it does NOT mean a
real module will behave this way; only real hardware can confirm that
(see cmis.py's many "inference, not independently confirmed" flags,
which this simulator deliberately implements as if they WERE confirmed,
since it has no way to simulate being wrong about the spec).
"""

import cmis


class FakeCmisModule:
    def __init__(self):
        self.lower = bytearray(128)
        self.pages = {}
        self.bank_select = 0x00
        self.page_select = 0x00
        self._unlock_status = 0x00  # Query Status reply Status byte (Table 9-3)
        self._setup_lower_memory()
        self._setup_page00()
        self._setup_page01()
        self._setup_page02()
        self.pages[0x03] = bytearray(128)  # User EEPROM, arbitrary content
        self._setup_page10_11()
        self._setup_page12()
        self._setup_page13_14()
        self._setup_page15()
        self._setup_page16_17()
        self._setup_page19()
        self._setup_page1c()
        self._setup_vdm_pages()
        self.pages[0x9F] = bytearray(128)  # CDB message page

    # --- Lower Memory setup -----------------------------------------------
    def _setup_lower_memory(self):
        self.lower[cmis.SFF8024_IDENTIFIER_BYTE] = 0x18  # QSFP-DD, arbitrary but non-zero
        self.lower[cmis.CMIS_REVISION_BYTE] = 0x50  # rev 5.0
        self.lower[cmis.MODULE_FLAGS_BYTE] = 0x00  # Paged memory model
        self.lower[cmis.MODULE_STATE_BYTE] = cmis.MODULE_STATE_READY << 1
        temp_raw = int(35.0 * 256)  # 35.0 C
        self.lower[cmis.TEMP_MON_BYTES[0]] = (temp_raw >> 8) & 0xFF
        self.lower[cmis.TEMP_MON_BYTES[1]] = temp_raw & 0xFF
        vcc_raw = int(3.3 / 100e-6)  # 3.3 V
        self.lower[cmis.VCC_MON_BYTES[0]] = (vcc_raw >> 8) & 0xFF
        self.lower[cmis.VCC_MON_BYTES[1]] = vcc_raw & 0xFF
        self.lower[cmis.CDB_STATUS_1_BYTE] = 0x00  # Reserved/idle-ish until a command runs
        self.lower[cmis.CDB_STATUS_2_BYTE] = 0x00

    # --- Page 00h -----------------------------------------------------------
    def _setup_page00(self):
        page = bytearray(128)

        def put_ascii(offset_length, text):
            offset, length = offset_length
            idx = offset - cmis.UPPER_MEMORY_BASE
            encoded = text.encode("ascii").ljust(length, b" ")[:length]
            page[idx:idx + length] = encoded

        put_ascii(cmis.PAGE00_VENDOR_NAME, "FAKE-VENDOR")
        put_ascii(cmis.PAGE00_VENDOR_PN, "FAKE-PN-0001")
        put_ascii(cmis.PAGE00_VENDOR_REV, "A0")
        put_ascii(cmis.PAGE00_VENDOR_SN, "SN0000000001")
        put_ascii(cmis.PAGE00_DATE_CODE, "26082700")
        start, end = cmis.PAGE00_CHECKSUM_COVERAGE
        checksum = sum(page[start - cmis.UPPER_MEMORY_BASE:end - cmis.UPPER_MEMORY_BASE]) & 0xFF
        page[cmis.PAGE00_CHECKSUM_BYTE - cmis.UPPER_MEMORY_BASE] = checksum
        self.pages[0x00] = page

    # --- Page 01h -----------------------------------------------------------
    def _setup_page01(self):
        page = bytearray(128)
        supported_pages = (
            (1 << cmis.PAGE01_SUPPORTED_PAGES_VDM_BIT)
            | (1 << cmis.PAGE01_SUPPORTED_PAGES_DIAG_BIT)
            | (1 << cmis.PAGE01_SUPPORTED_PAGES_PAGE03_BIT)
        )
        page[cmis.PAGE01_SUPPORTED_PAGES_BYTE - cmis.UPPER_MEMORY_BASE] = supported_pages
        page[cmis.PAGE01_SUPPORTED_PAGES_BYTE - cmis.UPPER_MEMORY_BASE] |= (
            1 << cmis.PAGE01_SUPPORTED_PAGES_NETWORK_PATH_BIT
        )
        page[cmis.PAGE01_MODULE_CHARACTERISTICS_BYTE - cmis.UPPER_MEMORY_BASE] = (
            1 << cmis.PAGE01_MODCHAR_TIMING_PAGE15H_SUPPORTED_BIT
        )
        page[cmis.PAGE01_SUPPORTED_CONTROLS_BYTE - cmis.UPPER_MEMORY_BASE] = (
            1 << cmis.PAGE01_SUPCTL_TRANSMITTER_TUNABLE_BIT
        )
        page[cmis.PAGE01_BYTE_162 - cmis.UPPER_MEMORY_BASE] = (
            1 << cmis.PAGE01_UNIDIR_RECONFIG_SUPPORTED_BIT
        )
        page[cmis.PAGE01_NAD_BANKS_BYTE - cmis.UPPER_MEMORY_BASE] = 1  # 1 bank of Page 1Ch
        cdb_off, _ = cmis.PAGE01_CDB_FUNCTIONALITY
        page[cdb_off - cmis.UPPER_MEMORY_BASE] = (1 << 6)  # cdb_instances_supported = 1
        start, end = cmis.PAGE01_CHECKSUM_COVERAGE
        checksum = sum(page[start - cmis.UPPER_MEMORY_BASE:end - cmis.UPPER_MEMORY_BASE]) & 0xFF
        page[cmis.PAGE01_CHECKSUM_BYTE - cmis.UPPER_MEMORY_BASE] = checksum
        self.pages[0x01] = page

    # --- Page 02h -----------------------------------------------------------
    def _setup_page02(self):
        page = bytearray(128)

        def put_quad(offset, high_alarm, low_alarm, high_warning, low_warning, signed=False):
            idx = offset - cmis.UPPER_MEMORY_BASE
            for i, v in enumerate((high_alarm, low_alarm, high_warning, low_warning)):
                if v < 0:
                    v += 0x10000
                page[idx + i * 2] = (v >> 8) & 0xFF
                page[idx + i * 2 + 1] = v & 0xFF

        put_quad(cmis.PAGE02_TEMP_THRESHOLDS, int(80 * 256), int(-10 * 256), int(75 * 256), int(-5 * 256), signed=True)
        put_quad(cmis.PAGE02_VCC_THRESHOLDS, int(3.6 / 100e-6), int(3.0 / 100e-6), int(3.5 / 100e-6), int(3.1 / 100e-6))
        for offset in (cmis.PAGE02_AUX1_THRESHOLDS, cmis.PAGE02_AUX2_THRESHOLDS,
                       cmis.PAGE02_AUX3_THRESHOLDS, cmis.PAGE02_CUSTOM_THRESHOLDS):
            put_quad(offset, 100, -100, 80, -80, signed=True)
        put_quad(cmis.PAGE02_TX_POWER_THRESHOLDS, 5000, 100, 4000, 200)
        put_quad(cmis.PAGE02_BIAS_THRESHOLDS, 8000, 500, 7000, 600)
        put_quad(cmis.PAGE02_RX_POWER_THRESHOLDS, 4000, 50, 3500, 100)
        self.pages[0x02] = page

    # --- Pages 10h/11h --------------------------------------------------
    def _setup_page10_11(self):
        self.pages[0x10] = bytearray(128)  # DPDeinit all 0 (all lanes initializing)
        page11 = bytearray(128)
        for byte_i in range(4):
            page11[byte_i] = (cmis.DP_STATE_ACTIVATED << 4) | cmis.DP_STATE_ACTIVATED
        page11[cmis.PAGE11_OUTPUT_STATUS_BYTES[0] - cmis.UPPER_MEMORY_BASE] = 0xFF
        page11[cmis.PAGE11_OUTPUT_STATUS_BYTES[1] - cmis.UPPER_MEMORY_BASE] = 0xFF
        self.pages[0x11] = page11

    # --- Page 12h --------------------------------------------------------
    def _setup_page12(self):
        page = bytearray(128)
        for lane in range(8):
            page[lane] = (0b0100 << 4)  # 50GHz grid, fine tuning disabled
            idx_ch = 8 + lane * 2
            page[idx_ch:idx_ch + 2] = (lane + 1).to_bytes(2, "big", signed=True)
            idx_freq = 40 + lane * 4
            page[idx_freq:idx_freq + 4] = (193100000 + lane).to_bytes(4, "big")  # 193.1THz-ish
            idx_pwr = 72 + lane * 2
            page[idx_pwr:idx_pwr + 2] = (100).to_bytes(2, "big", signed=True)  # 1.00 dBm
        self.pages[0x12] = page

    # --- Pages 13h/14h -----------------------------------------------------
    def _setup_page13_14(self):
        page13 = bytearray(128)
        page13[cmis.PAGE13_LOOPBACK_CAPABILITIES_BYTE - cmis.UPPER_MEMORY_BASE] = 0b01111111
        self.pages[0x13] = page13  # all loopback control bytes left at 0 (disabled)

        page14 = bytearray(128)
        self.pages[0x14] = page14

    # --- Page 15h ------------------------------------------------------
    def _setup_page15(self):
        page = bytearray(128)
        for lane in range(8):
            idx_rx = (cmis.PAGE15_RX_LATENCY_BASE - cmis.UPPER_MEMORY_BASE) + lane * 2
            idx_tx = (cmis.PAGE15_TX_LATENCY_BASE - cmis.UPPER_MEMORY_BASE) + lane * 2
            page[idx_rx:idx_rx + 2] = (100 + lane).to_bytes(2, "big")
            page[idx_tx:idx_tx + 2] = (200 + lane).to_bytes(2, "big")
        self.pages[0x15] = page

    # --- Page 16h/17h ------------------------------------------------------
    def _setup_page16_17(self):
        page16 = bytearray(128)
        for offset in cmis.PAGE16_NP_STATUS_BYTES:
            page16[offset - cmis.UPPER_MEMORY_BASE] = (
                (cmis.NP_STATE_ACTIVATED << 4) | cmis.NP_STATE_ACTIVATED
            )
        self.pages[0x16] = page16
        self.pages[0x17] = bytearray(128)  # no state-changed flags set

    # --- Page 19h ------------------------------------------------------
    def _setup_page19(self):
        page = bytearray(128)
        for lane in range(8):
            page[lane] = (0b0001 << 4) | (0b010 << 1) | 0  # AppSel=1, DataPathID=2, explicit=0
            page[8 + lane] = (0b0001 << 4) | (0b010 << 1) | 0
        self.pages[0x19] = page

    # --- Page 1Ch ------------------------------------------------------
    def _setup_page1c(self):
        page = bytearray(128)
        # one populated NAD (AppSel 1): host_if=1, media_if=2, 4 host lanes, 4 media lanes
        page[0], page[1], page[2] = 1, 2, (4 << 4) | 4
        self.pages[0x1C] = page

    # --- VDM pages 20h-2Fh -----------------------------------------------
    def _setup_vdm_pages(self):
        for page_num in (0x20, 0x21, 0x22, 0x23):
            self.pages[page_num] = bytearray(128)
        # one used instance in group 1: LaserAge, module-wide, LTSID=0
        self.pages[0x20][0] = 0x0F  # LTSID=0, resource=15 (module-wide)
        self.pages[0x20][1] = 0x01  # ObservableType=1 LaserAge

        for page_num in (0x24, 0x25, 0x26, 0x27):
            self.pages[page_num] = bytearray(128)
        self.pages[0x24][0:2] = (12345).to_bytes(2, "big")  # sample for instance 1

        for page_num in (0x28, 0x29, 0x2A, 0x2B):
            self.pages[page_num] = bytearray(128)
        self.pages[0x28][0:8] = bytes([0x00, 0x64, 0x00, 0x0A, 0x00, 0x50, 0x00, 0x14])  # LTSID0 quad

        self.pages[0x2C] = bytearray(128)  # VDM Flags
        self.pages[0x2D] = bytearray(128)  # VDM Masks
        page2f = bytearray(128)
        page2f[cmis.PAGE2F_VDM_SUPPORT_BYTE - cmis.UPPER_MEMORY_BASE] = 0x00  # 1 active group
        self.pages[0x2F] = page2f

    # --- Bridge-compatible interface --------------------------------------
    def scan(self):
        return [cmis.CMIS_I2C_ADDR]

    def close(self):
        pass

    def _current_page_buffer(self):
        if self.page_select not in self.pages:
            self.pages[self.page_select] = bytearray(128)
        return self.pages[self.page_select]

    def _select_page(self, bank, page):
        # Every page this simulator actually populated is "supported";
        # anything else falls back to Page 00h per the documented gotcha.
        if page in self.pages and bank == 0x00:
            self.bank_select, self.page_select = bank, page
        else:
            self.bank_select, self.page_select = 0x00, 0x00
        self.lower[cmis.BANK_SELECT_BYTE] = self.bank_select
        self.lower[cmis.PAGE_SELECT_BYTE] = self.page_select

    def write(self, addr, data):
        data = list(data)
        offset = data[0]
        payload = data[1:]
        if not payload:
            return

        if offset == cmis.BANK_SELECT_BYTE and len(payload) >= 2:
            self._select_page(payload[0], payload[1])
            return

        if offset < 0x80:
            self.lower[offset:offset + len(payload)] = bytes(payload)
            if offset == cmis.PASSWORD_ENTRY_AREA[0]:
                password = int.from_bytes(bytes(payload[:4]), "big")
                if password == cmis.DEFAULT_HOST_PASSWORD:
                    self._unlock_status = 0x01
            return

        page = self._current_page_buffer()
        idx = offset - cmis.UPPER_MEMORY_BASE
        page[idx:idx + len(payload)] = bytes(payload)

        if self.page_select == 0x9F and offset == cmis.UPPER_MEMORY_BASE and len(payload) >= 5:
            self._execute_cdb_command(bytes(payload))
        if self.page_select == cmis.PAGE_VDM_CONTROL and offset == cmis.PAGE2F_FREEZE_REQUEST_BYTE:
            self._handle_vdm_freeze(payload[0])
        if self.page_select == cmis.PAGE_DIAG_RESULTS and offset == cmis.PAGE14_DIAGNOSTICS_SELECTOR_BYTE:
            self._handle_diagnostics_selector(payload[0])

    def read(self, addr, n):
        return self.write_read(addr, [0x00], n)

    def write_read(self, addr, data, n):
        offset = list(data)[0]
        if offset < 0x80:
            return bytes(self.lower[offset:offset + n])
        page = self._current_page_buffer()
        idx = offset - cmis.UPPER_MEMORY_BASE
        return bytes(page[idx:idx + n])

    # --- CDB command execution ---------------------------------------------
    def _execute_cdb_command(self, command_bytes):
        cmd_id = (command_bytes[0] << 8) | command_bytes[1]
        lpl_length = command_bytes[4]
        received_checksum = command_bytes[5]
        lpl_payload = bytes(command_bytes[6:6 + lpl_length])

        expected_checksum = cmis.compute_cdb_checksum(bytes(command_bytes[0:5]) + lpl_payload)
        page9f = self.pages[0x9F]

        if received_checksum != expected_checksum:
            self._set_cdb_status(busy=False, failed=True, result=cmis.CDB_RESULT_FAILED_CHECKSUM_ERROR)
            page9f[cmis.CDB_REPLY_HEADER_RPL_LENGTH - cmis.UPPER_MEMORY_BASE] = 0
            return

        dispatch_result = self._dispatch_cdb_command(cmd_id, lpl_payload)
        if dispatch_result is None:
            self._set_cdb_status(busy=False, failed=True, result=cmis.CDB_RESULT_FAILED_UNKNOWN_CMDID)
            page9f[cmis.CDB_REPLY_HEADER_RPL_LENGTH - cmis.UPPER_MEMORY_BASE] = 0
            return

        success, failure_result, reply_lpl = dispatch_result
        if not success:
            self._set_cdb_status(busy=False, failed=True, result=failure_result)
            page9f[cmis.CDB_REPLY_HEADER_RPL_LENGTH - cmis.UPPER_MEMORY_BASE] = 0
            return

        self._set_cdb_status(busy=False, failed=False, result=cmis.CDB_RESULT_SUCCESS_COMPLETED)
        page9f[cmis.CDB_REPLY_HEADER_RPL_LENGTH - cmis.UPPER_MEMORY_BASE] = len(reply_lpl)
        lpl_base_idx = cmis.CDB_LPL_BASE - cmis.UPPER_MEMORY_BASE
        page9f[lpl_base_idx:lpl_base_idx + len(reply_lpl)] = reply_lpl

    def _dispatch_cdb_command(self, cmd_id, lpl_payload):
        """Returns None for an unrecognized CMDID, or (success, failure_result_code,
        reply_lpl) -- failure_result_code is only meaningful when success is False."""
        if cmd_id == cmis.CDB_CMD_QUERY_STATUS:
            return True, None, bytes([2, self._unlock_status])
        if cmd_id == cmis.CDB_CMD_ABORT:
            return True, None, b""
        if cmd_id == cmis.CDB_CMD_MODULE_FEATURES:
            reply = bytearray(36)
            reply[2] = 0b00010001  # CMDIDs 0x00 (Query Status) and 0x04 (Abort) supported
            reply[34:36] = (500).to_bytes(2, "big")  # MaxCompletionTime = 500ms
            return True, None, bytes(reply)
        if cmd_id == cmis.CDB_CMD_FW_MANAGEMENT_FEATURES:
            reply = bytearray(18)
            reply[1] = 0b00000011  # copy + abort supported, x1 duration multiplier
            reply[2] = 116  # StartCmdPayloadSize
            reply[3] = 0xFF  # ErasedByte
            reply[4] = 15    # ReadWriteLengthExt -> 128 byte EPL/LPL max
            reply[5] = 0b11  # WriteMechanism = both
            reply[6] = 0b01  # ReadMechanism = LPL
            return True, None, bytes(reply)
        if cmd_id == cmis.CDB_CMD_GET_FIRMWARE_INFO:
            return True, None, bytes([0x01, 0x01, 0x01, 0x00])  # bank A operational, image A present, v1.0
        if cmd_id == cmis.CDB_CMD_ENTER_PASSWORD:
            password = int.from_bytes(lpl_payload[:4], "big")
            if password == cmis.DEFAULT_HOST_PASSWORD:
                self._unlock_status = 0x01
                return True, None, b""
            return False, cmis.CDB_RESULT_FAILED_PASSWORD_ERROR, b""
        return None

    def _set_cdb_status(self, busy, failed, result):
        byte = (0x80 if busy else 0) | (0x40 if failed else 0) | (result & 0x3F)
        self.lower[cmis.CDB_STATUS_1_BYTE] = byte
        self.lower[cmis.CDB_CMD_COMPLETE_FLAG_BYTE] |= 0x40

    def _handle_diagnostics_selector(self, selector):
        page14 = self.pages[0x14]
        window_idx = cmis.PAGE14_DIAGNOSTICS_DATA_BASE - cmis.UPPER_MEMORY_BASE
        window = bytearray(64)
        if selector == cmis.DIAG_SELECTOR_HOST_COUNTERS_1_4:
            for lane in range(4):
                base = lane * 16
                window[base:base + 8] = (1000 * (lane + 1)).to_bytes(8, "little")
                window[base + 8:base + 16] = (10_000_000 + lane).to_bytes(8, "little")
        elif selector == cmis.DIAG_SELECTOR_BER_REALTIME:
            raw_f16 = (5 << 11) | 100  # arbitrary small BER-like value
            for lane in range(8):
                window[lane * 2] = raw_f16 & 0xFF
                window[lane * 2 + 1] = (raw_f16 >> 8) & 0xFF
                window[16 + lane * 2] = raw_f16 & 0xFF
                window[16 + lane * 2 + 1] = (raw_f16 >> 8) & 0xFF
        elif selector == cmis.DIAG_SELECTOR_SNR_REALTIME:
            raw_snr = int(20.5 * 256)  # 20.5 dB
            for lane in range(8):
                window[lane * 2:lane * 2 + 2] = raw_snr.to_bytes(2, "little")
                window[16 + lane * 2:16 + lane * 2 + 2] = raw_snr.to_bytes(2, "little")
        page14[window_idx:window_idx + 64] = window

    def _handle_vdm_freeze(self, freeze_byte):
        page2f = self.pages[cmis.PAGE_VDM_CONTROL]
        status_idx = cmis.PAGE2F_FREEZE_DONE_UNFREEZE_DONE_BYTE - cmis.UPPER_MEMORY_BASE
        if freeze_byte & 0x80:
            page2f[status_idx] = 0x80  # FreezeDone
        else:
            page2f[status_idx] = 0x40  # UnfreezeDone
