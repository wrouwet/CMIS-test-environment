# CMIS Test Environment

A pytest-based test suite, run from a host PC, for exercising an optical
transceiver module (QSFP-DD/OSFP-style pluggable) over its management
interface, per CMIS (the Common Management Interface Specification).
Sibling project to
[openbic-test-environment](https://github.com/wrouwet/openbic-test-environment)
(IPMB) and [mctp-test-environment](https://github.com/wrouwet/mctp-test-environment)
(MCTP) -- same style and philosophy, a different target protocol.

## Current status: no test target yet, but real spec-sourced code

Unlike the sibling projects at their equivalent stage, this repo skips
straight to spec-accurate code rather than placeholder scaffolding,
because the CMIS register map was researched directly from the primary
source before any code was written -- see "Source of truth" below.
**But there is still no physical CMIS module connected**, so nothing
here has been verified against real hardware yet. What HAS been done
without hardware:

- The register-parsing logic (`cmis.py`'s `parse_lower_memory()`,
  `parse_page00_vendor_info()`, `verify_page00_checksum()`,
  `build_page_select()`) has been unit-tested against hand-built
  synthetic byte buffers with known values -- confirming the
  offset/bit-field math is internally consistent with itself, which is
  a real but limited form of confidence: it proves the code does what
  the spec text says, not that the spec text was transcribed correctly,
  and definitely not that a real module actually behaves this way.
- All 49 tests in `tests/` collect cleanly under pytest (no import/syntax
  errors) and 48 PASS + 1 correctly SKIPS against `fake_cmis_module.py`'s
  in-memory simulator (`CMIS_USE_FAKE_BRIDGE=1`, see "Dry-running"
  below) -- but none have executed against a real `bridge` fixture /
  real hardware.

**Treat every byte offset and field meaning as "correctly transcribed
from the spec", not "confirmed against real silicon", until this
section is updated.** Once a module exists: run `./run_tests.sh` and
expect real, first-contact issues, not a clean pass -- see the sibling
projects' own history for how reliably that's been true so far.

## Source of truth

Every register offset, field, and gotcha in this repo is sourced
directly from:

> "Common Management Interface Specification (CMIS)", Rev 5.0,
> 2021-05-08, QSFP-DD MSA (hosted as a third-party spec by OIF)
> https://www.oiforum.com/wp-content/uploads/CMIS5p0_Third_Party_Spec.pdf

fetched and verified 2026-08-27 (302 pages, confirmed against the
title page). Section/table/page numbers are cited in code comments next
to each fact so anything here can be checked directly against that
document. CMIS 4.0, 5.1, 5.2, and 5.3 were subsequently also fetched and
independently checked against this project's decoded fields -- see
`cmis.VERSION_HISTORY` and the module-docstring citations throughout
`cmis.py` for what was cross-checked and where.

**Scope note on I3C**: despite the project name-check ("optical
transceiver talking I2C/I3C"), CMIS never adopts I3C as a management
transport, in any revision -- confirmed by grepping the full text of
4.0, 5.0, 5.1, 5.2, and 5.3, zero "I3C" hits in any of them. I2C
("I2CMCI") is the sole transport through 5.2. Revision 5.3
(OIF-CMIS-05.3, 2024-09-04) adds a second transport, but it's SPI
("SPIMCI", for co-packaged-optics use cases) -- not I3C, and it uses a
dedicated per-module chip-select wire rather than any form of shared-bus
addressing. **This project is I2C-only, and expects to stay that way.**

**Version compatibility**: CMIS 3.0/4.0/5.0/5.1 were QSFP-DD MSA
documents merely hosted by OIF; from 5.2 onward OIF itself publishes
CMIS as a formal Implementation Agreement (`OIF-CMIS-05.x`). The spec's
own compatibility rule (Appendix G): revisions sharing a major number
are backward-compatible (5.0/5.1/5.2/5.3 implementations are all
mutually compatible); the one real breaking change in the whole
lineage is 4.0->5.0, where the spec itself warns interoperability
"may or may not" work. Everything this project currently decodes was
independently confirmed byte-identical across the 4.0 and 5.3 documents
-- see `cmis.py`'s module docstring and `cmis.VERSION_HISTORY` for the
full citation trail. This is why the suite discovers-and-adapts (see
below) rather than branching on version internally: nothing decoded so
far actually differs by version, only by memory model.

## What you need before you start

**Hardware:**

1. A FRDM-MCXA153 bridge board flashed with the firmware from
   [frdm-mcxa153-usb-i2c-hub](https://github.com/wrouwet/frdm-mcxa153-usb-i2c-hub),
   wired to the transceiver module's management I2C bus.
2. A CMIS-compliant transceiver module (QSFP-DD, OSFP, or similar),
   powered, with its management interface accessible on that bus.

**One real architectural constraint worth knowing before wiring
multiple modules**: per the spec (Appendix B.2.1, B.2.4.1.4), every
CMIS module answers at the same fixed I2C address, `0x50` -- there is
no I2C-address-based way to distinguish multiple modules on a shared
bus. Real systems use an external, per-module hardware `ModSel` signal
for that. **This project assumes a single module per bus** and doesn't
attempt module-select signaling.

**Software**: same as the sibling projects -- Linux, Python 3.9+ with
`venv`, and `dialout` group membership (see the sibling projects'
READMEs for the full explanation of that gotcha).

## Quick start

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest tests/          # or ./run_tests.sh to also save test_report.txt
```

Without the hardware above connected, expect every test to fail at the
`bridge` fixture or at bus detection with a clear error -- that's
expected, not a code bug.

**Dry-running without hardware**: `CMIS_USE_FAKE_BRIDGE=1 .venv/bin/pytest tests/`
runs the whole suite against `fake_cmis_module.py`, an in-memory CMIS
module simulator, instead of a real bridge. 48 of 49 tests pass against
it as of this writing (1 correctly skips, a Flat-memory-only check
against a simulator that reports Paged) -- this proves the test code
itself runs correctly
end-to-end (real page-select/read/decode/assert round trips, not just
`--collect-only`), which is a genuinely useful signal while there's no
real hardware to test against. It is NOT evidence a real module behaves
this way -- see the file's own docstring for why.

## Layout

```
bridge.py               Python client for the bridge's text command protocol
                         (shared with the sibling projects)
cmis.py                 CMIS register map, field decoding, checksum/page-
                         select helpers -- see its module docstring for
                         full spec citations
cmis_helpers.py         Shared register-read/page-select plumbing built
                         on bridge.py's generic write()/write_read()
fake_cmis_module.py     in-memory CMIS module simulator for dry-running the
                         suite without hardware (CMIS_USE_FAKE_BRIDGE=1)
conftest.py             pytest fixture that connects the bridge once per session
tests/config.py         shared constants (module I2C address)
tests/test_bus.py       bus presence
tests/test_discovery.py CMIS's own on-the-wire discovery (revision, memory model) -- see below
tests/test_lower_memory.py
                         Identifier, CMIS revision, Module State, temp/VCC monitors
tests/test_page00_vendor_info.py
                         page selection + vendor identification block + checksum
tests/test_page01_advertising.py
                         capability advertisement, incl. whether CDB exists at all
tests/test_page02_thresholds.py
                         module-level alarm/warning threshold quads
tests/test_datapath.py  Pages 10h/11h -- per-lane Data Path state machine
tests/test_page03_user_eeprom.py
                         Page 03h -- real, non-destructive write/read/restore round trip
tests/test_page15_timing.py
                         Page 15h -- per-lane Rx/Tx transit latency
tests/test_page_select_edge_cases.py
                         page-select protocol itself: idempotency, the
                         unsupported-page-falls-back-to-0x00 gotcha, read/write isolation
tests/test_environmental_thresholds.py
                         live Lower Memory monitors cross-checked against Page 02h thresholds
tests/test_vdm.py       Pages 20h-2Fh -- VDM descriptor/sample dump + freeze/unfreeze handshake
tests/test_cdb.py       CDB (Page 9Fh + Lower Memory CdbStatus): Query Status, Abort,
                         Module/Firmware-Management Features, Get Firmware Info,
                         plus negative-path bad-checksum/unknown-CMDID rejection tests
tests/test_cdb_epl.py   CDB EPL (Pages A0h-AFh) framing -- unit tests only, no live send
tests/test_password.py  password mechanism: register-based AND CDB-based (Enter Password) unlock
tests/test_page12_tunable_laser.py
                         Page 12h -- per-lane grid spacing/channel/frequency/tuning status (read-only)
tests/test_page13_loopback.py
                         Page 13h -- loopback capabilities + confirms none active (read-only)
tests/test_page14_diagnostics.py
                         Page 14h -- DiagnosticsSelector mux + host-lane error/bit counters
tests/test_page16_17_network_path.py
                         Pages 16h/17h -- Network Path state machine + flags (5.1+)
tests/test_page19_datapath_config.py
                         Page 19h -- per-lane Tx/Rx Data Path config (5.2+, read-only)
tests/test_page1c_nad.py
                         Page 1Ch -- Normalized Application Descriptors (5.3+, read-only)
tests/test_page_enumeration.py
                         structure-agnostic sweep of the whole known page-number space
tests/test_advertised_vs_actual_pages.py
                         cross-checks Page 01h advertisement bits against actual selectability
```

## Architecture: discover the version, don't hardcode per-version suites

CMIS provides a real, on-the-wire discovery mechanism: every module
self-reports its own CMIS revision (Lower Memory byte `0x01`) and
whether it runs a Paged or Flat memory model (byte `0x02`, bit 7) --
the latter directly determining which pages even exist to test. Per
explicit user direction, this project uses that discovery mechanism
instead of maintaining separate hardcoded test suites per CMIS version
(4.0, 5.0, 5.2, ...): `cmis_helpers.discover_module()` reads and PRINTS
this up front every run (via the session-scoped `module_info` fixture,
triggered first by `tests/test_discovery.py`), and the rest of the
suite is expected to branch or skip cleanly based on what's actually
discovered -- not assume a specific version's behavior. As more of the
spec gets covered (Application Advertising, Datapath pages, CDB, VDM --
see "Known gaps" below), each new test file should gate on `module_info`
where a page/field genuinely doesn't exist on some discovered
version/model, printing why it's skipping, rather than either failing
on an absent feature or silently assuming every module looks like the
one this suite happened to be written against.

## Key CMIS facts this project relies on (see cmis.py for full citations)

- **Memory map**: Lower Memory (addresses `0x00`-`0x7F`) is static --
  the same register always lives at the same address. Upper Memory
  (`0x80`-`0xFF`) is paged -- its meaning depends on the currently
  selected page, written to two bytes at `0x7E`/`0x7F` (bank/page
  select). This is a genuinely paged model, not SFF-8636's flat memory
  map (though CMIS modules can also run in an explicit Flat Memory mode
  for simpler designs).
- **Gotcha**: writing an *unsupported* page number doesn't error --
  it silently resets the page selection back to `0x00`. Always read
  back the page-select bytes if you need to confirm a page change
  actually took (see `test_page00_vendor_info.py` for exactly this
  check) -- don't assume a write succeeding at the I2C level means the
  page actually changed.
- **Gotcha**: after selecting a new page, reads aren't guaranteed valid
  for up to 10ms (`tBPC`); after a write to a volatile register, up to
  10ms (`tWRITE`); after a write to non-volatile memory, up to 80ms
  (`tWRITENV`). This project's `cmis_helpers.select_page()` does a plain
  sleep for the first case; the spec's own recommended approach is
  ACK-polling instead of blindly sleeping the max duration, which isn't
  implemented here yet.
- **Open question, not yet resolved**: the exact Page 00h checksum
  algorithm (a plain 8-bit sum of bytes `0x80`-`0xDD` vs. some
  complement variant) wasn't confirmed from the spec text directly --
  implemented as a plain sum (the common SFF-8636/SFF-8472 convention)
  but flagged in `cmis.verify_page00_checksum()`'s docstring as an
  inference, not a confirmed fact. If a real module's checksum never
  matches, check this first before assuming the module itself is at
  fault.

## Known gaps / coming next

Coverage now spans Lower Memory (incl. CDB status), Page 00h (vendor
info), Page 01h (advertising -- 4.0-5.3-aware, fully bit-decoded
including the 5.1/5.2/5.3-added pages' advertisement bits), Page 02h
(module + lane-specific thresholds), Page 03h (user EEPROM), 10h/11h
(lane control/status), 12h (tunable laser), 13h/14h (loopback,
diagnostics selector + error counters), 15h (timing), 16h/17h (Network
Path, 5.1+), 19h (Data Path config, 5.2+), 1Ch (Normalized Application
Descriptors, 5.3+), VDM (Pages 20h-2Fh), both password mechanisms, and a
real CDB command set (Query Status, Abort, Module/Firmware-Management
Features, Get Firmware Info, negative-path bad-checksum/unknown-CMDID
tests, plus builders for the firmware-download sequence). Confirmed NOT
yet covered, sourced the same way (primary spec text, cited, not
guessed):

- **CDB firmware-download sequence, actually exercised live**: builders
  exist (`build_cdb_start_firmware_download()`, `build_cdb_write_firmware_block_lpl()`,
  `build_cdb_copy_firmware_image()`, `build_cdb_run_firmware_image()`) but
  no test sends them -- deliberately, since they have real, persistent
  side effects on a live module (this would need an actual firmware
  image and explicit opt-in, not something to run unprompted). EPL-carried
  (>120 byte) command payloads (Pages A0h-AFh) also aren't wired up.
- **VDM Observable Type table** (`cmis.VDM_OBSERVABLE_TYPES`) now covers
  every ID confirmed across CMIS 4.0-5.4 (0-24 stable since 5.0; 25-26
  added 5.2; 27-34/77-84 added 5.3) via `interpret_vdm_sample()` --
  IDs 100-127 (Custom) and 128-255 (Restricted/OIF) are still
  unavoidably vendor/OIF-specific and not decodable in principle.
- Page 14h now decodes all its non-Custom/non-Reserved selectors: BER
  (F16), SNR (scaled U16), and the 4-lane U64 error/bit counters.
- **CMIS's F16 data type** (`cmis.decode_f16()`, used by Page 14h's BER
  selector and several VDM observables) has NO worked example anywhere
  in the fetched spec text (4.0-5.4) -- implemented directly from the
  formal bit-layout/formula (5-bit scaled exponent, base-10, offset -24;
  11-bit mantissa), not cross-checked against a known-good input/output
  pair. Page 14h's specific byte-order for this field (assumed
  little-endian, matching its error counters) is a related inference,
  not confirmed from an explicit byte-offset table for that field.
- **Page 05h** (form-factor-specific signals, 5.2+): confirmed to have
  **no byte/bit layout in any of the four fetched CMIS primary spec
  documents (4.0-5.3)** -- it's defined in a separate, at-research-time
  unpublished supplement (`OIF-CMIS-FF-01.0`). Only presence (via Page
  01h byte 142 bit 3) is decodable; content decoding is blocked on that
  supplement becoming available, not on further effort here.
- **Page 18h**: reserved-but-empty in CMIS 5.2 (literally "reserved for
  expansion of Page 10h," no fields); gains real content only in CMIS
  5.3 (NAD block indices + an external "Versatile Control Set" parameter
  space, itself a separate spec) -- not decoded, since it's either empty
  or depends on another unfetched supplement depending on revision.
- **Page 19h's CMIS 5.3 extension** (NAD block indices, ACS Versatile
  Control Set parameter space at bytes 144-207) -- only the base Tx/Rx
  config fields (bytes 128-143, unchanged since 5.2) are decoded.
- **CDB checksum algorithm caveat**: the spec's prose calls CdbChkCode a
  "one's complement," but the one worked example available (0004h Abort,
  fixed CdbChkCode=FCh) only checks out as a negation
  (`(0x100 - sum) & 0xFF`), not a plain bitwise complement -- implemented
  to match the worked example; flagged in `cmis.compute_cdb_checksum()`'s
  docstring in case a real module disagrees. A second research pass
  reported FIXED checksum values for 0102h (Abort Firmware Download,
  claimed FCh) and 0107h (Complete Firmware Download, claimed F7h) that
  do NOT recompute correctly from their own CMDID via this project's
  negation formula (0102h computes to 0xFD, 0107h to 0xF8) -- likely a
  transcription slip in that research pass reusing 0004h's value, not a
  real inconsistency, but flagged rather than silently trusted since it
  wasn't independently re-verified against the primary table.
- **`vcs_supported` (Page 01h byte 162 bit 7)**: the field's exact name
  wasn't captured verbatim by the research pass that found it (inferred
  from context as gating the Versatile Control Set parameter space) --
  lower confidence than the rest of this file's Page 01h bit decoding.
- **Page 01h fiber-length/wavelength/module-characteristic advertising**
  (bytes 132-190+, beyond the specific bits this project decodes) --
  `parse_page01_advertising()` only decodes what current tests use.
- **SPIMCI** (the SPI transport added in CMIS 5.3) -- confirmed to exist,
  not implemented; this project remains I2C-only by design (see "Scope
  note on I3C" above), so this is noted for awareness, not planned work,
  unless a real need for it shows up.

## Adding tests

Same conventions as the sibling projects: prefer confirming behavior
against the primary spec document (with a page/table citation) or live
hardware observation over guessing at spec-typical behavior. Given this
project currently has zero hardware verification, be extra conservative
about what gets asserted vs. just printed for visibility -- see the
existing tests' docstrings for the pattern.
