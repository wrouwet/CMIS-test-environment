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
- All 5 tests in `tests/` collect cleanly under pytest (no import/syntax
  errors), but have never executed against a real `bridge` fixture.

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
document. Newer CMIS revisions exist (5.1/5.2/5.3 were seen in search
results) but were not fetched/verified -- if a newer revision matters
for your module, that's worth checking before trusting this repo's
specifics.

**Scope note on I3C**: despite the project name-check ("optical
transceiver talking I2C/I3C"), CMIS Rev 5.0 defines I2C as its only
management transport -- the full spec text was searched for "I3C" and
returned zero hits; Appendix B explicitly says only an I2C-based
variant is described in this revision. I3C support may exist in a later
CMIS revision, not yet researched. **This project is I2C-only for now.**

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

## Layout

```
bridge.py               Python client for the bridge's text command protocol
                         (shared with the sibling projects)
cmis.py                 CMIS register map, field decoding, checksum/page-
                         select helpers -- see its module docstring for
                         full spec citations
cmis_helpers.py         Shared register-read/page-select plumbing built
                         on bridge.py's generic write()/write_read()
conftest.py             pytest fixture that connects the bridge once per session
tests/config.py         shared constants (module I2C address)
tests/test_bus.py       bus presence
tests/test_lower_memory.py
                         Identifier, CMIS revision, Module State, temp/VCC monitors
tests/test_page00_vendor_info.py
                         page selection + vendor identification block + checksum
```

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

## Adding tests

Same conventions as the sibling projects: prefer confirming behavior
against the primary spec document (with a page/table citation) or live
hardware observation over guessing at spec-typical behavior. Given this
project currently has zero hardware verification, be extra conservative
about what gets asserted vs. just printed for visibility -- see the
existing tests' docstrings for the pattern.
