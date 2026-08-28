"""CDB EPL (Extended Payload, Pages A0h-AFh) framing -- pure unit tests,
no hardware needed. This project deliberately does NOT send an
EPL-carried CDB command against real hardware (see test_cdb.py's module
docstring: commands with real side effects aren't exercised live), so
this only verifies the segmenting/header-building logic itself against
synthetic data.
"""

import cmis


def test_epl_segmentation_exact_multiple():
    payload = bytes(range(128)) * 2  # exactly 256 bytes = 2 pages
    segments = cmis.build_cdb_epl_segments(payload)
    assert len(segments) == 2
    assert segments[0][0] == cmis.PAGE_CDB_EPL_BASE
    assert segments[1][0] == cmis.PAGE_CDB_EPL_BASE + 1
    assert segments[0][1] == payload[0:128]
    assert segments[1][1] == payload[128:256]


def test_epl_segmentation_pads_last_chunk():
    payload = bytes(range(10))  # 10 bytes, needs padding to 128
    segments = cmis.build_cdb_epl_segments(payload)
    assert len(segments) == 1
    page, chunk = segments[0]
    assert page == cmis.PAGE_CDB_EPL_BASE
    assert len(chunk) == 128
    assert chunk[:10] == payload
    assert chunk[10:] == bytes(118)  # zero-padded


def test_epl_segmentation_rejects_oversized_payload():
    try:
        cmis.build_cdb_epl_segments(bytes(2049))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for a >2048 byte EPL payload")


def test_build_cdb_command_with_epl_sets_epl_length():
    header, segments = cmis.build_cdb_command_with_epl(
        cmis.CDB_CMD_WRITE_FIRMWARE_BLOCK_EPL, epl_payload=bytes(300), lpl_payload=b"")
    epl_length = (header[2] << 8) | header[3]
    lpl_length = header[4]
    print(f"header={header.hex()}, epl_length={epl_length}, lpl_length={lpl_length}, "
          f"segments={len(segments)}")
    assert epl_length == 300
    assert lpl_length == 0
    assert len(segments) == 3  # ceil(300/128)
